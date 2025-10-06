# simulacoes/black_scholes.py
import math

SQRT_2PI = math.sqrt(2.0 * math.pi)

def _N(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def _n(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT_2PI

def black_scholes(S: float, K: float, r: float, q: float, sigma: float, T: float, kind: str):
    if S <= 0 or K <= 0 or sigma <= 0 or T <= 0:
        return {"preco": 0.0, "delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta_ano": 0.0, "rho": 0.0, "d1": 0.0, "d2": 0.0}

    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    Nd1 = _N(d1); Nd2 = _N(d2)
    n_d1 = _n(d1)
    disc_r = math.exp(-r * T)
    disc_q = math.exp(-q * T)

    if kind.upper() == "CALL":
        preco = S * disc_q * Nd1 - K * disc_r * Nd2
        delta = disc_q * Nd1
        theta_ano = (-(S * disc_q * n_d1 * sigma) / (2.0 * math.sqrt(T))) - r * K * disc_r * Nd2 + q * S * disc_q * Nd1
        rho = K * T * disc_r * Nd2
    else:
        preco = K * disc_r * _N(-d2) - S * disc_q * _N(-d1)
        delta = -disc_q * _N(-d1)
        theta_ano = (-(S * disc_q * n_d1 * sigma) / (2.0 * math.sqrt(T))) + r * K * disc_r * _N(-d2) - q * S * disc_q * _N(-d1)
        rho = -K * T * disc_r * _N(-d2)

    gamma = (disc_q * n_d1) / (S * sigma * math.sqrt(T))
    vega = S * disc_q * n_d1 * math.sqrt(T)  # por 1.0 de vol (100pp)

    return {"preco": preco, "delta": delta, "gamma": gamma, "vega": vega, "theta_ano": theta_ano, "rho": rho, "d1": d1, "d2": d2}

def bs_price(S, K, r, q, sigma, T, kind):
    return black_scholes(S, K, r, q, sigma, T, kind)["preco"]

def implied_vol(target_price, S, K, r, q, T, kind, tol=1e-6, max_iter=100):
    """Retorna σ (a.a., decimal) tal que BS ≈ target_price (bisseção em [1e-6, 5.0])."""
    try:
        target = float(target_price)
    except:
        return None
    if target <= 0:
        return 0.0

    def f(sig): return bs_price(S, K, r, q, sig, T, kind) - target

    low, high = 1e-6, 5.0
    f_low, f_high = f(low), f(high)
    if f_low * f_high > 0:
        for h in (1.0, 2.0, 3.0, 5.0):
            f_high = f(h)
            if f_low * f_high <= 0:
                high = h
                break
        else:
            return None

    for _ in range(max_iter):
        mid = (low + high) / 2
        fm = f(mid)
        if abs(fm) < tol:
            return mid
        if f_low * fm <= 0:
            high = mid; f_high = fm
        else:
            low = mid; f_low = fm
    return (low + high) / 2
