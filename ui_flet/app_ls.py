# ui_flet/app_ls.py
import os
os.environ.setdefault("MPLBACKEND", "Agg")  # Matplotlib sem janela (web/servidor)

# Carrega variáveis do .env, se existir (útil ao rodar local)
try:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv()  # .env no cwd
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)  # .env na raiz do projeto
except Exception:
    pass

import flet as ft
from typing import Dict, Any, List

from services.api import buscar_detalhes_opcao
from simulacoes.long_straddle import simular_long_straddle
from core.app_core import atualizar_e_screener_atm_2venc


# ---------------- Helpers ----------------
def show_snack(page, msg: str):
    page.snack_bar = ft.SnackBar(ft.Text(msg))
    page.snack_bar.open = True
    page.update()

def to_float(v, default=0.0):
    try:
        if v is None:
            return default
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        # aceita formatos BR: "1.234,56"
        if "," in s:
            if "." in s:
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", ".")
        return float(s)
    except (TypeError, ValueError):
        return default


def preco_compra_premio(leg: Dict[str, Any]) -> float:
    ask   = to_float(leg.get("ask"))
    last  = to_float(leg.get("last"))
    close = to_float(leg.get("close"))
    bid   = to_float(leg.get("bid"))
    if ask > 0: return ask
    if last > 0: return last
    if close > 0: return close
    if bid > 0: return bid
    return 0.0

def gerar_malha_precos(centro: float, n_pontos: int = 101, largura: float = 0.4) -> List[float]:
    if centro <= 0: centro = 10.0
    pmin = max(0.0, centro * (1 - largura))
    pmax = centro * (1 + largura)
    passo = (pmax - pmin) / (n_pontos - 1)
    return [round(pmin + i * passo, 2) for i in range(n_pontos)]

def fallback_res(call: Dict[str, Any], put: Dict[str, Any]) -> Dict[str, Any]:
    strike_call = to_float(call.get("strike"))
    strike_put  = to_float(put.get("strike"))
    premio_call = preco_compra_premio(call)
    premio_put  = preco_compra_premio(put)
    cs = int(to_float(call.get("contract_size") or put.get("contract_size") or 100) or 100)
    spot = to_float(call.get("spot_price") or put.get("spot_price"))
    venc = call.get("due_date") or put.get("due_date") or ""

    custo_total = (premio_call + premio_put) * cs
    be_down     = round(strike_put  - (premio_call + premio_put), 2)
    be_up       = round(strike_call + (premio_call + premio_put), 2)

    centro = spot or ((strike_call + strike_put)/2 if (strike_call and strike_put) else (strike_call or strike_put or 10.0))
    precos = gerar_malha_precos(centro)

    payoff = []
    for px in precos:
        lucro_call = max(0.0, px - strike_call) * cs
        lucro_put  = max(0.0, strike_put - px) * cs
        payoff.append(lucro_call + lucro_put - custo_total)

    return {
        "estrategia": "Long Straddle",
        "precos": precos,
        "payoff": payoff,
        "spot": spot,
        "be_down": be_down,
        "be_up": be_up,
        "vencimento": venc,
    }


# -------------- Painel: Simulador --------------
def build_simulador_panel(page):
    import datetime as dt
    from simulacoes.black_scholes import black_scholes, implied_vol

    # SELIC automática (com fallback)
    try:
        from services.rates import get_selic_aa_safe
        SELIC_AA = get_selic_aa_safe()  # % a.a.
    except Exception:
        SELIC_AA = to_float(os.getenv("SELIC_AA", "10.0"))

    # Dropdown único de pares (CALL|PUT); screener preenche
    dd_par = ft.Dropdown(label="Par (CALL - PUT)", options=[], value=None, width=420)
    page.sim_dd_par = dd_par  # screener usa isso para popular

    status_txt = ft.Text("", size=12)
    chart_container = ft.Container(width=640, height=380, padding=10, border_radius=12)

    # -------- helpers --------
    def _mid_price(d: Dict[str, Any]) -> float:
        b = to_float(d.get("bid")); a = to_float(d.get("ask"))
        if b > 0 and a > 0: return (b + a) / 2.0
        for k in ("ask", "last", "close", "bid"):
            v = to_float(d.get(k))
            if v > 0: return v
        return 0.0

    def _days_from_due(due_date: str) -> int:
        try:
            d = dt.datetime.strptime(due_date, "%Y-%m-%d").date()
            return max(1, (d - dt.date.today()).days)
        except Exception:
            return 30

    def _split_par(val: str):
        if not val: return None, None
        if "|" in val:
            a, b = val.split("|", 1); return a.strip(), b.strip()
        if " - " in val:
            a, b = val.split(" - ", 1); return a.strip(), b.strip()
        return None, None

    # -------- Form BS (q=0; dias vêm do par; tipo FIXO por card) --------
    def _make_bs_form(fixed_kind: str):
        state = {"days": 30}

        tf_S     = ft.TextField(label=f"Spot (S) {fixed_kind}", width=150)
        tf_K     = ft.TextField(label=f"Strike (K) {fixed_kind}", width=150)
        tf_r     = ft.TextField(label="r % a.a.", width=110, value=f"{SELIC_AA:.2f}")  # editável
        tf_sigma = ft.TextField(label="σ % a.a.", width=120)                            # "Preço dado σ"
        tf_prem  = ft.TextField(label="Preço/Prêmio (R$)", width=160)                   # "IV dado preço"
        dd_modo  = ft.Dropdown(label="Modo", width=190,
                               options=[ft.dropdown.Option("IV dado preço"), ft.dropdown.Option("Preço dado σ")],
                               value="IV dado preço")

        out = ft.Text("", size=11)
        grid = ft.DataTable(
            columns=[ft.DataColumn(ft.Text("Métrica")), ft.DataColumn(ft.Text("Valor"))],
            rows=[], column_spacing=18, visible=False
        )

        def _to_years(days):
            try:
                d = float(days)
                return max(0.0, d) / 252.0, 252.0  # base 252 (B3)
            except:
                return 0.0, 252.0

        def _fmt_money(v):
            try:
                s = f"{float(v):,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")
                return f"R$ {s}"
            except:
                return "R$ 0,0000"

        def _calc(_):
            try:
                S = to_float(tf_S.value); K = to_float(tf_K.value)
                r = to_float(tf_r.value)/100.0
                q = 0.0
                T, base_ano = _to_years(state["days"])
                kind = fixed_kind.upper()

                if (dd_modo.value or "") == "IV dado preço":
                    preco_mkt = to_float(tf_prem.value)
                    sigma = implied_vol(preco_mkt, S, K, r, q, T, kind)
                    if not sigma or sigma <= 0:
                        out.value = "IV não encontrada para o preço informado."
                        grid.visible = False; page.update(); return
                    tf_sigma.value = f"{sigma*100:.4f}".replace(".", ",")
                else:
                    sigma = to_float(tf_sigma.value)/100.0

                res = black_scholes(S, K, r, q, sigma, T, kind)
                preco = res["preco"]; theta_dia = res["theta_ano"]/base_ano
                grid.rows = [
                    ft.DataRow(cells=[ft.DataCell(ft.Text("Vol (σ a.a.)")), ft.DataCell(ft.Text(f"{sigma*100:.4f}%".replace(".", ",")))]),
                    ft.DataRow(cells=[ft.DataCell(ft.Text("Preço teórico")), ft.DataCell(ft.Text(_fmt_money(preco)))]),
                    ft.DataRow(cells=[ft.DataCell(ft.Text("Preço × 100")), ft.DataCell(ft.Text(_fmt_money(preco*100)))]),
                    ft.DataRow(cells=[ft.DataCell(ft.Text("Delta")),  ft.DataCell(ft.Text(f"{res['delta']:.4f}".replace(".", ",")))]),
                    ft.DataRow(cells=[ft.DataCell(ft.Text("Gamma")),  ft.DataCell(ft.Text(f"{res['gamma']:.6f}".replace(".", ",")))]),
                    ft.DataRow(cells=[ft.DataCell(ft.Text("Vega (1pp σ)")), ft.DataCell(ft.Text(f"{(res['vega']/100.0):.4f}".replace(".", ",")))]),
                    ft.DataRow(cells=[ft.DataCell(ft.Text("Theta/dia")), ft.DataCell(ft.Text(f"{theta_dia:.4f}".replace(".", ",")))]),
                    ft.DataRow(cells=[ft.DataCell(ft.Text("Rho")),    ft.DataCell(ft.Text(f"{res['rho']:.4f}".replace(".", ",")))]),
                ]
                grid.visible = True; out.value = ""; page.update()
            except Exception as ex:
                grid.visible = False; out.value = f"Erro: {ex}"; page.update()

        btn = ft.FilledButton("Calcular", icon="calculate", on_click=_calc)

        def setter(S=None, K=None, days=None, premio_default=None):
            if S is not None: tf_S.value = str(S)
            if K is not None: tf_K.value = str(K)
            if days is not None: state["days"] = int(days)
            if premio_default is not None: tf_prem.value = f"{premio_default:.4f}".replace(".", ",")
            dd_modo.value = "IV dado preço"; tf_sigma.value = ""
            page.update()
            _calc(None)  # calcula automático

        card = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(f"Black-Scholes — {fixed_kind}", size=14, weight=ft.FontWeight.BOLD),
                        ft.Row([tf_S, tf_K], spacing=8),
                        ft.Row([tf_r, tf_sigma, tf_prem], spacing=8),
                        ft.Row([dd_modo, btn], spacing=8),
                        grid, out
                    ], spacing=8
                ),
                padding=12
            )
        )
        return card, setter

    bs_call_card, bs_call_set = _make_bs_form("CALL")
    bs_put_card,  bs_put_set  = _make_bs_form("PUT")

    # expor setters (screener pode usar)
    page.bs_call_set = bs_call_set
    page.bs_put_set  = bs_put_set

    # -------- Simulação (gráfico) --------
    def on_simular(_):
        v = dd_par.value
        call_symbol, put_symbol = _split_par(v)
        if not (call_symbol and put_symbol):
            show_snack(page, "Selecione um par CALL|PUT."); return

        btn_simular.disabled = True
        status_txt.value = f"Simulando {call_symbol} x {put_symbol}..."
        page.update()
        try:
            call = buscar_detalhes_opcao(call_symbol)
            put  = buscar_detalhes_opcao(put_symbol)
            try:
                res = simular_long_straddle(call, put, renderizar=False)
            except TypeError:
                res = simular_long_straddle(call, put)
            except Exception:
                res = fallback_res(call, put)

            from viz.payoff import plotar_payoff
            fig, _ = plotar_payoff(
                res["precos"], res["payoff"], res.get("spot"),
                res.get("be_down"), res.get("be_up"),
                call.get("symbol",""), put.get("symbol",""),
                res.get("vencimento",""),
                estrategia_nome=res.get("estrategia","Long Straddle"),
                mostrar=False, fig_size=(6.0, 3.6), dpi=120, font_scale=0.95
            )
            from flet.matplotlib_chart import MatplotlibChart
            chart_container.content = MatplotlibChart(fig)
            status_txt.value = "Simulação concluída."
            page.update()
        except Exception as ex:
            status_txt.value = ""
            show_snack(page, f"Erro na simulação: {ex}")
        finally:
            btn_simular.disabled = False
            page.update()

    btn_simular = ft.FilledButton("Simular Long Straddle", icon="show_chart", on_click=on_simular, disabled=True)
    page.sim_btn = btn_simular
    page.sim_on_simular = on_simular

    # Prefill automático das duas calculadoras quando escolher o PAR
    def on_par_change(_):
        v = dd_par.value
        call_symbol, put_symbol = _split_par(v)
        if not (call_symbol and put_symbol):
            btn_simular.disabled = True
            page.update()
            return
        try:
            call = buscar_detalhes_opcao(call_symbol)
            put  = buscar_detalhes_opcao(put_symbol)

            # SPOT único vindo do screener (se existir); mantém coerência calculadoras + tabela
            spot_ovr = getattr(page, "spot_override", None)
            if spot_ovr is not None:
                spot = float(spot_ovr)
            else:
                spot = to_float(call.get("spot_price") or put.get("spot_price"))

            # Dias (API ou por due_date)
            days = call.get("days_to_maturity") or put.get("days_to_maturity") \
                   or _days_from_due(call.get("due_date") or put.get("due_date") or "")

            # Preços de referência (mid)
            prem_call = _mid_price(call)
            prem_put  = _mid_price(put)

            # Preenche e já calcula
            bs_call_set(S=spot, K=to_float(call.get("strike")), days=days, premio_default=prem_call)
            bs_put_set (S=spot, K=to_float(put.get("strike")),  days=days, premio_default=prem_put)

            btn_simular.disabled = False
            page.update()
        except Exception as ex:
            show_snack(page, f"Erro ao preencher BS: {ex}")
            btn_simular.disabled = True
            page.update()

    dd_par.on_change = on_par_change
    page.sim_on_par_change = on_par_change

    right_column = ft.Container(
        content=ft.Column([bs_call_card, bs_put_card], spacing=10),
        width=440
    )

    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Simulador Long Straddle", size=18),
                ft.Text("Escolha um PAR (CALL|PUT) para simular e ver Black-Scholes.", size=12),
                ft.Row([dd_par, btn_simular], spacing=12),
                status_txt,
                ft.Row([chart_container, right_column], spacing=16, vertical_alignment=ft.CrossAxisAlignment.START),
            ],
            spacing=14
        ),
        padding=20,
        border_radius=12,
    )


# -------------- Painel: Screener --------------
def build_screener_panel(page):
    from datetime import date

    LOT_MIN = 100

    def _parse_total_lot(v, default=10000):
        try:
            x = int(float(v))
            if x < LOT_MIN:
                x = LOT_MIN
        except Exception:
            x = default
        # normaliza para múltiplo de 100 (mais próximo)
        m = (x + LOT_MIN // 2) // LOT_MIN * LOT_MIN
        return int(m)

    tkr = ft.TextField(label="Ticker (ex.: PETR4)", width=220)
    lote_total_tf = ft.TextField(label="Lote Total", width=150, value="10000", text_align=ft.TextAlign.RIGHT)

    # --- NOVO: seleção de horizonte e crush ---
    dd_horiz = ft.Dropdown(
        label="Horizonte",
        options=[ft.dropdown.Option("Vencimento"), ft.dropdown.Option("D+1")],
        value="Vencimento",
        width=200,  # ↑ aumentamos para não “comer” o texto
    )

    tf_crush = ft.TextField(
        label="Crush IV (%)",
        value="10",
        width=120,
        text_align=ft.TextAlign.RIGHT,
        disabled=True,  # ← começa desabilitado (só habilita em D+1)
    )

    def _on_horiz_change(_):
        tf_crush.disabled = (dd_horiz.value != "D+1")
        tf_crush.update()

    dd_horiz.on_change = _on_horiz_change



    # DatePicker
    dp = ft.DatePicker(first_date=date(2020, 1, 1), last_date=date(2035, 12, 31))
    if dp not in page.overlay:
        page.overlay.append(dp)
        page.update()

    _H = 48
    _PAD = ft.padding.only(left=12, right=12, top=12, bottom=12)

    tf_venc = ft.TextField(
        label="Vencimento",
        width=220,
        height=_H,
        content_padding=_PAD,
        read_only=True,
        hint_text="YYYY-MM-DD",
        visible=False
    )

    def abrir_calendario(_):
        try:
            if hasattr(page, "open"):
                page.open(dp)
            else:
                dp.open = True
                page.update()
        except Exception:
            dp.open = True
            page.update()

    def on_date_change(_):
        if dp.value:
            tf_venc.value = dp.value.strftime("%Y-%m-%d")
            page.update()

    dp.on_change = on_date_change
    tf_venc.suffix = ft.IconButton(icon="event", tooltip="Selecionar data", on_click=abrir_calendario)

    status = ft.Text(size=12)
    busy = ft.Row(
        controls=[ft.ProgressRing(), ft.Text("Processando...")],
        visible=False,
        spacing=10
    )

    output = ft.Text(value="", selectable=True, visible=False)

    table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Moneyness")),
            ft.DataColumn(ft.Text("CALL")),
            ft.DataColumn(ft.Text("PUT")),
            ft.DataColumn(ft.Text("Strike")),
            ft.DataColumn(ft.Text("%BE↓")),
            ft.DataColumn(ft.Text("BE↓")),
            ft.DataColumn(ft.Text("%BE↑")),
            ft.DataColumn(ft.Text("BE↑")),
            ft.DataColumn(ft.Text("Spot")),
            ft.DataColumn(ft.Text("Prêmio Total")),
            ft.DataColumn(ft.Text("Prêmio CALL")),
            ft.DataColumn(ft.Text("Δ CALL")),
            ft.DataColumn(ft.Text("Prêmio PUT")),
            ft.DataColumn(ft.Text("Δ PUT")),
            ft.DataColumn(ft.Text("Vencimento")),
            ft.DataColumn(ft.Text("Lote CALL")),
            ft.DataColumn(ft.Text("Lote PUT")),
            ft.DataColumn(ft.Text("Custo Operação")),
        ],
        rows=[],
        column_spacing=12,
    )

    table.visible = False

    def on_row_select(e, call_symbol, put_symbol):
        try:
            dd_par = getattr(page, "sim_dd_par", None)
            sim_fn = getattr(page, "sim_on_simular", None)
            par_change = getattr(page, "sim_on_par_change", None)
            sim_btn = getattr(page, "sim_btn", None)

            if not dd_par:
                show_snack(page, "Não encontrei o dropdown do simulador (par CALL-PUT).")
                return

            key = f"{call_symbol}|{put_symbol}"
            label = f"{call_symbol} - {put_symbol}"

            have = False
            for opt in (dd_par.options or []):
                if getattr(opt, "key", None) == key:
                    have = True
                    break
            if not have:
                dd_par.options.append(ft.dropdown.Option(text=label, key=key))

            dd_par.value = key
            dd_par.update()

            if callable(par_change):
                par_change(None)

            if sim_btn:
                sim_btn.disabled = False
                sim_btn.update()

            show_snack(page, f"Par carregado: {label}")

            go_sim = getattr(page, "go_simulador", None)
            if callable(go_sim):
                go_sim(None)

            page.update()

            if callable(sim_fn):
                sim_fn(None)
        except Exception as ex:
            show_snack(page, f"Erro ao carregar no simulador: {ex}")

    # ---- SPOT ÚNICO (sempre igual na grade inteira) ----
    def _spot_unico(tkr: str) -> float | None:
        t = (tkr or "").upper().strip()
        # (a) fonte BS do ativo — quando existir no seu projeto (placeholder)
        for fn_name in ("get_spot_ativo_bs", "spot_ativo_bs", "black_scholes_spot"):
            try:
                fn = getattr(__import__("services.api", fromlist=[fn_name]), fn_name)
                v = float(fn(t))
                if v > 0:
                    return round(v, 2)
            except Exception:
                pass
        # (b) fallback: payload das opções — mediana das amostras no maior 'time'
        try:
            from services.api import buscar_opcoes_ativo
            lista = buscar_opcoes_ativo(t)
            xs, ts = [], []
            for r in (lista or []):
                if isinstance(r, dict):
                    sp = r.get("spot_price")
                    tm = r.get("time")
                    if sp is not None:
                        xs.append(float(sp))
                    if tm is not None:
                        ts.append(int(tm))
            if not xs:
                return None
            if ts:
                tmax = max(ts)
                xs = [float(r["spot_price"]) for r in lista
                      if isinstance(r, dict) and r.get("spot_price") is not None and r.get("time") == tmax] or xs
            xs.sort()
            n = len(xs)
            med = xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])
            return round(float(med), 2)
        except Exception:
            return None

    def on_screener(_):
        try:
            t = (tkr.value or "").strip().upper()
            total_lot = _parse_total_lot(lote_total_tf.value, default=10000)

            if not t:
                status.value = "Informe o Ticker."
                output.value = "⚠️ Informe o Ticker e clique em Rodar."
                output.visible = True
                table.rows = []
                page.update()
                return

            def _to_f(v):
                try:
                    return float(v)
                except Exception:
                    return 0.0

            def _fmt2(v):  # 2 casas, decimal com vírgula
                return f"{_to_f(v):.2f}".replace(".", ",")

            def _fmt4(v):  # 4 casas, decimal com vírgula
                return f"{_to_f(v):.4f}".replace(".", ",")

            def _fmt_pct(v):  # percentual com vírgula (v já deve ser %)
                try:
                    return f"{float(v):.2f}%".replace(".", ",")
                except Exception:
                    return ""

            status.value = "Rodando..."
            busy.visible = True
            output.visible = False
            table.rows = []
            page.update()

            # screener ATM com refresh forçado
            res = atualizar_e_screener_atm_2venc(t, refresh=True)
            linhas = (res or {}).get("atm", [])

            # -------- SPOT ÚNICO (prioriza Oplab oficial) --------
            from services.api import get_spot_ativo_oficial
            spot_uni = get_spot_ativo_oficial(t)
            if spot_uni is None:
                # fallback local já existente
                try:
                    spot_uni = _spot_unico(t)
                except Exception:
                    spot_uni = None
            if spot_uni is None and linhas:
                spot_uni = _to_f(linhas[0].get("spot"))
            spot_uni = _to_f(spot_uni) if spot_uni is not None else 0.0
            page.spot_override = spot_uni  # simulador também usa o mesmo spot
            # ------------------------------------------------------

            # ---------- Cálculo D+1 (simulação em memória) ----------
            if dd_horiz.value == "D+1" and linhas:
                from simulacoes.black_scholes import black_scholes, implied_vol
                from services.api import buscar_detalhes_opcao

                def _mid(d: dict) -> float:
                    b = to_float(d.get("bid"));
                    a = to_float(d.get("ask"))
                    if b > 0 and a > 0:
                        return (b + a) / 2.0
                    for k in ("ask", "last", "close", "bid"):
                        v = to_float(d.get(k))
                        if v > 0:
                            return v
                    return 0.0

                def _implied_or_min(preco, S, K, r, T, kind):
                    try:
                        iv = implied_vol(preco, S, K, r, 0.0, T, kind)
                        return max(0.0001, iv) if iv else 0.0001
                    except Exception:
                        return 0.0001

                crush = to_float(tf_crush.value, 10.0)  # %
                f = max(0.0, 1.0 - crush / 100.0)
                r_aa = to_float(os.getenv("SELIC_AA", "10.0")) / 100.0

                for r in linhas:
                    call = r.get("call");
                    put = r.get("put")
                    if not (call and put):
                        continue
                    try:
                        cd = buscar_detalhes_opcao(call)
                        pd = buscar_detalhes_opcao(put)

                        # === SEMPRE o mesmo SPOT ÚNICO ===
                        S = spot_uni if spot_uni is not None else to_float(cd.get("spot_price") or pd.get("spot_price"))
                        Kc = to_float(cd.get("strike"))
                        Kp = to_float(pd.get("strike"))

                        # dias -> T hoje e T-1 dia
                        def _T_days(x):
                            return max(1, int(to_float(x, 1))) / 252.0

                        Tc = _T_days(cd.get("days_to_maturity"))
                        Tp = _T_days(pd.get("days_to_maturity"))
                        Tc1 = max(Tc - 1 / 252.0, 1e-6)
                        Tp1 = max(Tp - 1 / 252.0, 1e-6)

                        # preço de mercado hoje (para inferir IV)
                        Pc_mkt = _mid(cd)
                        Pp_mkt = _mid(pd)

                        # IV hoje (inferida) e IV com crush
                        sig_c = _implied_or_min(Pc_mkt, S, Kc, r_aa, Tc, "CALL")
                        sig_p = _implied_or_min(Pp_mkt, S, Kp, r_aa, Tp, "PUT")
                        sig_c1 = max(1e-4, sig_c * f)
                        sig_p1 = max(1e-4, sig_p * f)

                        # preço teórico D+1
                        Pc1 = black_scholes(S, Kc, r_aa, 0.0, sig_c1, Tc1, "CALL")["preco"]
                        Pp1 = black_scholes(S, Kp, r_aa, 0.0, sig_p1, Tp1, "PUT")["preco"]

                        r["call_premio"] = Pc1
                        r["put_premio"] = Pp1
                        r["premium_total"] = Pc1 + Pp1
                        r["be_down"] = round(Kp - (Pc1 + Pp1), 4)
                        r["be_up"] = round(Kc + (Pc1 + Pp1), 4)
                        r["spot"] = S  # guardo no dict, mas exibiremos spot_uni na grade
                        # BE% será calculado de forma unificada no make_row a partir de spot_uni
                    except Exception:
                        continue
            # ---------- Fim D+1 ----------

            if not linhas:
                output.value = "Nenhuma linha ATM encontrada."
                output.visible = True
                busy.visible = False
                status.value = ""
                page.update()
                return

            def _round_lots(call_raw, put_raw, lot_min, total):
                c = int(call_raw // lot_min) * lot_min
                p = int(put_raw // lot_min) * lot_min
                rem = total - (c + p)
                while rem >= lot_min:
                    frac_c = (call_raw - c)
                    frac_p = (put_raw - p)
                    if frac_c >= frac_p:
                        c += lot_min
                    else:
                        p += lot_min
                    rem -= lot_min
                return c, p

            def make_row(r):
                call = r.get("call", "")
                put = r.get("put", "")

                delta_c = r.get("call_delta")
                delta_p = r.get("put_delta")

                w_call = abs(float(delta_p)) if delta_p is not None else None
                w_put = abs(float(delta_c)) if delta_c is not None else None

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

                raw_call = total_lot * (w_call / soma)
                raw_put = total_lot - raw_call

                qty_call, qty_put = _round_lots(raw_call, raw_put, LOT_MIN, total_lot)

                def _fmt_money(v):
                    try:
                        s = f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        return f"R$ {s}"
                    except Exception:
                        return "R$ 0,00"

                call_premio = _to_f(r.get("call_premio"))
                put_premio = _to_f(r.get("put_premio"))
                custo_oper = qty_call * call_premio + qty_put * put_premio

                # --- %BE calculados SEMPRE contra o mesmo spot_uni ---
                be_down_val = r.get("be_down")
                be_up_val = r.get("be_up")
                if spot_uni and spot_uni > 0:
                    # preserva o sinal: %BE↓ negativo, %BE↑ positivo
                    be_pct_down_show = ((be_down_val / spot_uni) - 1.0) * 100.0 if be_down_val is not None else None
                    be_pct_up_show = ((be_up_val / spot_uni) - 1.0) * 100.0 if be_up_val is not None else None
                else:
                    be_pct_down_show = None
                    be_pct_up_show = None

                return ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text("ATM")),
                        ft.DataCell(ft.Text(call)),
                        ft.DataCell(ft.Text(put)),
                        ft.DataCell(ft.Text(_fmt2(r.get("strike")))),

                        # ATENÇÃO: ajuste os cabeçalhos para bater com a ordem abaixo
                        # [%BE↓, BE↓, %BE↑, BE↑]
                        ft.DataCell(ft.Text(_fmt_pct(be_pct_down_show) if be_pct_down_show is not None else "")),
                        ft.DataCell(ft.Text(_fmt2(be_down_val))),
                        ft.DataCell(ft.Text(_fmt_pct(be_pct_up_show) if be_pct_up_show is not None else "")),
                        ft.DataCell(ft.Text(_fmt2(be_up_val))),

                        ft.DataCell(ft.Text(_fmt2(spot_uni))),
                        ft.DataCell(ft.Text(_fmt4(r.get("premium_total")))),
                        ft.DataCell(ft.Text(_fmt4(r.get("call_premio")))),
                        ft.DataCell(ft.Text(_fmt4(delta_c) if delta_c is not None else "")),
                        ft.DataCell(ft.Text(_fmt4(r.get("put_premio")))),
                        ft.DataCell(ft.Text(_fmt4(delta_p) if delta_p is not None else "")),
                        ft.DataCell(ft.Text(r.get("due_date", ""))),
                        ft.DataCell(
                            ft.Text(f"{int(qty_call):,}".replace(",", "X").replace(".", ",").replace("X", "."))),
                        ft.DataCell(ft.Text(f"{int(qty_put):,}".replace(",", "X").replace(".", ",").replace("X", "."))),
                        ft.DataCell(ft.Text(_fmt_money(custo_oper))),
                    ],
                    on_select_changed=lambda e, c=call, p=put: on_row_select(e, c, p),
                )

            safe_rows = []
            for r in linhas:
                try:
                    row = make_row(r)
                    if row is not None:
                        safe_rows.append(row)
                except Exception as ex:
                    print(f"[ROW] ignorada {r.get('call')}|{r.get('put')} -> {ex}", flush=True)
            table.rows = safe_rows

            table.visible = True

            # Preencher dropdown único com os pares CALL - PUT (Option com key/text)
            pares_opts = []
            for r in linhas:
                call = r.get("call")
                put = r.get("put")
                if call and put:
                    key = f"{call}|{put}"
                    text = f"{call} - {put}"
                    pares_opts.append(ft.dropdown.Option(text=text, key=key))

            uniq = {}
            for opt in pares_opts:
                k = getattr(opt, "key", None) or getattr(opt, "text", None)
                if k not in uniq:
                    uniq[k] = opt
            pares_opts = list(uniq.values())

            if hasattr(page, "sim_dd_par"):
                page.sim_dd_par.options = pares_opts
                page.sim_dd_par.value = None
                page.sim_dd_par.update()

            busy.visible = False
            status.value = f"{len(linhas)} linhas ATM (2 vencimentos)."
            page.update()

        except Exception as ex:
            busy.visible = False
            status.value = ""
            show_snack(page, f"Erro no screener ATM: {ex}")
            page.update()

    # <<-- AQUI TERMINA o try/except do on_screener -->>


    # botão para rodar o screener
    btn_rodar = ft.FilledButton("Rodar screener", icon="search", on_click=on_screener)

    # retorno da UI do screener (sem isso a função retorna None e quebra a app)
    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Screener de Long Straddle", size=18),
                ft.Text("Informe Ticker para listar pares CALL/PUT e o Lote Total (múltiplo de 100).", size=12),
                ft.Row([tkr, lote_total_tf, dd_horiz, tf_crush, tf_venc], spacing=10),
                ft.Row([btn_rodar], spacing=10),
                status,
                busy,
                ft.Divider(),
                ft.Text("Resultado"),
                table,
                output,
            ],
            spacing=14
        ),
        padding=20,
        border_radius=12,
    )

# -------------- App --------------
def main(page):
    page.title = "Simulador & Screener — Long Straddle"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 16
    page.appbar = ft.AppBar(title=ft.Text("Simulador & Screener — Long Straddle"))
    page.scroll = ft.ScrollMode.AUTO

    simulador_panel = build_simulador_panel(page)
    screener_panel  = build_screener_panel(page)

    # começa no Screener
    simulador_panel.visible = False

    def show_simulador(_):
        print("[menu] Simulador", flush=True)
        simulador_panel.visible = True
        screener_panel.visible  = False
        page.update()

    def show_screener(_):
        print("[menu] Screener", flush=True)
        simulador_panel.visible = False
        screener_panel.visible  = True
        page.update()

    # Expor handlers de navegação
    page.go_simulador = show_simulador
    page.go_screener  = show_screener

    menu = ft.Row(
        controls=[
            ft.FilledTonalButton("Screener",  icon="search",     on_click=show_screener),
            ft.FilledTonalButton("Simulador", icon="show_chart", on_click=show_simulador),
        ],
        spacing=10
    )

    page.add(menu, screener_panel, simulador_panel)

if __name__ == "__main__":
    ft.app(target=main)
