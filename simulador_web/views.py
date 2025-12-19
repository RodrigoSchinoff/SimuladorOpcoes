# simulador_web/views.py
from django.shortcuts import render
from core.cache_keys import ls_cache_key
from core.lock import acquire_lock, release_lock
from simulacoes.long_straddle import simular_long_straddle
from simulacoes.black_scholes import black_scholes, implied_vol
from core.app_core import atualizar_e_screener_atm_2venc
from services.api import buscar_detalhes_opcao, get_spot_ativo_oficial
from simulador_web.models import PlanAssetList
from asgiref.sync import sync_to_async
from django.contrib.auth import logout
from django.shortcuts import redirect

import asyncio


from .utils import subscription_required
import os


def landing(request):
    return render(request, "simulador_web/landing.html")


LOT_MIN = 100
DEFAULT_TOTAL_LOT = 10000

# Lista padrão de ativos (20 mais líquidos aprox.)
LISTA_ATIVOS_PADRAO = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "ABEV3",
    "BBAS3", "WEGE3", "PRIO3", "BOVA11", "SUZB3",
    # "LREN3", "SUZB3", "GGBR4", "BRFS3", "RAIL3",
    # "CMIG4", "HAPV3", "PRIO3", "UGPA3", "ELET3",
]


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


def home(request):
    return render(request, "simulador_web/home.html")


# =========================================================
# LONG STRADDLE – VIEW PRINCIPAL
# =========================================================
# =========================================================
# LONG STRADDLE – VIEW PRINCIPAL (COM CACHE COMPLETO)
# =========================================================

# cache local (global no módulo)
_ls_cache = {}

async def acquire_lock_async(key):
    return await asyncio.to_thread(acquire_lock, key)

async def release_lock_async(key):
    await asyncio.to_thread(release_lock, key)

@sync_to_async
def get_tickers_for_user(user):
    plan = user.subscription.plan
    pal = PlanAssetList.objects.get(plan=plan)
    return list(pal.assets)

@subscription_required
async def long_straddle(request):

    # 🔒 EVITAR EXECUÇÃO AUTOMÁTICA (HEAD / GET VAZIO)
    if request.method == "HEAD":
        return render(request, "simulador_web/long_straddle.html", {})

    if not request.GET:
        contexto = {
            "resultado": None,
            "erro": None,
            "ativo": "",
            "spot_oficial": None,
            "linhas_screener": None,
            "lote_total": DEFAULT_TOTAL_LOT,
            "horizonte": "Vencimento",
            "crush_iv": 10,
            "num_vencimentos": "1",
            "be_max_pct": None,
            "aviso_horizonte": None,
        }
        return render(request, "simulador_web/long_straddle.html", contexto)


    # ---------------------------------------------------------
    # PARÂMETROS DO FORM + CHAVE DE CACHE
    # ---------------------------------------------------------
    ativo = (request.GET.get("ativo") or "").upper().strip()
    lote_total_raw = request.GET.get("lote_total") or str(DEFAULT_TOTAL_LOT)
    horizonte = request.GET.get("horizonte") or "Vencimento"
    crush_iv_raw = request.GET.get("crush_iv") or "10"
    num_vencimentos = request.GET.get("num_vencimentos", "1")
    be_max_pct_raw = request.GET.get("be_max_pct")

    lote_total = _parse_total_lot(lote_total_raw, DEFAULT_TOTAL_LOT)
    crush_iv = _to_float(crush_iv_raw, 10.0)
    be_max_pct = float(be_max_pct_raw) if be_max_pct_raw else None

    user_plan = request.user.subscription.plan
    cache_key = ls_cache_key(ativo, horizonte, num_vencimentos, user_plan)

    import time
    now_ts = time.time()
    ttl_ls = 200  # segundos de TTL do Long Straddle

    global _ls_cache
    cached = _ls_cache.get(cache_key)
    if cached and now_ts - cached["ts"] <= ttl_ls:
        return render(request, "simulador_web/long_straddle.html", cached["data"])

    # Anti-stampede: aguardar lock se cache frio
    if not await acquire_lock_async(cache_key):
        # não conseguiu lock → tentar ler cache novamente (outro thread pode ter gerado)
        cached = _ls_cache.get(cache_key)
        if cached:
            return render(request, "simulador_web/long_straddle.html", cached["data"])
        raise Exception("Sistema ocupado, tente novamente em instantes.")

    # ---------------------------------------------------------
    # SEM PARÂMETROS → tela vazia
    # ---------------------------------------------------------
    if not request.GET:
        contexto = {
            "resultado": None,
            "erro": None,
            "ativo": "",
            "spot_oficial": None,
            "linhas_screener": None,
            "lote_total": DEFAULT_TOTAL_LOT,
            "horizonte": "Vencimento",
            "crush_iv": 10,
            "num_vencimentos": "1",
            "be_max_pct": None,
            "aviso_horizonte": None,
        }
        return render(request, "simulador_web/long_straddle.html", contexto)

    try:
        # ------------------------------------------------------
        # 1) DEFINIR QUAIS ATIVOS SERÃO PROCESSADOS
        # ------------------------------------------------------
        if ativo:
            tickers = [ativo]
        else:
            tickers = await get_tickers_for_user(request.user)
        # ------------------------------------------------------
        # 2) RODAR SCREENER ATM PARA CADA TICKER (ASSÍNCRONO)
        # ------------------------------------------------------
        import asyncio

        async def run_screener(tkr):
            return await asyncio.to_thread(atualizar_e_screener_atm_2venc, tkr, False)

        linhas_atm = []
        resultados = await asyncio.gather(*[run_screener(t) for t in tickers], return_exceptions=True)

        for tkr, res in zip(tickers, resultados):
            if isinstance(res, Exception):
                continue
            atm_tkr = (res or {}).get("atm", []) or []
            for row in atm_tkr:
                r = dict(row)
                r["ticker"] = tkr
                linhas_atm.append(r)

        if not linhas_atm:
            raise ValueError("Nenhuma linha ATM retornada pelo screener.")

        linhas_atm.sort(key=lambda r: r.get("ticker", ""))

        # ------------------------------------------------------
        # 3) SPOT OFICIAL
        # ------------------------------------------------------
        from services.api import get_spot_ativo_oficial

        spot_uni = None
        spots_oficiais = {}

        if len(tickers) == 1:
            try:
                spot_uni = get_spot_ativo_oficial(tickers[0])
            except:
                spot_uni = None
            if spot_uni is None and linhas_atm:
                spot_uni = _to_float(linhas_atm[0].get("spot"))
            spot_uni = _to_float(spot_uni) if spot_uni else 0.0
            if spot_uni:
                spots_oficiais[tickers[0]] = spot_uni
        else:
            for tkr in tickers:
                try:
                    so = get_spot_ativo_oficial(tkr)
                    if so is not None:
                        spots_oficiais[tkr] = _to_float(so)
                except:
                    continue

        for r in linhas_atm:
            tkr = r.get("ticker")
            if tkr in spots_oficiais:
                r["spot_oficial"] = spots_oficiais[tkr]

        # ------------------------------------------------------
        # 4) D+1 + CRUSH IV (mesma lógica Flet)
        # ------------------------------------------------------
        from simulacoes.black_scholes import black_scholes, implied_vol
        from services.api import buscar_detalhes_opcao
        import os

        if horizonte == "D+1" and linhas_atm:

            def _mid(d):
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
                except:
                    return 0.0001

            def _T_years(days_val):
                try:
                    dias = max(1, int(_to_float(days_val, 1)))
                    return dias / 252.0
                except:
                    return 1 / 252.0

            crush = crush_iv
            f = max(0.0, 1.0 - crush / 100.0)
            r_aa = _to_float(os.getenv("SELIC_AA", "10.0")) / 100.0

            detalhes_cache = {}

            for r in linhas_atm:
                call_sym = r.get("call")
                put_sym = r.get("put")
                if not call_sym or not put_sym:
                    continue

                try:
                    if call_sym in detalhes_cache:
                        cd = detalhes_cache[call_sym]
                    else:
                        cd = buscar_detalhes_opcao(call_sym)
                        detalhes_cache[call_sym] = cd

                    if put_sym in detalhes_cache:
                        pd = detalhes_cache[put_sym]
                    else:
                        pd = buscar_detalhes_opcao(put_sym)
                        detalhes_cache[put_sym] = pd

                    if spot_uni and spot_uni > 0:
                        S = spot_uni
                    else:
                        S = _to_float(r.get("spot_oficial") or cd.get("spot_price") or pd.get("spot_price"))

                    Kc = _to_float(cd.get("strike"))
                    Kp = _to_float(pd.get("strike"))
                    Tc = _T_years(cd.get("days_to_maturity"))
                    Tp = _T_years(pd.get("days_to_maturity"))
                    Tc1 = max(Tc - 1/252.0, 1e-6)
                    Tp1 = max(Tp - 1/252.0, 1e-6)

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

                except:
                    continue

            aviso_horizonte = f"Cálculo D+1 aplicado com Crush IV de {crush_iv:.1f}%."
        else:
            aviso_horizonte = None

        # ------------------------------------------------------
        # 5) LOTES, CUSTO, BE%
        # ------------------------------------------------------
        linhas_enriquecidas = []
        for r in linhas_atm:
            delta_c = r.get("call_delta")
            delta_p = r.get("put_delta")

            w_call = abs(_to_float(delta_p)) if delta_p is not None else 1.0
            w_put = abs(_to_float(delta_c)) if delta_c is not None else 1.0
            soma = w_call + w_put

            if soma == 0:
                continue

            raw_call = lote_total * (w_call / soma)
            raw_put = lote_total - raw_call

            qty_call, qty_put = _round_lots(raw_call, raw_put, lote_total)

            call_premio = _to_float(r.get("call_premio"))
            put_premio = _to_float(r.get("put_premio"))
            custo_oper = qty_call * call_premio + qty_put * put_premio

            r = dict(r)
            r["qty_call"] = qty_call
            r["qty_put"] = qty_put
            r["custo_operacao"] = custo_oper

            if r.get("spot_oficial") is not None:
                spot_ref = _to_float(r["spot_oficial"])
            elif spot_uni:
                spot_ref = spot_uni
            else:
                spot_ref = _to_float(r.get("spot"))

            be_down_val = r.get("be_down")
            be_up_val = r.get("be_up")

            if spot_ref and spot_ref > 0:
                r["be_pct_down"] = ((be_down_val / spot_ref) - 1.0) * 100 if be_down_val else None
                r["be_pct_up"] = ((be_up_val / spot_ref) - 1.0) * 100 if be_up_val else None
            else:
                r["be_pct_down"] = None
                r["be_pct_up"] = None

            linhas_enriquecidas.append(r)

        # ------------------------------------------------------
        # 6) FILTROS
        # ------------------------------------------------------
        if be_max_pct is not None:
            linhas_enriquecidas = [
                r for r in linhas_enriquecidas
                if (
                    r.get("be_pct_down") is not None and abs(r["be_pct_down"]) <= be_max_pct
                ) or (
                    r.get("be_pct_up") is not None and abs(r["be_pct_up"]) <= be_max_pct
                )
            ]

        if num_vencimentos in ("1", "2"):
            max_rows = 2 if num_vencimentos == "1" else 4
            agrupado = {}
            for r in linhas_enriquecidas:
                agrupado.setdefault(r["ticker"], []).append(r)

            linhas_final = []
            for tkr, rows in agrupado.items():
                linhas_final.extend(rows[:max_rows])
            linhas_enriquecidas = linhas_final

        if not linhas_enriquecidas:
            raise ValueError("Nenhuma opção após filtros.")

        # ------------------------------------------------------
        # 7) SIMULAÇÃO FINAL
        # ------------------------------------------------------
        from services.api import buscar_detalhes_opcao
        from simulacoes.long_straddle import simular_long_straddle

        primeira = linhas_enriquecidas[0]
        call0 = buscar_detalhes_opcao(primeira["call"])
        put0 = buscar_detalhes_opcao(primeira["put"])
        resultado = simular_long_straddle(call0, put0, renderizar=False)

        if spot_uni:
            resultado["spot"] = float(spot_uni)
        else:
            resultado["spot"] = _to_float(primeira.get("spot_oficial") or primeira.get("spot"))

        contexto = {
            "resultado": resultado,
            "erro": None,
            "ativo": ativo,
            "spot_oficial": spot_uni if spot_uni else None,
            "linhas_screener": linhas_enriquecidas,
            "lote_total": lote_total,
            "horizonte": horizonte,
            "crush_iv": crush_iv,
            "aviso_horizonte": aviso_horizonte,
            "num_vencimentos": num_vencimentos,
            "be_max_pct": be_max_pct,
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
            "num_vencimentos": num_vencimentos,
            "be_max_pct": be_max_pct,
            "aviso_horizonte": None,
        }

    finally:
        await release_lock_async(cache_key)

    # ---------------------------------------------------------
    # SALVAR RESULTADO FINAL NO CACHE
    # ---------------------------------------------------------
    _ls_cache[cache_key] = {
        "ts": time.time(),
        "data": contexto
    }

    return render(request, "simulador_web/long_straddle.html", contexto)

def sair(request):
    logout(request)
    return redirect("landing")