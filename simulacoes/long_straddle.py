from typing import Dict, Any, List
from math import isclose
from viz.payoff import plotar_payoff


__all__ = ["simular_long_straddle", "calcular_payoff_long_straddle"]

# --------- helpers internos ---------
def _to_float(v, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (ValueError, TypeError):
        return default

def _to_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (ValueError, TypeError):
        return default

def _preco_compra_premio(leg: Dict[str, Any]) -> float:
    """
    Para quem COMPRA a opção, use o ASK quando existir; senão, caia para last/close/bid.
    """
    bid = _to_float(leg.get("bid"))
    ask = _to_float(leg.get("ask"))
    last = _to_float(leg.get("last"))
    close = _to_float(leg.get("close"))

    if ask > 0:
        return ask
    if last > 0:
        return last
    if close > 0:
        return close
    if bid > 0:
        return bid
    return 0.0

def _gerar_malha_precos(centro: float, n_pontos: int = 101, largura: float = 0.4) -> List[float]:
    """
    Gera preços de (1-largura)*centro até (1+largura)*centro.
    Ex.: largura=0.4 → 60% a 140% do centro, 101 pontos.
    """
    if centro <= 0:
        centro = 10.0  # fallback seguro
    p_min = max(0.0, centro * (1 - largura))
    p_max = centro * (1 + largura)
    passo = (p_max - p_min) / (n_pontos - 1)
    return [round(p_min + i * passo, 2) for i in range(n_pontos)]

# --------- API pública ---------
# simulacoes/long_straddle.py (apenas trechos relevantes)

def simular_long_straddle(dados_call: Dict[str, Any], dados_put: Dict[str, Any], *, renderizar: bool = True) -> Dict[str, Any]:
    # --- extrair com defaults seguros ---
    symbol_call = dados_call.get("symbol", "CALL")
    symbol_put  = dados_put.get("symbol", "PUT")

    strike_call = _to_float(dados_call.get("strike"))
    strike_put  = _to_float(dados_put.get("strike"))

    premio_call = _preco_compra_premio(dados_call)
    premio_put  = _preco_compra_premio(dados_put)

    spot        = _to_float(dados_call.get("spot_price") or dados_put.get("spot_price"))
    contract_size = _to_int(dados_call.get("contract_size") or dados_put.get("contract_size"), 100) or 100
    vencimento  = dados_call.get("due_date") or dados_put.get("due_date") or ""

    # --- estratégia (sempre definida) ---
    is_straddle = (strike_call > 0 and strike_put > 0 and isclose(strike_call, strike_put, abs_tol=1e-6))
    estrategia  = "Long Straddle" if is_straddle else "Long Strangle"

    # --- custos e BE ---
    custo_total = (premio_call + premio_put) * contract_size
    be_inferior = round(strike_put  - (premio_call + premio_put), 2)
    be_superior = round(strike_call + (premio_call + premio_put), 2)

    # --- malha de preços ---
    if strike_call > 0 and strike_put > 0:
        strike_medio = (strike_call + strike_put) / 2
    else:
        strike_medio = 0.0
    centro = spot or strike_medio or strike_call or strike_put or 10.0
    precos: List[float] = _gerar_malha_precos(centro)

    # --- payoff ---
    resultados: List[float] = []
    for px in precos:
        lucro_call = max(0.0, px - strike_call) * contract_size
        lucro_put  = max(0.0, strike_put - px) * contract_size
        resultados.append(lucro_call + lucro_put - custo_total)

    # --- plotar só quando pedido (ex.: CLI). No Flet passe renderizar=False ---
    if renderizar:
        try:
            plotar_payoff(
                precos,
                resultados,
                spot,
                be_inferior,
                be_superior,
                symbol_call,
                symbol_put,
                vencimento,
                estrategia_nome=estrategia,
                mostrar=True  # abre janela apenas no terminal/CLI
            )
        except Exception as e:
            print("⚠️ Erro ao plotar payoff:", e)

    return {
        "estrategia": estrategia,
        "strike_call": strike_call,
        "strike_put": strike_put,
        "premio_call": premio_call,
        "premio_put": premio_put,
        "contract_size": contract_size,
        "custo_total": custo_total,
        "be_down": be_inferior,
        "be_up": be_superior,
        "spot": spot,
        "vencimento": vencimento,
        "precos": precos,
        "payoff": resultados,
    }
def calcular_payoff_long_straddle(
    precos_ativos: List[float],
    strike_call: float,
    strike_put: float,
    premio_call: float,
    premio_put: float,
    lote: int = 100
) -> List[float]:
    """
    Calcula apenas o vetor de payoff (sem plotar), útil para testes.
    Aceita strikes diferentes (strangle).
    """
    custo_total = (premio_call + premio_put) * lote
    resultado: List[float] = []
    for px in precos_ativos:
        lucro_call = max(px - strike_call, 0.0) * lote
        lucro_put  = max(strike_put - px, 0.0) * lote
        resultado.append(lucro_call + lucro_put - custo_total)
    return resultado
