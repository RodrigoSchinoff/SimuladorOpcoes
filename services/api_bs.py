# services/api_bs.py
import os
import requests

BASE_URL = "https://api.oplab.com.br/v3/market/options/bs"


def _get_headers():
    """
    Usa sempre o token da Oplab vindo do .env (OPLAB_TOKEN).
    """
    tok = os.getenv("OPLAB_TOKEN")
    if tok:
        return {"Access-Token": tok}
    raise RuntimeError("Defina OPLAB_TOKEN no .env ou nas variáveis de ambiente.")


def bs_greeks(
    *,
    symbol: str,
    kind: str,
    spotprice: float,
    strike: float,
    premium: float,
    dtm: int,
    vol: float,
    due_date: str,
    irate: float = 0.0,
    amount: int = 100,
    timeout: int = 8,
) -> dict:
    """
    Chamada direta da API Black-Scholes da Oplab.
    Todos os parâmetros obrigatórios estão aqui, seguindo a doc oficial.
    """
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
