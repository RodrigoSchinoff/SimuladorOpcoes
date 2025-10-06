# etl/carregar_opcoes_db.py
from typing import Any, Dict, List, Tuple, Optional
from psycopg2.extras import execute_values
from db.conexao import conectar
from services.api import buscar_opcoes_ativo

TABELA = "opcoes_do_ativo"
ESQUEMA = "public"  # ajuste se usar outro schema

def _colunas_da_tabela() -> List[str]:
    con = conectar()
    if not con:
        raise RuntimeError("Sem conexão.")
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """, (ESQUEMA, TABELA))
        return [r[0] for r in cur.fetchall()]
    finally:
        con.close()

def _to_list(json_result: Any) -> List[Dict[str, Any]]:
    if isinstance(json_result, dict):
        return [json_result]
    if isinstance(json_result, list):
        return json_result
    raise TypeError(f"Resposta inesperada da API: {type(json_result)}")

def inserir_opcoes_do_ativo(ativo_base: str, so_vencimento: Optional[str] = None) -> int:
    """
    Busca opções na API para 'ativo_base' e faz UPSERT na tabela public.opcoes_do_ativo.
    Regras:
      - Mantém os timestamps do PROVEDOR (JSON): created_at / updated_at (se existirem no JSON e na tabela).
      - Controla frescor por coluna PRÓPRIA: data_ultima_consulta (server-side).
          * INSERT: usa DEFAULT now() (coluna fica fora da lista do INSERT)
          * UPDATE: força "data_ultima_consulta = NOW()" no DO UPDATE
      - Chave de conflito: ("symbol").
      - parent_symbol recebe ativo_base quando vier ausente/vazio no JSON.
    """
    ativo_norm = (ativo_base or "").upper().strip()

    # 1) Busca dados na API (uma chamada única, todas as séries)
    dados = buscar_opcoes_ativo(ativo_norm)
    rows = _to_list(dados)

    print(f"DEBUG1: len(rows)= {len(rows)}", flush=True)
    if rows:
        print(f"DEBUG1: keys[0]= {sorted(list(rows[0].keys()))}", flush=True)
        try:
            print("DEBUG1: sample spot/bid =", rows[0].get("spot_price"), rows[0].get("bid"), flush=True)
        except Exception:
            pass
        n_spot = sum(1 for r in rows if r.get("spot_price") is not None)
        print(f"DEBUG1: possui 'spot_price' em quantas linhas? {n_spot} nulos spot_price: {len(rows) - n_spot}",
              flush=True)

    # (opcional) filtrar por vencimento específico
    if so_vencimento:
        rows = [r for r in rows if r.get("due_date") == so_vencimento]

    if not rows:
        return 0

    # 2) Colunas existentes na tabela
    colunas_tabela = _colunas_da_tabela()

    print("DEBUG2: 'spot_price' na tabela?", "spot_price" in colunas_tabela, flush=True)
    print("DEBUG2: total colunas_tabela =", len(colunas_tabela), flush=True)

    # 3) Interseção: só colunas que EXISTEM NA TABELA e aparecem em PELO MENOS UM item do JSON
    #    OBS: NÃO colocamos "data_ultima_consulta" aqui para o INSERT usar DEFAULT now() no servidor.
    colunas_insert = [c for c in colunas_tabela if any(c in r for r in rows) and c != "data_ultima_consulta"]

    # 4) Garantias mínimas
    if "symbol" not in colunas_insert:
        raise RuntimeError("A coluna 'symbol' (PK/UNIQUE) precisa existir na tabela e no JSON.")
    if "parent_symbol" in colunas_tabela and "parent_symbol" not in colunas_insert:
        colunas_insert.append("parent_symbol")

    # 5) Montar valores (na ordem de colunas_insert)
    valores: List[Tuple] = []
    for r in rows:
        linha = []
        for c in colunas_insert:
            v = r.get(c, None)
            if c == "parent_symbol":
                # se vier vazio, usa o ativo_base informado
                if v is None or (isinstance(v, str) and v.strip() == ""):
                    v = ativo_norm
            linha.append(v)
        valores.append(tuple(linha))

    # 6) UPSERT: INSERT ... ON CONFLICT("symbol") DO UPDATE ...
    cols_sql = ", ".join([f'"{c}"' for c in colunas_insert])

    # No DO UPDATE, atualizamos TODAS as colunas do INSERT (exceto symbol)
    # e SEMPRE "data_ultima_consulta = NOW()" se a coluna existir na tabela.
    set_cols = [c for c in colunas_insert if c != "symbol"]

    if set_cols:
        set_list = [f'"{c}" = EXCLUDED."{c}"' for c in set_cols]

        # ✅ nossa coluna de frescor (server-side, independente do provedor)
        if "data_ultima_consulta" in colunas_tabela:
            set_list.append('"data_ultima_consulta" = NOW()')

        set_clause = ", ".join(set_list)
        on_conflict = f'ON CONFLICT ("symbol") DO UPDATE SET {set_clause}'
    else:
        on_conflict = 'ON CONFLICT ("symbol") DO NOTHING'

    sql = f'INSERT INTO "{ESQUEMA}"."{TABELA}" ({cols_sql}) VALUES %s {on_conflict}'

    # 7) Execução em lote
    con = conectar()
    if not con:
        raise RuntimeError("Sem conexão.")
    try:
        cur = con.cursor()
        execute_values(cur, sql, valores, page_size=1000)
        con.commit()
        return len(valores)
    finally:
        try:
            con.close()
        except Exception:
            pass
