from decimal import Decimal


def classificar_ls_por_iv(
    iv_atual: Decimal,
    metricas: dict,
) -> dict:
    """
    Classifica o Long Straddle com base na IV atual
    em relação ao histórico (percentis).

    IMPORTANTE:
    - Todas as comparações são feitas em DECIMAL (0–1)
    - Percentuais (ex: 27.5) são normalizados para 0.275

    Regras:
    - Barato: iv_atual < p25
    - Justo:  p25 <= iv_atual <= p75
    - Caro:   iv_atual > p75
    """

    if iv_atual is None or metricas.get("count", 0) == 0:
        return {
            "classificacao": "Indisponível",
            "motivo": "Dados insuficientes",
        }

    def _to_decimal(x):
        """
        Normaliza valores para Decimal em escala 0–1.
        Aceita:
        - 0.28  → 0.28
        - 28.0  → 0.28
        """
        try:
            x = Decimal(str(x))
        except Exception:
            return None

        # Se veio em percentual (> 1.5), converte para decimal
        if x > Decimal("1.5"):
            return x / Decimal("100")

        return x

    iv = _to_decimal(iv_atual)
    p25 = _to_decimal(metricas.get("p25"))
    p75 = _to_decimal(metricas.get("p75"))

    if iv is None or p25 is None or p75 is None:
        return {
            "classificacao": "Indisponível",
            "motivo": "Falha ao normalizar dados de IV",
        }

    if iv < p25:
        return {
            "classificacao": "Barato",
            "motivo": "IV atual abaixo do P25 histórico",
        }

    if iv > p75:
        return {
            "classificacao": "Caro",
            "motivo": "IV atual acima do P75 histórico",
        }

    return {
        "classificacao": "Justo",
        "motivo": "IV atual dentro da faixa histórica",
    }
