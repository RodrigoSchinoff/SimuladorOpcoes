from django.shortcuts import render

from simulacoes.long_straddle import simular_long_straddle
from simulacoes.black_scholes import black_scholes, implied_vol

from core.app_core import atualizar_e_screener_atm_2venc
from services.api import buscar_detalhes_opcao, get_spot_ativo_oficial

import os




LOT_MIN = 100
DEFAULT_TOTAL_LOT = 10000


def _to_float(v, default=0.0):
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _parse_total_lot(v, default=DEFAULT_TOTAL_LOT):
    try:
        x = int(float(v))
        if x < LOT_MIN:
            x = LOT_MIN
    except Exception:
        x = default
    # normaliza para múltiplo de 100 (mais próximo)
    m = (x + LOT_MIN // 2) // LOT_MIN * LOT_MIN
    return int(m)


def _round_lots(call_raw, put_raw, total):
    c = int(call_raw // LOT_MIN) * LOT_MIN
    p = int(put_raw // LOT_MIN) * LOT_MIN
    rem = total - (c + p)
    while rem >= LOT_MIN:
        frac_c = (call_raw - c)
        frac_p = (put_raw - p)
        if frac_c >= frac_p:
            c += LOT_MIN
        else:
            p += LOT_MIN
        rem -= LOT_MIN
    return c, p


# Página inicial simples
def home(request):
    return render(request, "simulador_web/home.html")


# Long Straddle – usando o core real + screener/market_data
def long_straddle(request):
    ativo = (request.GET.get("ativo") or "").upper().strip()
    lote_total_raw = request.GET.get("lote_total") or str(DEFAULT_TOTAL_LOT)
    horizonte = request.GET.get("horizonte") or "Vencimento"
    crush_iv_raw = request.GET.get("crush_iv") or "10"

    lote_total = _parse_total_lot(lote_total_raw, DEFAULT_TOTAL_LOT)
    crush_iv = _to_float(crush_iv_raw, 10.0)

    if not ativo:
        return render(
            request,
            "simulador_web/long_straddle.html",
            {
                "resultado": None,
                "erro": None,
                "ativo": "",
                "spot_oficial": None,
                "linhas_screener": None,
                "lote_total": lote_total,
                "horizonte": horizonte,
                "crush_iv": crush_iv,
                "aviso_horizonte": None,
            },
        )

    try:
        # ---------- 1) Screener ATM (mesmo core do Flet) ----------
        res = atualizar_e_screener_atm_2venc(ativo, refresh=False)
        linhas_atm = (res or {}).get("atm", []) or []

        if not linhas_atm:
            raise ValueError("Nenhuma linha ATM retornada pelo screener.")

        # ---------- 2) Spot único oficial (igual Flet) ----------
        spot_uni = get_spot_ativo_oficial(ativo)
        if spot_uni is None and linhas_atm:
            spot_uni = _to_float(linhas_atm[0].get("spot"))
        spot_uni = _to_float(spot_uni) if spot_uni is not None else 0.0

        # ---------- 3) D+1 + Crush IV (cópia do Flet, sem UI) ----------
        if horizonte == "D+1" and linhas_atm:
            def _mid(d: dict) -> float:
                b = _to_float(d.get("bid"))
                a = _to_float(d.get("ask"))
                if b > 0 and a > 0:
                    return (b + a) / 2.0
                for k in ("ask", "last", "close", "bid"):
                    v = _to_float(d.get(k))
                    if v > 0:
                        return v
                return 0.0

            def _implied_or_min(preco, S, K, r, T, kind):
                try:
                    iv = implied_vol(preco, S, K, r, 0.0, T, kind)
                    return max(0.0001, iv) if iv else 0.0001
                except Exception:
                    return 0.0001

            def _T_years(days_val):
                try:
                    dias = max(1, int(_to_float(days_val, 1)))
                    return dias / 252.0
                except Exception:
                    return 1.0 / 252.0

            crush = crush_iv
            f = max(0.0, 1.0 - crush / 100.0)
            r_aa = _to_float(os.getenv("SELIC_AA", "10.0")) / 100.0

            for r in linhas_atm:
                call_sym = r.get("call")
                put_sym = r.get("put")
                if not (call_sym and put_sym):
                    continue
                try:
                    cd = buscar_detalhes_opcao(call_sym)
                    pd = buscar_detalhes_opcao(put_sym)

                    # sempre o mesmo SPOT único, como no Flet
                    S = spot_uni if spot_uni else _to_float(
                        cd.get("spot_price") or pd.get("spot_price")
                    )

                    Kc = _to_float(cd.get("strike"))
                    Kp = _to_float(pd.get("strike"))

                    Tc = _T_years(cd.get("days_to_maturity"))
                    Tp = _T_years(pd.get("days_to_maturity"))
                    Tc1 = max(Tc - 1 / 252.0, 1e-6)
                    Tp1 = max(Tp - 1 / 252.0, 1e-6)

                    Pc_mkt = _mid(cd)
                    Pp_mkt = _mid(pd)

                    sig_c = _implied_or_min(Pc_mkt, S, Kc, r_aa, Tc, "CALL")
                    sig_p = _implied_or_min(Pp_mkt, S, Kp, r_aa, Tp, "PUT")
                    sig_c1 = max(1e-4, sig_c * f)
                    sig_p1 = max(1e-4, sig_p * f)

                    Pc1 = black_scholes(S, Kc, r_aa, 0.0, sig_c1, Tc1, "CALL")["preco"]
                    Pp1 = black_scholes(S, Kp, r_aa, 0.0, sig_p1, Tp1, "PUT")["preco"]

                    r["call_premio"] = Pc1
                    r["put_premio"] = Pp1
                    r["premium_total"] = Pc1 + Pp1
                    r["be_down"] = round(Kp - (Pc1 + Pp1), 4)
                    r["be_up"] = round(Kc + (Pc1 + Pp1), 4)
                    r["spot"] = S
                except Exception:
                    continue

            aviso_horizonte = f"Cálculo D+1 aplicado com Crush IV de {crush_iv:.1f}%."
        else:
            aviso_horizonte = None

        # ---------- 4) Lotes e custo (mesma lógica do Flet) ----------
        linhas_enriquecidas = []
        for r in linhas_atm:
            call_sym = r.get("call")
            put_sym = r.get("put")
            delta_c = r.get("call_delta")
            delta_p = r.get("put_delta")

            w_call = abs(_to_float(delta_p)) if delta_p is not None else None
            w_put = abs(_to_float(delta_c)) if delta_c is not None else None

            if not w_call and not w_put:
                w_call = w_put = 1.0
            elif not w_call:
                w_call = 1.0
            elif not w_put:
                w_put = 1.0

            soma = (w_call or 0.0) + (w_put or 0.0)
            if soma == 0:
                w_call = w_put = 1.0
                soma = 2.0

            raw_call = lote_total * (w_call / soma)
            raw_put = lote_total - raw_call

            qty_call, qty_put = _round_lots(raw_call, raw_put, lote_total)

            call_premio = _to_float(r.get("call_premio"))
            put_premio = _to_float(r.get("put_premio"))
            custo_oper = qty_call * call_premio + qty_put * put_premio

            linha = dict(r)
            linha["qty_call"] = qty_call
            linha["qty_put"] = qty_put
            linha["custo_operacao"] = custo_oper
            linhas_enriquecidas.append(linha)

        # ---------- 5) Simulador (usa o primeiro par da lista) ----------
        primeira = linhas_atm[0]
        call0 = buscar_detalhes_opcao(primeira["call"])
        put0 = buscar_detalhes_opcao(primeira["put"])
        resultado = simular_long_straddle(call0, put0, renderizar=False)

        if spot_uni:
            resultado["spot"] = float(spot_uni)

        contexto = {
            "resultado": resultado,
            "erro": None,
            "ativo": ativo,
            "spot_oficial": spot_uni,
            "linhas_screener": linhas_enriquecidas,
            "lote_total": lote_total,
            "horizonte": horizonte,
            "crush_iv": crush_iv,
            "aviso_horizonte": aviso_horizonte,
        }

    except Exception as ex:
        contexto = {
            "resultado": None,
            "erro": str(ex),
            "ativo": ativo,
            "spot_oficial": None,
            "linhas_screener": None,
            "lote_total": lote_total,
            "horizonte": horizonte,
            "crush_iv": crush_iv,
            "aviso_horizonte": None,
        }

    return render(request, "simulador_web/long_straddle.html", contexto)
