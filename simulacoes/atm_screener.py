# simulacoes/atm_screener.py
from typing import Dict, Any, List, Optional, Tuple
from datetime import date
import calendar
import time
import uuid
import concurrent.futures as cf
from math import log, sqrt, erf

from services.api import (
    buscar_opcoes_ativo,
    get_spot_ativo_oficial,
)
from simulacoes.utils import extrair_float as _f, preco_compra_premio as _prem
from services.api_bs import bs_greeks


LOG_DEBUG = False


# ------------------------------------------------------------
# 3ª sexta-feira oficial
# ------------------------------------------------------------
def _third_friday(d: date) -> date:
    c = calendar.Calendar(firstweekday=calendar.MONDAY)
    fridays = [dt for dt in c.itermonthdates(d.year, d.month)
               if dt.weekday() == 4 and dt.month == d.month]
    return fridays[2]


def _next_two_official_dues(today: date, opcoes: List[dict]) -> List[str]:
    """
    Retorna somente vencimentos oficiais (3ª sexta), garantindo que existam
    CALL e PUT para esse vencimento.
    """
    valid = []
    d = today

    # Gera 12 meses futuros → suficiente
    for _ in range(12):
        due = _third_friday(d).strftime("%Y-%m-%d")

        has_call = any(o for o in opcoes if o["due_date"][:10] == due
                       and (o.get("category") or "").upper().startswith("CALL"))

        has_put = any(o for o in opcoes if o["due_date"][:10] == due
                      and (o.get("category") or "").upper().startswith("PUT"))

        if has_call and has_put:
            valid.append(due)
            if len(valid) == 2:
                return valid

        # próximo mês
        y = d.year + (1 if d.month == 12 else 0)
        m = 1 if d.month == 12 else d.month + 1
        d = date(y, m, 1)

    return valid


# ------------------------------------------------------------
# Spot fallback
# ------------------------------------------------------------
def _spot_from_ops(ops: List[Dict[str, Any]], fallback: float = 0.0) -> float:
    for o in ops:
        sp = _f(o.get("spot_price"))
        if sp > 0:
            return sp
    ks = sorted({_f(o.get("strike")) for o in ops if _f(o.get("strike")) > 0})
    return ks[len(ks) // 2] if ks else fallback


# ------------------------------------------------------------
# Melhor perna
# ------------------------------------------------------------
def _choose_leg(legs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not legs:
        return None

    def score(o):
        ask = _f(o.get("ask")); bid = _f(o.get("bid"))
        oi = int(o.get("open_interest") or o.get("oi") or 0)
        vol = int(o.get("volume") or 0)
        spread = (ask - bid) if (ask > 0 and bid > 0) else 9e9
        return (0 if ask > 0 else (1 if bid > 0 else 2), -oi, -vol, spread)

    return sorted(legs, key=score)[0]


# ------------------------------------------------------------
# Seleção dos dois strikes ATM
# ------------------------------------------------------------
def _two_atm_strikes(ks: List[float], spot: float) -> List[float]:
    if not ks:
        return []
    ks = sorted(set([round(k, 2) for k in ks if k > 0]))
    below = [k for k in ks if k < spot]
    above = [k for k in ks if k > spot]

    k_down = max(below) if below else ks[0]
    k_up   = min(above) if above else ks[-1]

    if k_down == k_up:
        idx = ks.index(k_up)
        if idx > 0:
            k_down = ks[idx - 1]
        if idx < len(ks) - 1:
            k_up = ks[idx + 1]

    return [k_down, k_up]


# ------------------------------------------------------------
# Cálculo local de delta
# ------------------------------------------------------------
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _bs_delta_local(spot, strike, dias, vol, r, is_call):
    if spot <= 0 or strike <= 0 or vol <= 0 or dias <= 0:
        return None
    t = dias / 252.0
    d1 = (log(spot / strike) + (r + 0.5 * vol * vol) * t) / (vol * sqrt(t))
    nd1 = _norm_cdf(d1)
    return nd1 if is_call else (nd1 - 1.0)


def _iv(o: dict) -> float:
    for k in ("iv", "implied_vol", "implied_volatility", "sigma"):
        try:
            v = float(o.get(k))
            if v > 0:
                return v
        except:
            pass
    return 0.0


# ------------------------------------------------------------
# Monta ATM para um vencimento
# ------------------------------------------------------------
def _pairs_for_due(ticker: str, due_date: str, ops: List[dict], spot: float) -> List[dict]:
    sc_id = f"SC-{uuid.uuid4().hex[:6]}"
    t0 = time.perf_counter()

    calls = [o for o in ops if o["due_date"].startswith(due_date)
             and (o.get("category") or "").upper().startswith("CALL")]
    puts  = [o for o in ops if o["due_date"].startswith(due_date)
             and (o.get("category") or "").upper().startswith("PUT")]

    if not calls or not puts:
        return []

    strikes_call = {round(_f(o.get("strike")), 6) for o in calls if _f(o.get("strike")) > 0}
    strikes_put  = {round(_f(o.get("strike")), 6) for o in puts  if _f(o.get("strike")) > 0}
    strikes = sorted(strikes_call & strikes_put)
    if not strikes:
        return []

    ks = _two_atm_strikes([float(k) for k in strikes], spot)
    out = []

    for k in ks:
        cs = [o for o in calls if abs(_f(o.get("strike")) - k) < 1e-6]
        ps = [o for o in puts  if abs(_f(o.get("strike")) - k) < 1e-6]
        c = _choose_leg(cs)
        p = _choose_leg(ps)
        if not c or not p:
            continue

        prem_call = _prem(c)
        prem_put  = _prem(p)
        prem = prem_call + prem_put

        dias = int(c.get("days_to_maturity") or p.get("days_to_maturity") or 0)
        irate = 0.0
        amount = int((c.get("contract_size") or p.get("contract_size") or 100) or 100)

        vol_call = _iv(c)
        vol_put  = _iv(p)

        spot_c = round(spot, 2)

        def _delta_leg(o, kind, vol_in, prem_in):
            d_local = _bs_delta_local(spot, float(o.get("strike")), dias, vol_in, irate, kind == "CALL")
            if d_local is not None:
                return d_local

            params = dict(
                symbol=o.get("symbol"),
                due_date=due_date,
                kind=kind,
                spotprice=spot_c,
                strike=round(float(o.get("strike")), 2),
                premium=round(float(prem_in), 4),
                dtm=int(dias),
                vol=round(float(vol_in), 4),
                irate=irate,
                amount=amount,
            )

            try:
                resp = bs_greeks(**params, timeout=3)
                return float(resp.get("delta")) if resp.get("delta") is not None else None
            except:
                return None

        with cf.ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(_delta_leg, c, "CALL", vol_call, prem_call)
            f2 = ex.submit(_delta_leg, p, "PUT",  vol_put, prem_put)
            try:
                d_call = f1.result(timeout=5)
            except:
                d_call = None
            try:
                d_put = f2.result(timeout=5)
            except:
                d_put = None

        be_d = round(k - prem, 2)
        be_u = round(k + prem, 2)
        be_pct = round(min(abs(be_u - spot), abs(spot - be_d)) / spot * 100.0, 2) if spot > 0 else None

        out.append({
            "bucket": "ATM",
            "call": c["symbol"],
            "put":  p["symbol"],
            "due_date": due_date,
            "strike": float(k),
            "spot": spot,
            "premium_total": round(prem, 4),
            "premium_contrato": round(prem * amount, 2),
            "contract_size": amount,
            "be_down": be_d, "be_up": be_u, "be_pct": be_pct,
            "call_premio": round(prem_call, 4),
            "put_premio":  round(prem_put, 4),
            "call_delta": None if d_call is None else round(d_call, 4),
            "put_delta":  None if d_put  is None else round(d_put, 4),
        })

    return out


# ------------------------------------------------------------
# SCREENER PRINCIPAL (limpo, funcional)
# ------------------------------------------------------------
def screener_atm_dois_vencimentos(ticker: str, hoje: Optional[date] = None) -> Dict[str, List[Dict[str, Any]]]:
    hoje = hoje or date.today()
    scid = f"SC-{uuid.uuid4().hex[:6]}"

    ops = buscar_opcoes_ativo(ticker)
    if not ops:
        return {"atm": [], "due_dates": []}

    # Obtém vencimentos oficiais válidos
    dues = _next_two_official_dues(hoje, ops)
    if len(dues) < 2:
        return {"atm": [], "due_dates": dues}

    # Spot oficial → fallback para opções
    try:
        spot_oficial = float(get_spot_ativo_oficial(ticker) or 0.0)
    except:
        spot_oficial = 0.0
    spot = spot_oficial if spot_oficial > 0 else _spot_from_ops(ops)

    linhas = []
    for d in dues:
        pares = _pairs_for_due(ticker, d, ops, spot)
        linhas.extend(pares)

    linhas.sort(key=lambda r: (r["due_date"], abs(_f(r.get("strike")) - _f(r.get("spot")))))

    return {"atm": linhas, "due_dates": dues}
