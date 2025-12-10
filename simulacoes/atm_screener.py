# simulacoes/atm_screener.py
from typing import Dict, Any, List, Optional
from datetime import date
import calendar
import time
import uuid
import concurrent.futures as cf
from math import log, sqrt, erf

from services.api import buscar_opcoes_ativo, get_spot_ativo_oficial
from services.api_bs import bs_greeks
from simulacoes.utils import extrair_float as _f, preco_compra_premio as _prem


# ------------------------------------------------------------
# LOG HELPERS
# ------------------------------------------------------------
def _log(scid: str, msg: str):
    print(f"[{scid}] {msg}", flush=True)


# ------------------------------------------------------------
# Datas
# ------------------------------------------------------------
def _third_friday(d: date) -> date:
    c = calendar.Calendar(firstweekday=calendar.MONDAY)
    fridays = [dt for dt in c.itermonthdates(d.year, d.month)
               if dt.weekday() == 4 and dt.month == d.month]
    return fridays[2]


def _next_two_official_dues(today: date, ops: List[dict]) -> List[str]:
    valid = []
    d = today

    for _ in range(12):
        due = _third_friday(d).strftime("%Y-%m-%d")

        has_call = any(o for o in ops if o["due_date"][:10] == due and (o.get("category") or "").upper().startswith("CALL"))
        has_put  = any(o for o in ops if o["due_date"][:10] == due and (o.get("category") or "").upper().startswith("PUT"))

        if has_call and has_put:
            valid.append(due)
            if len(valid) == 2:
                return valid

        y = d.year + (1 if d.month == 12 else 0)
        m = 1 if d.month == 12 else d.month + 1
        d = date(y, m, 1)

    return valid


# ------------------------------------------------------------
# Spot fallback
# ------------------------------------------------------------
def _spot_from_ops(ops: List[Dict[str, Any]], fallback=0.0) -> float:
    for o in ops:
        sp = _f(o.get("spot_price"))
        if sp > 0:
            return sp
    ks = sorted({_f(o.get("strike")) for o in ops if _f(o.get("strike")) > 0})
    return ks[len(ks)//2] if ks else fallback


# ------------------------------------------------------------
# Melhor perna
# ------------------------------------------------------------
def _choose_leg(legs: List[Dict[str, Any]]):
    if not legs:
        return None

    def score(o):
        ask, bid = _f(o.get("ask")), _f(o.get("bid"))
        oi = int(o.get("open_interest") or 0)
        vol = int(o.get("volume") or 0)
        spread = (ask - bid) if (ask > 0 and bid > 0) else 9e9
        return (0 if ask > 0 else (1 if bid > 0 else 2), -oi, -vol, spread)

    return sorted(legs, key=score)[0]


# ------------------------------------------------------------
# Dois strikes ATM
# ------------------------------------------------------------
def _two_atm_strikes(ks, spot):
    ks = sorted(set(round(k, 2) for k in ks if k > 0))
    if not ks:
        return []

    below = [k for k in ks if k < spot]
    above = [k for k in ks if k > spot]

    k_down = max(below) if below else ks[0]
    k_up   = min(above) if above else ks[-1]

    if k_down == k_up:
        i = ks.index(k_up)
        if i > 0:
            k_down = ks[i - 1]
        if i < len(ks) - 1:
            k_up = ks[i + 1]

    return [k_down, k_up]


# ------------------------------------------------------------
# Cálculo BS local + fallback API
# ------------------------------------------------------------
def _norm_cdf(x): return 0.5 * (1 + erf(x / sqrt(2)))


def _bs_delta_local(spot, strike, dias, vol, r, call_flag):
    if spot <= 0 or strike <= 0 or vol <= 0 or dias <= 0:
        return None
    t = dias / 252
    d1 = (log(spot/strike) + (r + 0.5*vol*vol)*t)/(vol*sqrt(t))
    nd1 = _norm_cdf(d1)
    return nd1 if call_flag else nd1 - 1


def _iv(o):
    for k in ("iv", "implied_vol", "implied_volatility", "sigma"):
        try:
            v = float(o.get(k))
            if v > 0:
                return v
        except:
            pass
    return 0.0


# ------------------------------------------------------------
# Monta pares ATM
# ------------------------------------------------------------
def _pairs_for_due(scid, ticker, due_date, ops, spot):
    t0 = time.perf_counter()

    calls = [o for o in ops if o["due_date"].startswith(due_date) and (o.get("category") or "").upper().startswith("CALL")]
    puts  = [o for o in ops if o["due_date"].startswith(due_date) and (o.get("category") or "").upper().startswith("PUT")]

    strikes_call = {round(_f(o.get("strike")), 6) for o in calls}
    strikes_put  = {round(_f(o.get("strike")), 6) for o in puts}
    strikes = sorted(strikes_call & strikes_put)

    ks = _two_atm_strikes([float(k) for k in strikes], spot)
    out = []

    for k in ks:
        cs = [o for o in calls if abs(_f(o.get("strike")) - k) < 1e-6]
        ps = [o for o in puts  if abs(_f(o.get("strike")) - k) < 1e-6]

        c = _choose_leg(cs)
        p = _choose_leg(ps)
        if not c or not p:
            continue

        prem_c = _prem(c)
        prem_p = _prem(p)
        prem = prem_c + prem_p

        dias = int(c.get("days_to_maturity") or p.get("days_to_maturity") or 0)
        iv_c = _iv(c)
        iv_p = _iv(p)
        r = 0.0
        amount = int((c.get("contract_size") or 100) or 100)
        spot_r = round(spot, 2)

        # LOG para ver se local ou API
        def _delta_leg(o, is_call, vol, premio):
            # local first
            d_local = _bs_delta_local(spot_r, float(o["strike"]), dias, vol, r, is_call)
            if d_local is not None:
                return d_local, "LOCAL"

            # API fallback
            params = dict(
                symbol=o["symbol"], kind="CALL" if is_call else "PUT",
                spotprice=spot_r, strike=float(o["strike"]),
                premium=premio, dtm=dias, vol=vol, irate=0.0,
                due_date=due_date, amount=amount
            )
            try:
                resp = bs_greeks(**params, timeout=3)
                d = resp.get("delta")
                return (float(d) if d is not None else None), "API"
            except:
                return None, "MISS"

        with cf.ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(_delta_leg, c, True,  iv_c, prem_c)
            f2 = ex.submit(_delta_leg, p, False, iv_p, prem_p)
            d_call, src_c = f1.result()
            d_put,  src_p = f2.result()

        out.append({
            "bucket": "ATM",
            "call": c["symbol"],
            "put": p["symbol"],
            "due_date": due_date,
            "strike": float(k),
            "spot": spot,
            "premium_total": round(prem, 4),
            "contract_size": amount,
            "call_delta": None if d_call is None else round(d_call, 4),
            "put_delta":  None if d_put  is None else round(d_put, 4),
            "src_call": src_c,
            "src_put": src_p,
        })

    dt = time.perf_counter() - t0
    _log(scid, f"⏱ {ticker} {due_date} | linhas={len(out)} | {dt:.3f}s")
    return out


# ------------------------------------------------------------
# Screener principal
# ------------------------------------------------------------
def screener_atm_dois_vencimentos(ticker: str, hoje: Optional[date] = None) -> Dict[str, List[Dict[str, Any]]]:
    scid = f"SC-{uuid.uuid4().hex[:6]}"
    t0 = time.perf_counter()
    hoje = hoje or date.today()

    _log(scid, f"▶ START screener_atm_dois_vencimentos ticker={ticker}")

    ops = buscar_opcoes_ativo(ticker)
    if not ops:
        return {"atm": [], "due_dates": []}

    dues = _next_two_official_dues(hoje, ops)

    spot_oficial = float(get_spot_ativo_oficial(ticker) or 0.0)
    spot = spot_oficial if spot_oficial > 0 else _spot_from_ops(ops)

    _log(scid, f"💰 SPOT={spot} (oficial) | vencimentos={dues}")

    linhas = []
    for d in dues:
        linhas.extend(_pairs_for_due(scid, ticker, d, ops, spot))

    linhas.sort(key=lambda r: (r["due_date"], abs(_f(r["strike"]) - spot)))

    _log(scid, f"✔ END screener ticker={ticker} | linhas={len(linhas)} | {time.perf_counter()-t0:.3f}s")

    return {"atm": linhas, "due_dates": dues}
