# simulador_web/domain/iv_atm_decision.py

from __future__ import annotations

from datetime import date
from decimal import Decimal

from simulador_web.domain.iv_atm_atual import get_iv_atual_atm
from simulador_web.domain.iv_atm_metrics import calcular_metricas_iv_atm
from simulador_web.domain.iv_atm_classifier import classificar_ls_por_iv


def decidir_ls_por_iv(
    ticker: str,
    *,
    iv_override: float | Decimal | None = None,
    hoje: date | None = None,
    limit: int = 60,
) -> dict:
    """
    Decisão final do Módulo LS baseada em IV.

    Regras:
    - Se iv_override for informado -> usa IV manual.
    - Senão -> usa IV atual do mercado (get_iv_atual_atm).
    - Se não houver IV válida -> retorna 'Indisponível'.
    """

    ticker = (ticker or "").upper().strip()
    if not ticker:
        raise ValueError("ticker é obrigatório")

    # 1) Métricas históricas (sempre tentamos)
    metricas = calcular_metricas_iv_atm(ticker, limit=limit)

    # 2) Determinar IV atual
    origem_iv = "mercado"
    iv_atual = None

    if iv_override is not None:
        try:
            iv_atual = Decimal(str(float(iv_override)))
            origem_iv = "manual"
        except Exception:
            iv_atual = None
            origem_iv = "manual"
    else:
        atual = get_iv_atual_atm(ticker, hoje=hoje)
        iv_atual = atual.get("iv_mean")

    # 3) Sem IV -> Indisponível
    if iv_atual is None or iv_atual <= 0:
        return {
            "ticker": ticker,
            "iv_atual": iv_atual,
            "origem_iv": origem_iv,
            "metricas": metricas,
            "classificacao": "Indisponível",
            "motivo": "IV atual indisponível",
        }

    # 4) Classificar LS
    resultado = classificar_ls_por_iv(iv_atual, metricas)

    return {
        "ticker": ticker,
        "iv_atual": iv_atual,
        "origem_iv": origem_iv,
        "metricas": metricas,
        "classificacao": resultado.get("classificacao"),
        "motivo": resultado.get("motivo"),
    }
