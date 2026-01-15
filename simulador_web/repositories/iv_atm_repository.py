from simulador_web.models import IvAtmHistorico


def get_iv_atm_historico_por_pregoes(
    ticker: str,
    limit: int = 60,
) -> list[dict]:
    """
    Retorna os últimos N pregões de IV ATM para um ticker.

    - Ordenação final: ascendente por data
    - Nenhum cálculo ou decisão aqui
    """

    qs = (
        IvAtmHistorico.objects
        .filter(ticker=ticker.upper())
        .order_by("-trade_date")[:limit]
    )

    # Reordenar para ascendente
    registros = list(qs)[::-1]

    return [
        {
            "trade_date": r.trade_date,
            "spot_price": r.spot_price,
            "iv_atm_mean": r.iv_atm_mean,
        }
        for r in registros
    ]



def get_iv_atm_por_data(
    ticker: str,
    ref_date,
    modo: str = "EXATA",  # EXATA | ANTERIOR | POSTERIOR
):
    qs = IvAtmHistorico.objects.filter(ticker=ticker.upper())

    if modo == "EXATA":
        r = qs.filter(trade_date=ref_date).first()

    elif modo == "ANTERIOR":
        r = (
            qs.filter(trade_date__lt=ref_date)
            .order_by("-trade_date")
            .first()
        )

    elif modo == "POSTERIOR":
        r = (
            qs.filter(trade_date__gt=ref_date)
            .order_by("trade_date")
            .first()
        )

    else:
        raise ValueError(f"Modo inválido: {modo}")

    return r.iv_atm_mean if r else None
