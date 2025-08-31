# repositories/bs_repo.py
from typing import Optional, Dict, Any
import psycopg2.extras
from db.conexao import conectar

TABELA = "opcoes_bs"

def get_cached_bs(
    *, symbol: str, due_date: str, kind: str, spotprice: float, strike: float,
    premium: float, dtm: int, vol: float, irate: float, amount: int,
    ttl_minutes: int = 60
) -> Optional[Dict[str, Any]]:
    sql = f"""
        SELECT moneyness, price, delta, gamma, vega, theta, rho, volatility, poe,
               spotprice, strike, margin
        FROM {TABELA}
        WHERE symbol=%s AND due_date=%s AND type=%s
          AND spotprice=%s AND strike=%s AND premium=%s AND dtm=%s AND vol=%s AND irate=%s AND amount=%s
          AND created_at > NOW() - (%s || ' minutes')::interval
        LIMIT 1
    """
    conn = conectar()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (symbol, due_date, kind, spotprice, strike, premium, dtm, vol, irate, amount, ttl_minutes))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        try: conn.close()
        except Exception: pass

def upsert_bs(
    *, symbol: str, due_date: str, kind: str, irate: float, premium: float,
    dtm: int, vol: float, amount: int, resp: Dict[str, Any]
) -> None:
    sql = f"""
        INSERT INTO {TABELA} (
            symbol, type, due_date, moneyness, price, delta, gamma, vega, theta, rho, volatility, poe,
            spotprice, strike, margin, irate, premium, dtm, vol, amount, created_at
        )
        VALUES (
            %(symbol)s, %(type)s, %(due_date)s, %(moneyness)s, %(price)s, %(delta)s, %(gamma)s, %(vega)s, %(theta)s, %(rho)s, %(volatility)s, %(poe)s,
            %(spotprice)s, %(strike)s, %(margin)s, %(irate)s, %(premium)s, %(dtm)s, %(vol)s, %(amount)s, NOW()
        )
        ON CONFLICT (symbol, due_date, type, spotprice, strike, premium, dtm, vol, irate, amount)
        DO UPDATE SET
            moneyness = EXCLUDED.moneyness,
            price     = EXCLUDED.price,
            delta     = EXCLUDED.delta,
            gamma     = EXCLUDED.gamma,
            vega      = EXCLUDED.vega,
            theta     = EXCLUDED.theta,
            rho       = EXCLUDED.rho,
            volatility= EXCLUDED.volatility,
            poe       = EXCLUDED.poe,
            margin    = EXCLUDED.margin,
            created_at= NOW()
    """
    data = dict(resp)
    data.update({
        "symbol": symbol, "type": kind, "due_date": due_date,
        "irate": irate, "premium": premium, "dtm": dtm, "vol": vol, "amount": amount
    })
    conn = conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, data)
            conn.commit()
    finally:
        try: conn.close()
        except Exception: pass
