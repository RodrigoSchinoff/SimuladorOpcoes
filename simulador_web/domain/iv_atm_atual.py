# simulador_web/domain/iv_atm_atual.py

from __future__ import annotations

from datetime import date
from decimal import Decimal

from simulacoes.atm_screener import screener_atm_dois_vencimentos
from simulacoes.black_scholes import implied_vol


def get_iv_atual_atm(
    ticker: str,
    *,
    hoje: date | None = None,
    pregoes_window: int = 60,  # reservado para uso futuro
) -> dict:
    """
    Calcula IV atual ATM do ativo (tempo real), inferida localmente via implied_vol().

    - Se 'hoje' for None -> usa date.today() (comportamento atual, inalterado)
    - Se 'hoje' for informado -> permite replay/teste histórico
    """

    ticker = (ticker or "").upper().strip()
    if not ticker:
        raise ValueError("ticker é obrigatório")

    r = screener_atm_dois_vencimentos(ticker, hoje=hoje)
    linhas = (r or {}).get("atm") or []
    if not linhas:
        return {
            "ticker": ticker,
            "trade_date": hoje or date.today(),
            "spot": None,
            "due_date": None,
            "strike": None,
            "days_to_maturity": None,
            "iv_call": None,
            "iv_put": None,
            "iv_mean": None,
            "motivo": "Sem linhas ATM no screener",
        }

    # Primeira linha já vem ordenada: vencimento mais próximo + strike mais próximo do spot
    ref = linhas[0]

    spot = float(ref.get("spot") or 0.0)
    strike = float(ref.get("strike") or 0.0)
    dtm = int(ref.get("days_to_maturity") or 0)

    premio_call = float(ref.get("call_premio") or 0.0)
    premio_put = float(ref.get("put_premio") or 0.0)

    due_date = (ref.get("due_date") or "").strip()

    if spot <= 0 or strike <= 0 or dtm <= 0:
        return {
            "ticker": ticker,
            "trade_date": hoje or date.today(),
            "spot": Decimal(str(spot)) if spot else None,
            "due_date": due_date or None,
            "strike": Decimal(str(strike)) if strike else None,
            "days_to_maturity": dtm or None,
            "iv_call": None,
            "iv_put": None,
            "iv_mean": None,
            "motivo": "Dados insuficientes para implied_vol (spot/strike/dtm)",
        }

    # Convenção do projeto
    T = dtm / 252.0
    r_rate = 0.0
    q_div = 0.0

    iv_call = implied_vol(premio_call, spot, strike, r_rate, q_div, T, "CALL")
    iv_put = implied_vol(premio_put, spot, strike, r_rate, q_div, T, "PUT")

    def _dec(x):
        if x is None:
            return None
        try:
            return Decimal(str(float(x)))
        except Exception:
            return None

    iv_call_d = _dec(iv_call)
    iv_put_d = _dec(iv_put)

    iv_mean = None
    if iv_call_d is not None and iv_put_d is not None:
        iv_mean = (iv_call_d + iv_put_d) / Decimal("2")

    return {
        "ticker": ticker,
        "trade_date": hoje or date.today(),
        "spot": _dec(spot),
        "due_date": due_date or None,
        "strike": _dec(strike),
        "days_to_maturity": dtm,
        "call_symbol": ref.get("call"),
        "put_symbol": ref.get("put"),
        "call_premio": _dec(premio_call),
        "put_premio": _dec(premio_put),
        "iv_call": iv_call_d,
        "iv_put": iv_put_d,
        "iv_mean": iv_mean,
        "motivo": None,
    }
