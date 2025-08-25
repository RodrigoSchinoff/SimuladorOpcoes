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
    Busca opções na API para 'ativo_base' e faz UPSERT na tabela (ON CONFLICT(symbol) DO UPDATE).
    - Se 'so_vencimento' for informado, filtra aquele due_date.
    - Preenche parent_symbol com 'ativo_base' quando vier ausente/NULL no JSON.
    """
    ativo_norm = (ativo_base or "").upper().strip()

    # 1) Busca dados na API
    dados = buscar_opcoes_ativo(ativo_norm)
    rows = _to_list(dados)

    if so_vencimento:
        rows = [r for r in rows if r.get("due_date") == so_vencimento]

    if not rows:
        return 0

    # 2) Colunas existentes na tabela
    colunas_tabela = _colunas_da_tabela()

    # 3) Interseção: só chaves que existam como colunas
    colunas_insert = [c for c in colunas_tabela if any(c in r for r in rows)]

    # ⚠️ Garantir que 'symbol' (PK) e 'parent_symbol' entrem no INSERT
    if "symbol" not in colunas_insert:
        raise RuntimeError("A coluna 'symbol' (PK) precisa existir na tabela e no JSON.")
    if "parent_symbol" in colunas_tabela and "parent_symbol" not in colunas_insert:
        colunas_insert.append("parent_symbol")

    # 4) Montar valores respeitando a ordem das colunas
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

    # 5) INSERT ... ON CONFLICT(symbol) DO UPDATE (UPSERT)
    cols_sql = ", ".join([f'"{c}"' for c in colunas_insert])

    set_cols = [c for c in colunas_insert if c != "symbol"]
    tem_updated_at = "updated_at" in colunas_tabela
    updated_at_clause = '"updated_at" = NOW()' if tem_updated_at and "updated_at" not in set_cols else None

    if set_cols:
        set_list = [f'"{c}" = EXCLUDED."{c}"' for c in set_cols]
        if updated_at_clause:
            set_list.append(updated_at_clause)
        set_clause = ", ".join(set_list)
        on_conflict = f'ON CONFLICT ("symbol") DO UPDATE SET {set_clause}'
    else:
        on_conflict = 'ON CONFLICT ("symbol") DO NOTHING'

    sql = f'INSERT INTO "{ESQUEMA}"."{TABELA}" ({cols_sql}) VALUES %s {on_conflict}'

    # 6) Execução em lote
    con = conectar()
    if not con:
        raise RuntimeError("Sem conexão.")
    try:
        cur = con.cursor()
        execute_values(cur, sql, valores, page_size=1000)
        con.commit()
        return len(valores)
    finally:
        con.close()
