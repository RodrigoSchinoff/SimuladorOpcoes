from typing import Dict, Any, List

def extrair_float(v, default=0.0):
    try: return float(v) if v is not None else default
    except (ValueError, TypeError): return default

def preco_compra_premio(leg: Dict[str, Any]) -> float:
    bid = extrair_float(leg.get("bid"))
    ask = extrair_float(leg.get("ask"))
    last = extrair_float(leg.get("last"))
    close = extrair_float(leg.get("close"))
    if ask > 0: return ask
    if bid > 0 and ask > 0: return (bid + ask) / 2
    if last > 0: return last
    if close > 0: return close
    if bid > 0: return bid
    return 0.0

def gerar_malha_precos(centro: float, n_pontos: int = 101, largura: float = 0.4) -> List[float]:
    if centro <= 0: centro = 10.0
    pmin = max(0.0, centro * (1 - largura))
    pmax = centro * (1 + largura)
    passo = (pmax - pmin) / (n_pontos - 1)
    return [round(pmin + i*passo, 2) for i in range(n_pontos)]
