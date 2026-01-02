# services/iv_historica.py

import requests
from collections import defaultdict
from datetime import datetime, date
from decimal import Decimal

from services.api import HEADERS

HIST_OPTIONS_URL = (
    "https://api.oplab.com.br/v3/market/historical/options/{spot}/{date_from}/{date_to}"
)


def _date_from_time(timestr: str) -> date:
    return datetime.fromisoformat(timestr.replace("Z", "")).date()


def _date_from_due_date(datestr: str) -> date:
    # "2024-12-20T00:00:00.000Z" -> date(2024, 12, 20)
    return datetime.fromisoformat(datestr.replace("Z", "")).date()


def buscar_iv_atm_historica(
    ticker: str,
    date_from: str,
    date_to: str,
):
    url = HIST_OPTIONS_URL.format(
        spot=ticker.upper(),
        date_from=date_from,
        date_to=date_to,
    )

    resp = requests.get(url, headers=HEADERS, timeout=6.0)
    if resp.status_code != 200:
        raise Exception(
            f"Erro ao buscar histórico de opções {ticker}: "
            f"{resp.status_code} - {resp.text}"
        )

    data = resp.json() or []

    by_date = defaultdict(list)
    for row in data:
        trade_date = _date_from_time(row["time"])
        by_date[trade_date].append(row)

    resultado = []

    for trade_date, rows in sorted(by_date.items()):
        atms = [r for r in rows if r.get("moneyness") == "ATM"]
        if not atms:
            continue

        calls = [r for r in atms if r.get("type") == "CALL"]
        puts = [r for r in atms if r.get("type") == "PUT"]
        if not calls or not puts:
            continue

        spot_price = None
        for r in atms:
            spot = r.get("spot") or {}
            for k in ("price", "last", "close", "spot"):
                try:
                    v = float(spot.get(k))
                    if v > 0:
                        spot_price = v
                        break
                except Exception:
                    pass
            if spot_price:
                break

        if not spot_price:
            continue

        def _best_by_premium(rows):
            return min(
                rows,
                key=lambda r: abs(
                    Decimal(str(r["premium"])) - Decimal(str(spot_price))
                )
            )

        call = _best_by_premium(calls)
        put = _best_by_premium(puts)

        iv_call = Decimal(str(call["volatility"]))
        iv_put = Decimal(str(put["volatility"]))
        iv_mean = (iv_call + iv_put) / Decimal("2")

        resultado.append({
            "ticker": ticker.upper(),
            "trade_date": trade_date,
            "spot_price": Decimal(str(spot_price)),

            "call": {
                "symbol": call["symbol"],
                "due_date": _date_from_due_date(call["due_date"]),
                "days_to_maturity": call["days_to_maturity"],
                "premium": Decimal(str(call["premium"])),
                "volatility": iv_call,
            },

            "put": {
                "symbol": put["symbol"],
                "due_date": _date_from_due_date(put["due_date"]),
                "days_to_maturity": put["days_to_maturity"],
                "premium": Decimal(str(put["premium"])),
                "volatility": iv_put,
            },

            "iv_atm_mean": iv_mean,
        })

    return resultado
