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
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from simulador_web.models import Lead
from simulador_web.domain.iv_atm_decision import build_iv_decisao

import json

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


def fmt_brl(v):
    """
    Formatação pt-BR sem símbolo de moeda.
    Ex: 5931.5 -> "5.931,50"
    """
    try:
        return f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00"


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


def _redirect_landing_inactive(request):
    messages.error(request, "Sua assinatura está expirada ou bloqueada. Regularize para continuar.")
    return redirect("/accounts/login/")


@subscription_required
async def long_straddle(request):

    # =====================================================
    # BLOQUEIO DEFINITIVO: expirada / blocked / inválida
    # (antes de qualquer execução, cache, lock ou API)
    # =====================================================
    if not request.user.is_authenticated:
        return redirect("/accounts/login/?next=/app/ls/")

    sub = getattr(request.user, "subscription", None)

    if not sub:
        return _redirect_landing_inactive(request)

    if getattr(sub, "status", None) == "blocked":
        return _redirect_landing_inactive(request)

    end_date = getattr(sub, "end_date", None)
    if end_date and end_date < timezone.localdate():
        return _redirect_landing_inactive(request)

    # mantém a regra central de validade
    if hasattr(sub, "is_active") and not sub.is_active():
        return _redirect_landing_inactive(request)

    # 🔒 EVITAR EXECUÇÃO AUTOMÁTICA (HEAD / GET VAZIO)
    if request.method == "HEAD":
        contexto = {}
        contexto["iv_decisao"] = build_iv_decisao(request, "")
        return render(request, "simulador_web/long_straddle.html", contexto)

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
        contexto["iv_decisao"] = build_iv_decisao(request, "")
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
    cache_key = (
        f"{ls_cache_key(ativo, horizonte, num_vencimentos, user_plan)}"
        f"|lot={lote_total}"
        f"|crush={crush_iv}"
        f"|be={be_max_pct}"
    )

    import time
    now_ts = time.time()
    ttl_ls = 600  # segundos de TTL do Long Straddle

    global _ls_cache
    cached = _ls_cache.get(cache_key)
    if cached and now_ts - cached["ts"] <= ttl_ls:
        contexto = dict(cached["data"])
        if user_plan == "pro":
            contexto["iv_decisao"] = await asyncio.to_thread(
                build_iv_decisao, request, ativo
            )
        else:
            contexto["iv_decisao"] = None

        return render(request, "simulador_web/long_straddle.html", contexto)

    # Anti-stampede: aguardar lock se cache frio
    if not await acquire_lock_async(cache_key):
        # não conseguiu lock → tentar ler cache novamente (outro thread pode ter gerado)
        cached = _ls_cache.get(cache_key)
        if cached:
            contexto = dict(cached["data"])
            if user_plan == "pro":
                contexto["iv_decisao"] = await asyncio.to_thread(
                    build_iv_decisao, request, ativo
                )
            else:
                contexto["iv_decisao"] = None

            return render(request, "simulador_web/long_straddle.html", contexto)
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
        contexto["iv_decisao"] = build_iv_decisao(request, "")
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

            # >>> AJUSTE D+1 (LOG / MID / BS)
            # Logs ativados por padrão em ambiente local.
            # Para desligar explicitamente: export LS_D1_LOG=0
            log_d1 = os.getenv("LS_D1_LOG", "1") == "1"

            def _px_ref(d):
                """
                Preço de referência para mercado:
                - Se bid>0 e ask>0 => MID
                - Senão => fallback (ask/last/close/bid)
                Retorna: (preco, src, bid, ask)
                """
                b = _to_float(d.get("bid"))
                a = _to_float(d.get("ask"))
                last = _to_float(d.get("last"))
                close = _to_float(d.get("close"))

                if b > 0 and a > 0:
                    return (b + a) / 2.0, "MID", b, a

                if a > 0:
                    return a, "ASK", b, a
                if last > 0:
                    return last, "LAST", b, a
                if close > 0:
                    return close, "CLOSE", b, a
                if b > 0:
                    return b, "BID", b, a
                return 0.0, "ZERO", b, a

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

                    # D+1 => reduz 1 dia útil
                    Tc1 = max(Tc - 1/252.0, 1e-6)
                    Tp1 = max(Tp - 1/252.0, 1e-6)

                    Pc_mkt, src_c, bid_c, ask_c = _px_ref(cd)
                    Pp_mkt, src_p, bid_p, ask_p = _px_ref(pd)

                    if log_d1:
                        print(f"[D+1][PX][CALL] {call_sym} | bid={bid_c:.4f} | ask={ask_c:.4f} | src={src_c} | px={Pc_mkt:.4f}", flush=True)
                        print(f"[D+1][PX][PUT ] {put_sym} | bid={bid_p:.4f} | ask={ask_p:.4f} | src={src_p} | px={Pp_mkt:.4f}", flush=True)

                    # IV de mercado (a partir do preço de mercado)
                    sig_c = _implied_or_min(Pc_mkt, S, Kc, r_aa, Tc, "CALL")
                    sig_p = _implied_or_min(Pp_mkt, S, Kp, r_aa, Tp, "PUT")

                    # IV pós-crush para o cenário D+1
                    sig_c1 = max(1e-4, sig_c * f)
                    sig_p1 = max(1e-4, sig_p * f)

                    # BS do cenário (para delta/greeks), mas prêmio exibido vem do mercado (px_ref)
                    bs_c = black_scholes(S, Kc, r_aa, 0.0, sig_c1, Tc1, "CALL") or {}
                    bs_p = black_scholes(S, Kp, r_aa, 0.0, sig_p1, Tp1, "PUT") or {}

                    d_c = bs_c.get("delta")
                    d_p = bs_p.get("delta")

                    if log_d1:
                        print(f"[D+1][BS][CALL] {call_sym} | IV_mkt={sig_c:.4f} | IV_crush={sig_c1:.4f} | delta={d_c}", flush=True)
                        print(f"[D+1][BS][PUT ] {put_sym} | IV_mkt={sig_p:.4f} | IV_crush={sig_p1:.4f} | delta={d_p}", flush=True)

                    # Prêmios exibidos no D+1 = preço de mercado (MID quando possível)
                    r["call_premio"] = Pc_mkt
                    r["put_premio"] = Pp_mkt
                    prem_total = Pc_mkt + Pp_mkt
                    r["premium_total"] = prem_total

                    # BE coerente com o prêmio exibido (corrige bug Pc1/Pp1 inexistentes)
                    r["be_down"] = round(Kp - prem_total, 4)
                    r["be_up"] = round(Kc + prem_total, 4)

                    # Atualiza deltas para D+1 (sem depender do screener)
                    if d_c is not None:
                        r["call_delta"] = round(_to_float(d_c), 4)
                    if d_p is not None:
                        r["put_delta"] = round(_to_float(d_p), 4)

                    S = r["spot"]  # usa o mesmo spot do screener ATM

                except:
                    continue

            aviso_horizonte = f"Cálculo D+1 aplicado com Crush IV de {crush_iv:.1f}%."
            # <<< FIM AJUSTE D+1
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

            # ✅ Substituição mínima: remove locale e mantém padrão R$ 5.931,50
            r["custo_operacao"] = fmt_brl(custo_oper)

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
        # 6.1) ORDENAÇÃO POR MENOR BE% + REDUÇÃO (APENAS PLANO PRO)
        # ------------------------------------------------------

        if user_plan == "pro":

            def _be_pct_min(r):
                vals = []
                if r.get("be_pct_down") is not None:
                    vals.append(abs(r["be_pct_down"]))
                if r.get("be_pct_up") is not None:
                    vals.append(abs(r["be_pct_up"]))
                return min(vals) if vals else float("inf")

            # Sempre ordenar por menor BE%
            linhas_enriquecidas.sort(key=_be_pct_min)

            # Consulta FULL (sem ativo): manter apenas 1 LS por ticker
            if not ativo:
                agrupado = {}
                for r in linhas_enriquecidas:
                    agrupado.setdefault(r["ticker"], []).append(r)

                linhas_finais = []

                for tkr, rows in agrupado.items():

                    # 🔎 LOG — CANDIDATOS
                    print(f"[LS-RANK][CANDIDATOS] {tkr}", flush=True)
                    for r in rows:
                        print(
                            f"  call={r.get('call')} put={r.get('put')} | "
                            f"venc={r.get('due_date')} | "
                            f"be_pct_down={r.get('be_pct_down'):.4f} "
                            f"be_pct_up={r.get('be_pct_up'):.4f} | "
                            f"be_pct_min={_be_pct_min(r):.4f}",
                            flush=True
                        )

                    # vencedor = menor BE%
                    vencedor = rows[0]
                    linhas_finais.append(vencedor)

                    # 🏆 LOG — ESCOLHIDO
                    print(
                        f"[LS-RANK][ESCOLHIDO] {tkr} | "
                        f"call={vencedor.get('call')} put={vencedor.get('put')} | "
                        f"be_pct_min={_be_pct_min(vencedor):.4f}",
                        flush=True
                    )

                linhas_enriquecidas = linhas_finais

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
    # INJETAR IV DECISÃO (FORÇADO)
    # ---------------------------------------------------------
    if user_plan == "pro":
        contexto["iv_decisao"] = await asyncio.to_thread(
            build_iv_decisao, request, ativo
        )
    else:
        contexto["iv_decisao"] = None

    # ---------------------------------------------------------
    # SALVAR RESULTADO FINAL NO CACHE
    # ---------------------------------------------------------
    contexto_cache = dict(contexto)
    contexto_cache["iv_decisao"] = None  # nunca cachear IV decisão

    _ls_cache[cache_key] = {
        "ts": time.time(),
        "data": contexto_cache
    }

    # >>> IV HISTÓRICA (FORA DO CACHE) <<<
    if user_plan == "pro":
        contexto["iv_decisao"] = await asyncio.to_thread(
            build_iv_decisao, request, ativo
        )
    else:
        contexto["iv_decisao"] = None

    return render(request, "simulador_web/long_straddle.html", contexto)


def sair(request):
    logout(request)
    return redirect("landing")


def planos(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))

            plano = data.get("plano", "").strip()
            if plano not in ("trial", "pro"):
                return JsonResponse({"ok": False}, status=400)

            nome = data.get("nome", "").strip()
            email = data.get("email", "").strip()
            whatsapp = data.get("whatsapp", "").strip()
            cpf = data.get("cpf", "").strip()

            # captura de IP (proxy-safe)
            ip = request.META.get("HTTP_X_FORWARDED_FOR")
            if ip:
                ip = ip.split(",")[0].strip()
            else:
                ip = request.META.get("REMOTE_ADDR")

            # 1) salva o lead (fonte da verdade)
            Lead.objects.create(
                nome=nome,
                email=email,
                whatsapp=whatsapp,
                cpf=cpf,
                plano_interesse=plano,
                status="novo",
                ip_origem=ip,
            )

            # 2) envia e-mail (não crítico)
            resend_key = os.getenv("RESEND_API_KEY")
            if resend_key:
                try:
                    import requests

                    requests.post(
                        "https://api.resend.com/emails",
                        headers={
                            "Authorization": f"Bearer {resend_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "from": "StraddlePro <onboarding@resend.dev>",
                            "to": ["rodrigo.scholiveira@gmail.com"],
                            "subject": "Novo lead – StraddlePro",
                            "text": (
                                "Novo lead recebido:\n\n"
                                f"Nome: {nome}\n"
                                f"E-mail: {email}\n"
                                f"WhatsApp: {whatsapp}\n"
                                f"CPF: {cpf}\n"
                                f"Plano: {plano}\n"
                                f"IP: {ip}"
                            ),
                        },
                        timeout=5,
                    )
                except Exception:
                    pass  # e-mail nunca pode quebrar o fluxo

            return JsonResponse({"ok": True})

        except Exception:
            return JsonResponse({"ok": False}, status=400)

    return render(request, "simulador_web/planos.html")
