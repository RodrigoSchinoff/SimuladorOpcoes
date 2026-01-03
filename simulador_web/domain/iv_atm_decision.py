from __future__ import annotations

from datetime import date
from decimal import Decimal

from simulador_web.domain.iv_atm_atual import get_iv_atual_atm
from simulador_web.domain.iv_atm_metrics import calcular_metricas_iv_atm
from simulador_web.domain.iv_atm_classifier import classificar_ls_por_iv


# =========================================================
# NÚCLEO DE DECISÃO (INDEPENDENTE DE VIEW / PLANO)
# =========================================================
def decidir_ls_por_iv(
    ticker: str,
    *,
    iv_override: float | Decimal | None = None,
    hoje: date | None = None,
    limit: int = 60,
) -> dict:
    """
    Decisão final do Módulo LS baseada em IV.
    Retorna SEMPRE um dict utilizável pela VIEW.

    Convenção:
    - Internamente: IV em decimal (ex.: 0.35)
    - Para UI: também enviamos campos *_pct em 0-100 (ex.: 35.0)
    """

    ticker = (ticker or "").upper().strip()
    if not ticker:
        raise ValueError("ticker é obrigatório")

    # 1) Métricas históricas (normalmente em decimal: 0.27 = 27%)
    metricas = calcular_metricas_iv_atm(ticker, limit=limit)

    p25 = metricas.get("p25")
    p50 = metricas.get("p50")
    p75 = metricas.get("p75")
    janela = metricas.get("window") or limit

    # 2) IV atual (decimal)
    origem_iv = "mercado"
    iv_atual = None

    if iv_override is not None:
        try:
            iv_atual = Decimal(str(float(iv_override)))
            origem_iv = "manual"
        except Exception:
            iv_atual = None
    else:
        atual = get_iv_atual_atm(ticker, hoje=hoje)
        iv_atual = atual.get("iv_mean") if atual else None

    # helpers p/ UI
    def _to_pct(x):
        """
        Normaliza para percentual (0-100).

        - Se vier em decimal (0.27) -> 27.0
        - Se já vier em % (27.0) -> 27.0
        """
        try:
            if x is None:
                return None
            xf = float(x)
            # auto-detect: valores <= 1.5 são decimais típicos (0-1)
            if xf <= 1.5:
                return xf * 100.0
            return xf
        except Exception:
            return None

    iv_baixa_pct = _to_pct(p25)
    iv_normal_pct = _to_pct(p50)
    iv_alta_pct = _to_pct(p75)

    # 3) Sem IV → indisponível
    if iv_atual is None or float(iv_atual) <= 0:
        return {
            "ticker": ticker,
            "origem_iv": origem_iv,
            "classificacao": "Indisponível",
            "motivo": "IV atual indisponível",
            "janela": janela,

            # UI (%)
            "iv_atual_pct": None,
            "iv_baixa_pct": iv_baixa_pct,
            "iv_normal_pct": iv_normal_pct,
            "iv_alta_pct": iv_alta_pct,
        }

    # 4) Classificação
    resultado = classificar_ls_por_iv(iv_atual, metricas)

    return {
        "ticker": ticker,
        "origem_iv": origem_iv,
        "classificacao": resultado.get("classificacao"),
        "motivo": resultado.get("motivo"),
        "janela": janela,

        # UI (%)
        "iv_atual_pct": _to_pct(iv_atual),
        "iv_baixa_pct": iv_baixa_pct,
        "iv_normal_pct": iv_normal_pct,
        "iv_alta_pct": iv_alta_pct,
    }


# =========================================================
# ADAPTER PARA VIEW (REQUEST / GET)
# =========================================================
def build_iv_decisao(request, ticker: str):
    """
    Adapter TEMPORÁRIO – EXECUTA SEMPRE.

    Entrada:
    - iv_override no GET pode ser:
      - "35"  (35%)
      - "0.35" (já decimal)
    """
    if not ticker:
        return None

    raw = (request.GET.get("iv_override") or "").strip()
    iv_override = None

    if raw:
        try:
            x = float(raw.replace(",", "."))
            # se vier 35 -> 0.35
            # se vier 0.35 -> mantém
            if x > 1.5:
                iv_override = x / 100.0
            else:
                iv_override = x
        except Exception:
            iv_override = None

    try:
        return decidir_ls_por_iv(
            ticker=ticker,
            iv_override=iv_override,
        )
    except Exception as e:
        return {
            "ticker": ticker,
            "classificacao": "Erro",
            "motivo": str(e),
            "janela": None,
            "iv_atual_pct": None,
            "iv_baixa_pct": None,
            "iv_normal_pct": None,
            "iv_alta_pct": None,
        }
