from decimal import Decimal
from statistics import mean

from simulador_web.repositories.iv_atm_repository import (
    get_iv_atm_historico_por_pregoes
)


def calcular_metricas_iv_atm(
    ticker: str,
    limit: int = 60,
) -> dict:
    """
    Calcula métricas estatísticas da IV ATM histórica.

    Retorna:
    - count
    - iv_mean
    - iv_min
    - iv_max
    - p25
    - p50 (mediana)
    - p75
    """

    historico = get_iv_atm_historico_por_pregoes(
        ticker=ticker,
        limit=limit,
    )

    if not historico:
        return {
            "count": 0,
            "iv_mean": None,
            "iv_min": None,
            "iv_max": None,
            "p25": None,
            "p50": None,
            "p75": None,
        }

    ivs = [Decimal(r["iv_atm_mean"]) for r in historico]
    ivs_sorted = sorted(ivs)
    n = len(ivs_sorted)

    def _percentil(p):
        if n == 1:
            return ivs_sorted[0]
        k = (n - 1) * p
        f = int(k)
        c = min(f + 1, n - 1)
        if f == c:
            return ivs_sorted[f]
        return ivs_sorted[f] + (ivs_sorted[c] - ivs_sorted[f]) * Decimal(k - f)

    return {
        "count": n,
        "iv_mean": mean(ivs_sorted),
        "iv_min": ivs_sorted[0],
        "iv_max": ivs_sorted[-1],
        "p25": _percentil(Decimal("0.25")),
        "p50": _percentil(Decimal("0.50")),
        "p75": _percentil(Decimal("0.75")),
    }
