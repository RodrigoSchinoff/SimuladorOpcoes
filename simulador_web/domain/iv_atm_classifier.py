from decimal import Decimal


def classificar_ls_por_iv(
    iv_atual: Decimal,
    metricas: dict,
) -> dict:
    """
    Classifica o Long Straddle com base na IV atual
    em relação ao histórico (percentis).

    Regras:
    - Barato: iv_atual < p25
    - Justo:  p25 <= iv_atual <= p75
    - Caro:   iv_atual > p75
    """

    if iv_atual is None or metricas.get("count", 0) == 0:
        return {
            "classificacao": None,
            "motivo": "Dados insuficientes",
        }

    p25 = metricas["p25"]
    p75 = metricas["p75"]

    if iv_atual < p25:
        return {
            "classificacao": "Barato",
            "motivo": "IV atual abaixo do P25 histórico",
        }

    if iv_atual > p75:
        return {
            "classificacao": "Caro",
            "motivo": "IV atual acima do P75 histórico",
        }

    return {
        "classificacao": "Justo",
        "motivo": "IV atual dentro da faixa histórica",
    }
