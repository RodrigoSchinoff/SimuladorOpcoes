# simulacoes/ls_screener.py
from typing import List, Dict, Any
from repositories.opcoes_repo import buscar_opcoes_por_ticker_vencimento

def _to_float(v, default: float = 0.0) -> float:
    try: return float(v)
    except (TypeError, ValueError): return default


def _premium(o: Dict[str, Any]) -> float:
    # custo para montar a posição (prioriza ASK; fallback BID, CLOSE, OPEN)
    for k in ("ask", "bid", "close", "open"):
        try:
            v = float(o.get(k))
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    return 0.0


def _spot(call: Dict[str, Any], put: Dict[str, Any]) -> float:
    return _to_float(call.get("spot_price") or put.get("spot_price"))

def _be_points(k_call: float, k_put: float, prem_tot: float) -> tuple[float, float]:
    return round(k_put - prem_tot, 2), round(k_call + prem_tot, 2)

def _be_pct(spot: float, be_down: float, be_up: float) -> float | None:
    if spot <= 0: return None
    desloc = min(abs(be_up - spot), abs(spot - be_down))
    return round(desloc / spot * 100.0, 2)

def _pair_straddles(calls: List[Dict[str, Any]], puts: List[Dict[str, Any]]):
    map_calls: dict[float, Dict[str, Any]] = {}
    for c in calls:
        k = _to_float(c.get("strike"))
        if k not in map_calls:
            map_calls[k] = c
    pairs = []
    for p in puts:
        k = _to_float(p.get("strike"))
        c = map_calls.get(k)
        if c: pairs.append((c, p))
    return pairs

def screener_ls_por_ticker_vencimento(ticker: str, due_date: str) -> dict[str, List[Dict[str, Any]]]:
    ops = buscar_opcoes_por_ticker_vencimento(ticker, due_date)
    calls = [o for o in ops if (o.get("tipo") or "").upper().startswith("CALL")]
    puts  = [o for o in ops if (o.get("tipo") or "").upper().startswith("PUT")]
    pairs = _pair_straddles(calls, puts)

    resultados = []
    for c, p in pairs:
        k_call = _to_float(c.get("strike"))
        k_put  = _to_float(p.get("strike"))
        prem   = _premium(c) + _premium(p)
        spot   = _spot(c, p)
        be_down, be_up = _be_points(k_call, k_put, prem)
        bepct = _be_pct(spot, be_down, be_up)
        if bepct is None: continue

        csz = int((c.get("contract_size") or p.get("contract_size") or 100) or 100)

        resultados.append({
            "call": c.get("symbol"),
            "put": p.get("symbol"),
            "due_date": due_date,
            "strike": k_call,
            "premium_total": round(prem, 4),  # prêmio por ação (CALL+PUT)
            "premium_contrato": round(prem * csz, 2),  # prêmio x contrato
            "contract_size": csz,
            "be_down": be_down,
            "be_up": be_up,
            "be_pct": bepct,
            "spot": spot,
        })

    buckets = {"lt_3": [], "btw_3_5": [], "gt_5": []}
    for r in resultados:
        if r["be_pct"] <= 3.00: buckets["lt_3"].append(r)
        elif r["be_pct"] <= 5.00: buckets["btw_3_5"].append(r)
        else: buckets["gt_5"].append(r)

    for k in buckets: buckets[k].sort(key=lambda x: x["be_pct"])
    return buckets
