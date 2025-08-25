# repositories/opcoes_repo.py
from typing import List, Dict, Any
import psycopg2.extras
from db.conexao import conectar

def buscar_opcoes_por_ticker_vencimento(ticker: str, due_date: str) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            symbol,
            COALESCE(type, category) AS tipo,
            parent_symbol,
            strike,
            bid, ask, --last,
            close,
            contract_size,
            spot_price,
            due_date
        FROM opcoes_do_ativo
        WHERE parent_symbol = %s
          AND due_date = %s
        ORDER BY strike, symbol
    """
    conn = conectar()
    if not conn:
        raise RuntimeError("Não foi possível conectar ao banco.")
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (ticker.upper().strip(), due_date))
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    finally:
        try: conn.close()
        except Exception: pass

def listar_vencimentos(ticker: str) -> List[str]:
    sql = """
        SELECT DISTINCT due_date
        FROM opcoes_do_ativo
        WHERE parent_symbol = %s
        ORDER BY due_date
    """
    conn = conectar()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (ticker.upper().strip(),))
            return [r[0] for r in cur.fetchall()]
    finally:
        try: conn.close()
        except Exception: pass
