# simulacoes/atm_screener.py
from typing import Dict, Any, List, Optional, Tuple
from datetime import date
import calendar

from repositories.opcoes_repo import buscar_opcoes_por_ticker_vencimento
from simulacoes.utils import extrair_float as _f, preco_compra_premio as _prem
from services.api import get_spot_ativo_oficial  # <- usa a função do módulo services.api


def _third_friday(d: date) -> date:
    c = calendar.Calendar(firstweekday=calendar.MONDAY)
    fridays = [dt for dt in c.itermonthdates(d.year, d.month) if dt.weekday() == 4 and dt.month == d.month]
    return fridays[2]


def _next_two_third_fridays(today: date) -> Tuple[date, date]:
    tf = _third_friday(today)
    if tf >= today:
        y, m = (today.year + (1 if today.month == 12 else 0), 1 if today.month == 12 else today.month + 1)
        return tf, _third_friday(date(y, m, 1))
    y, m = (today.year + (1 if today.month == 12 else 0), 1 if today.month == 12 else today.month + 1)
    first = _third_friday(date(y, m, 1))
    y2, m2 = (first.year + (1 if first.month == 12 else 0), 1 if first.month == 12 else first.month + 1)
    return first, _third_friday(date(y2, m2, 1))


def _spot_from_ops(ops: List[Dict[str, Any]], fallback: float = 0.0) -> float:
    """
    Fallback de spot: tenta usar campo spot_price; se não, mediana dos strikes.
    Usado apenas quando não conseguir pegar o spot oficial.
    """
    for o in ops:
        sp = _f(o.get("spot_price"))
        if sp > 0:
            return sp
    ks = sorted({_f(o.get("strike")) for o in ops if _f(o.get("strike")) > 0})
    return ks[len(ks) // 2] if ks else fallback


def _choose_leg(legs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not legs:
        return None

    def score(o: Dict[str, Any]):
        ask = _f(o.get("ask")); bid = _f(o.get("bid"))
        oi = int(o.get("open_interest") or o.get("oi") or 0)
        vol = int(o.get("volume") or 0)
        spread = (ask - bid) if (ask > 0 and bid > 0) else 9e9
        return (0 if ask > 0 else (1 if bid > 0 else 2), -oi, -vol, spread)

    return sorted(legs, key=score)[0]


def _two_atm_strikes(ks: List[float], spot: float) -> List[float]:
    """
    Regra:
    - sempre 1 strike abaixo do spot
    - sempre 1 strike acima do spot
    - se não houver abaixo, usa o menor strike
    - se não houver acima, usa o maior strike
    """
    if not ks:
        return []

    ks = sorted(set([round(k, 2) for k in ks if k > 0]))

    # abaixo = estritamente menores que o spot
    below = [k for k in ks if k < spot]
    # acima  = estritamente maiores que o spot
    above = [k for k in ks if k > spot]

    # 1) garantir strike abaixo
    if below:
        k_down = max(below)
    else:
        # se não tiver nada abaixo, pega o menor disponível
        k_down = ks[0]

    # 2) garantir strike acima
    if above:
        k_up = min(above)
    else:
        # se não tiver nada acima, pega o maior disponível
        k_up = ks[-1]

    # 3) se por acaso ainda forem iguais, ajusta pros vizinhos
    if k_down == k_up:
        idx = ks.index(k_up)
        if idx > 0:
            k_down = ks[idx - 1]
        if idx < len(ks) - 1:
            k_up = ks[idx + 1]

    return [k_down, k_up]


def _pairs_for_due(ticker: str, due_date: str) -> List[Dict[str, Any]]:
    # --- DEBUG ---
    import time, uuid
    sc_id = f"SC-{uuid.uuid4().hex[:6]}"
    t0 = time.perf_counter()
    print(f"[{sc_id}] START _pairs_for_due ticker={ticker} due={due_date}", flush=True)
    # --- DEBUG ---

    tq = time.perf_counter()
    print(f"[{sc_id}] Q_BEFORE due={due_date}", flush=True)
    ops = buscar_opcoes_por_ticker_vencimento(ticker, due_date)
    print(f"[{sc_id}] Q_AFTER due={due_date} dt={time.perf_counter()-tq:.3f}s rows={len(ops or [])}", flush=True)

    if not ops:
        print(f"[{sc_id}] END _pairs_for_due due={due_date} total={time.perf_counter()-t0:.3f}s (no ops)", flush=True)
        return []

    # mesmo padrão já usado no ls_screener: campo normalizado "tipo"
    tc = time.perf_counter()
    calls = [o for o in ops if (o.get("tipo") or "").upper().startswith("CALL")]
    puts  = [o for o in ops if (o.get("tipo") or "").upper().startswith("PUT")]

    # 1) tenta usar o SPOT OFICIAL (Oplab) via services.api
    try:
        spot_oficial = float(get_spot_ativo_oficial(ticker) or 0.0)
    except Exception:
        spot_oficial = 0.0

    # 2) fallback: spot derivado das opções
    if spot_oficial > 0:
        spot = spot_oficial
    else:
        spot = _spot_from_ops(ops)

    strikes_call = {round(_f(o.get("strike")), 6) for o in calls if _f(o.get("strike")) > 0}
    strikes_put  = {round(_f(o.get("strike")), 6) for o in puts  if _f(o.get("strike")) > 0}
    strikes = sorted(strikes_call & strikes_put)
    print(
        f"[{sc_id}] PREP due={due_date} dt={time.perf_counter()-tc:.3f}s "
        f"calls={len(calls)} puts={len(puts)} strikes={len(strikes)} "
        f"spot={spot} spot_oficial={spot_oficial}",
        flush=True,
    )

    if not strikes:
        print(f"[{sc_id}] END _pairs_for_due due={due_date} total={time.perf_counter()-t0:.3f}s (no strikes)", flush=True)
        return []

    ks = _two_atm_strikes([float(k) for k in strikes], spot)
    out: List[Dict[str, Any]] = []

    tcalc = time.perf_counter()
    for k in ks:
        cs = [o for o in calls if abs(_f(o.get("strike")) - k) < 1e-6]
        ps = [o for o in puts  if abs(_f(o.get("strike")) - k) < 1e-6]
        c = _choose_leg(cs); p = _choose_leg(ps)
        if not c or not p:
            continue

        prem_call = _prem(c)
        prem_put  = _prem(p)
        prem = prem_call + prem_put

        dias   = int(c.get("days_to_maturity") or p.get("days_to_maturity") or 0)
        irate  = 0.0
        amount = int((c.get("contract_size") or p.get("contract_size") or 100) or 100)

        # --- BLOCO DELTA (local + cache + API) ---
        import concurrent.futures as cf
        from services.api_bs import bs_greeks
        from repositories.bs_repo import get_cached_bs, upsert_bs
        from math import log, sqrt, erf

        def _norm_cdf(x: float) -> float:
            return 0.5 * (1.0 + erf(x / sqrt(2.0)))

        def _bs_delta_local(spot_, strike_, dias_, vol_, r_, is_call):
            if spot_ <= 0 or strike_ <= 0 or vol_ <= 0 or dias_ <= 0:
                return None
            t = dias_ / 252.0
            d1 = (log(spot_ / strike_) + (r_ + 0.5 * vol_ * vol_) * t) / (vol_ * sqrt(t))
            nd1 = _norm_cdf(d1)
            return nd1 if is_call else (nd1 - 1.0)

        def _iv(o: dict) -> float:
            for k_iv in ("iv", "implied_vol", "implied_volatility", "sigma"):
                try:
                    v = float(o.get(k_iv))
                    if v > 0:
                        return v
                except Exception:
                    pass
            return 0.0

        vol_call = _iv(c)
        vol_put  = _iv(p)

        def _canon(v, nd):
            try:
                return round(float(v), nd)
            except Exception:
                return None

        spot_c = _canon(spot, 2)

        def _delta_for_leg(o: dict, kind: str, vol_in: float, prem_in: float):
            # 0) tentativa local (instantânea, se tiver IV)
            d_local = _bs_delta_local(
                spot,
                float(o.get("strike") or 0),
                dias,
                vol_in,
                irate,
                kind == "CALL",
            )
            if d_local is not None:
                try:
                    if LOG_DEBUG:
                        print(f"[{sc_id}] LOCAL_DELTA kind={kind} strike={o.get('strike')}", flush=True)
                except Exception:
                    pass
                return d_local

            # 1) cache + API (sempre que o local não resolver)
            params = dict(
                symbol=o.get("symbol"),
                due_date=due_date,
                kind=kind,
                spotprice=spot_c,
                strike=_canon(o.get("strike"), 2),
                premium=_canon(prem_in, 4),
                dtm=int(dias),
                vol=_canon(vol_in, 4),
                irate=irate,
                amount=amount,
            )

            # cache
            try:
                cached = get_cached_bs(**params, ttl_minutes=60)
                if cached and cached.get("delta") is not None:
                    return float(cached["delta"])
            except Exception:
                pass

            # API
            try:
                resp = bs_greeks(**params, timeout=3)
                resp["spotprice"] = params["spotprice"]
                resp["strike"]    = params["strike"]
                resp["premium"]   = params["premium"]
                resp["vol"]       = params["vol"]
                resp["dtm"]       = params["dtm"]

                upsert_bs(
                    resp=resp,
                    symbol=params["symbol"], due_date=params["due_date"], kind=params["kind"],
                    irate=params["irate"], premium=params["premium"], dtm=params["dtm"],
                    vol=params["vol"], amount=params["amount"],
                )
                return float(resp.get("delta")) if resp.get("delta") is not None else None
            except Exception:
                return None
        # --- FIM BLOCO DELTA ---

        with cf.ThreadPoolExecutor(max_workers=2) as ex:
            f_c = ex.submit(_delta_for_leg, c, "CALL", vol_call, prem_call)
            f_p = ex.submit(_delta_for_leg, p, "PUT",  vol_put,  prem_put)
            try:
                d_call = f_c.result(timeout=5)
            except Exception:
                d_call = None
            try:
                d_put  = f_p.result(timeout=5)
            except Exception:
                d_put  = None

        csz = amount
        be_d = round(k - prem, 2)
        be_u = round(k + prem, 2)
        be_pct = round(min(abs(be_u - spot), abs(spot - be_d)) / spot * 100.0, 2) if spot > 0 else None

        out.append({
            "bucket": "ATM",
            "call": c.get("symbol"),
            "put":  p.get("symbol"),
            "due_date": due_date,
            "strike": float(k),
            "spot": spot,
            "premium_total": round(prem, 4),
            "premium_contrato": round(prem * csz, 2),
            "contract_size": csz,
            "be_down": be_d, "be_up": be_u, "be_pct": be_pct,
            "call_premio": round(prem_call, 4),
            "put_premio":  round(prem_put,  4),
            "call_delta":  None if d_call is None else round(d_call, 4),
            "put_delta":   None if d_put  is None else round(d_put,  4),
        })

    print(f"[{sc_id}] CALC due={due_date} dt={time.perf_counter()-tcalc:.3f}s", flush=True)
    print(f"[{sc_id}] END _pairs_for_due due={due_date} total={time.perf_counter()-t0:.3f}s out={len(out)}", flush=True)
    return out


def screener_atm_dois_vencimentos(ticker: str, hoje: Optional[date] = None) -> Dict[str, List[Dict[str, Any]]]:
    # --- DEBUG ---
    import time, uuid
    sc_id_all = f"SC-{uuid.uuid4().hex[:6]}"
    t0 = time.perf_counter()
    # --- DEBUG ---

    """
    Retorna somente as 2 linhas ATM (1 strike abaixo e 1 acima) para cada
    um dos 2 próximos vencimentos (terceira sexta-feira).
    Saída: {'atm': [...], 'due_dates': [v1, v2]}
    """
    hoje = hoje or date.today()
    v1, v2 = _next_two_third_fridays(hoje)
    ds = [v1.strftime("%Y-%m-%d"), v2.strftime("%Y-%m-%d")]

    print(f"[{sc_id_all}] START screener_atm_dois_vencimentos ticker={ticker} ds={ds}", flush=True)

    linhas: List[Dict[str, Any]] = []
    for d in ds:
        tp = time.perf_counter()
        pares = _pairs_for_due(ticker, d)
        print(f"[{sc_id_all}] DUE_AGG due={d} dt={time.perf_counter()-tp:.3f}s pairs={len(pares)}", flush=True)
        linhas.extend(pares)

    ts = time.perf_counter()
    linhas.sort(key=lambda r: (r["due_date"], abs(_f(r.get("strike")) - _f(r.get("spot")))))
    print(f"[{sc_id_all}] SORT dt={time.perf_counter()-ts:.3f}s", flush=True)

    print(f"[{sc_id_all}] END screener total={time.perf_counter()-t0:.3f}s linhas={len(linhas)}", flush=True)
    return {"atm": linhas, "due_dates": ds}
