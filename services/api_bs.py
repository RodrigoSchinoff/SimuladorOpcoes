# services/oplab_bs.py
import os
import requests

BASE_URL = "https://api.oplab.com.br/v3/market/options/bs"

def _get_headers():
    # Prioriza token do .env; se não houver, usa o HEADERS já usado pela sua services/api.py
    tok = os.getenv("OPLAB_TOKEN") or os.getenv("OPLAB_ACCESS_TOKEN")
    if tok:
        return {"Access-Token": tok}
    try:
        from services.api import HEADERS
        if "Access-Token" in HEADERS:
            return HEADERS
    except Exception:
        pass
    raise RuntimeError("Defina OPLAB_TOKEN (ou configure services.api.HEADERS).")

def bs_greeks(
    *, symbol: str, kind: str, spotprice: float, strike: float,
    premium: float, dtm: int, vol: float, due_date: str,
    irate: float = 0.0, amount: int = 100, timeout: int = 8
) -> dict:
    params = {
        "symbol": symbol,
        "irate": irate,
        "type": kind,           # "CALL" | "PUT"
        "spotprice": spotprice,
        "strike": strike,
        "premium": premium,
        "dtm": dtm,
        "vol": vol or 0,
        "duedate": due_date,
        "amount": amount,
    }
    r = requests.get(BASE_URL, params=params, headers=_get_headers(), timeout=timeout or 3)
    r.raise_for_status()
    return r.json()
