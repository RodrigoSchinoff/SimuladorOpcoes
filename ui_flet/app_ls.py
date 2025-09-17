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
        return float(v) if v is not None else default
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
    # Dropdown ÚNICO de pares CALL - PUT (o screener preenche)
    dd_par = ft.Dropdown(label="Par CALL - PUT", options=[], value=None, width=420)

    status_txt = ft.Text("", size=12)
    chart_container = ft.Container(width=700, height=380, padding=10, border_radius=12)

    def on_simular(_):
        if not dd_par.value:
            show_snack(page, "Selecione um par de opções (CALL - PUT).")
            return

        # dd_par.value vem como "CALLSYM - PUTSYM" (texto do option)
        try:
            call_symbol, put_symbol = [s.strip() for s in dd_par.value.split(" - ", 1)]
        except Exception:
            show_snack(page, "Par inválido. Re-selecione um par CALL - PUT.")
            return

        print(f"[simulador] clicou simular: {call_symbol} x {put_symbol}", flush=True)
        btn_simular.disabled = True
        status_txt.value = f"Simulando {call_symbol} × {put_symbol}..."
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

    # Botão começa desabilitado; habilita quando escolher um par
    btn_simular = ft.FilledButton("Simular Long Straddle", icon="show_chart", on_click=on_simular, disabled=True)

    page.sim_dd_par = dd_par
    page.sim_on_simular = on_simular
    page.sim_btn = btn_simular  # <-- importante para habilitar via screener

    # Habilitar/desabilitar ao selecionar par
    def habilitar_botao(_):
        btn_simular.disabled = not bool(dd_par.value)
        page.update()

    dd_par.on_change = habilitar_botao

    # Expor referências para o screener e para outros handlers
    page.sim_dd_par = dd_par
    page.sim_on_simular = on_simular

    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Simulador Long Straddle", size=18),
                ft.Text("Escolha um par de opções CALL - PUT e visualize o payoff.", size=12),
                dd_par,
                btn_simular,
                status_txt,
                chart_container,
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
        print("[screener] abrir_calendario()", flush=True)
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
        print(f"[screener] on_date_change value={dp.value}", flush=True)
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
            ft.DataColumn(ft.Text("BE%")),
            ft.DataColumn(ft.Text("BE↓")),
            ft.DataColumn(ft.Text("BE↑")),
            ft.DataColumn(ft.Text("Spot")),
            ft.DataColumn(ft.Text("Prêmio Total")),
            ft.DataColumn(ft.Text("Prêmio CALL")),
            ft.DataColumn(ft.Text("Δ CALL")),
            ft.DataColumn(ft.Text("Prêmio PUT")),
            ft.DataColumn(ft.Text("Δ PUT")),
            ft.DataColumn(ft.Text("Vencimento")),
            # --- NOVAS COLUNAS (clean) ---
            ft.DataColumn(ft.Text("Lote CALL")),
            ft.DataColumn(ft.Text("Lote PUT")),
            ft.DataColumn(ft.Text("Custo Operação")),

        ],
        rows=[],
        column_spacing=12,
    )

    table.visible = False

    # Carrega o par no simulador ao selecionar linha
    def on_row_select(e, call_symbol, put_symbol):
        try:
            dd_par = getattr(page, "sim_dd_par", None)
            sim_fn = getattr(page, "sim_on_simular", None)

            if not dd_par:
                show_snack(page, "Não encontrei o dropdown do simulador (par CALL-PUT).")
                return

            label = f"{call_symbol} - {put_symbol}"

            # garantir que a opção exista (Option(text))
            existing_texts = [getattr(opt, "text", None) for opt in (dd_par.options or [])]
            if label not in existing_texts:
                dd_par.options.append(ft.dropdown.Option(label))

            dd_par.value = label
            dd_par.update()

            # habilita botão programaticamente (sem depender de on_change)
            sim_btn = getattr(page, "sim_btn", None)
            if sim_btn:
                sim_btn.disabled = False
                sim_btn.update()

            show_snack(page, f"Par carregado no simulador: {label}")

            go_sim = getattr(page, "go_simulador", None)
            if callable(go_sim):
                go_sim(None)

            page.update()

            if callable(sim_fn):
                sim_fn(None)
            else:
                show_snack(page, "Clique em 'Simular Long Straddle' para rodar.")
        except Exception as ex:
            show_snack(page, f"Erro ao carregar no simulador: {ex}")

    def on_screener(_):
        try:
            t = (tkr.value or "").strip().upper()
            total_lot = _parse_total_lot(lote_total_tf.value, default=10000)

            print(f"[screener] Rodar screener ATM (2 vencimentos): t={t}, total_lot={total_lot}", flush=True)

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

            def _fmt_pct(v):  # percentual com vírgula
                try:
                    return f"{float(v):.2f}%".replace(".", ",")
                except Exception:
                    return ""

            status.value = "Rodando..."
            busy.visible = True
            output.visible = False
            table.rows = []
            page.update()

            # screener ATM (2 próximos vencimentos)
            from core.app_core import atualizar_e_screener_atm_2venc
            res = atualizar_e_screener_atm_2venc(t)
            linhas = (res or {}).get("atm", [])
            if not linhas:
                output.value = "Nenhuma linha ATM encontrada."
                output.visible = True
                busy.visible = False
                status.value = ""
                page.update()
                return

            def _round_lots(call_raw, put_raw, lot_min, total):
                # arredonda para baixo para múltiplos de lot_min
                c = int(call_raw // lot_min) * lot_min
                p = int(put_raw  // lot_min) * lot_min
                rem = total - (c + p)
                # distribui o restante (em blocos de lot_min) para quem tiver maior fração pendente
                while rem >= lot_min:
                    frac_c = (call_raw - c)
                    frac_p = (put_raw  - p)
                    if frac_c >= frac_p:
                        c += lot_min
                    else:
                        p += lot_min
                    rem -= lot_min
                return c, p

            def make_row(r):
                call = r.get("call", "")
                put  = r.get("put", "")

                # deltas podem vir None; tratamos
                delta_c = r.get("call_delta")
                delta_p = r.get("put_delta")

                # pesos pelos deltas (valor absoluto)
                w_call = abs(float(delta_p)) if delta_p is not None else None
                w_put  = abs(float(delta_c)) if delta_c is not None else None

                # fallback de pesos se deltas ausentes/zero
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
                raw_put  = total_lot - raw_call

                qty_call, qty_put = _round_lots(raw_call, raw_put, LOT_MIN, total_lot)

                def _fmt_money(v):
                    try:
                        s = f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        return f"R$ {s}"
                    except Exception:
                        return "R$ 0,00"

                call_premio = _to_f(r.get("call_premio"))
                put_premio = _to_f(r.get("put_premio"))
                # Se seus prêmios forem "por contrato (100)", use:
                # custo_oper = (qty_call/100) * call_premio + (qty_put/100) * put_premio
                custo_oper = qty_call * call_premio + qty_put * put_premio

                def _fmt2l(v):
                    # inteiro com separador de milhar BR
                    try:
                        return f"{int(v):,}".replace(",", "X").replace(".", ",").replace("X", ".")
                    except Exception:
                        return "0"

                def _fmt2(v):
                    return f"{_to_f(v):.2f}".replace(".", ",")

                def _fmt4(v):
                    return f"{_to_f(v):.4f}".replace(".", ",")

                def _fmt_pct2(v):
                    try:
                        return f"{float(v):.2f}".replace(".", ",") + "%"
                    except Exception:
                        return ""

                return ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text("ATM")),
                        ft.DataCell(ft.Text(call)),
                        ft.DataCell(ft.Text(put)),
                        ft.DataCell(ft.Text(_fmt2(r.get("strike")))),
                        ft.DataCell(
                            ft.Text(_fmt_pct(v := r.get("be_pct")) if (v := r.get("be_pct")) is not None else "")),
                        # opcional
                        ft.DataCell(ft.Text(_fmt2(r.get("be_down")))),
                        ft.DataCell(ft.Text(_fmt2(r.get("be_up")))),
                        ft.DataCell(ft.Text(_fmt2(r.get("spot")))),
                        ft.DataCell(ft.Text(_fmt4(r.get("premium_total")))),
                        ft.DataCell(ft.Text(_fmt4(r.get("call_premio")))),
                        ft.DataCell(ft.Text(_fmt4(delta_c) if delta_c is not None else "")),
                        ft.DataCell(ft.Text(_fmt4(r.get("put_premio")))),
                        ft.DataCell(ft.Text(_fmt4(delta_p) if delta_p is not None else "")),
                        ft.DataCell(ft.Text(r.get("due_date", ""))),
                        # --- NOVAS CÉLULAS (somente os dois lotes) ---
                        ft.DataCell(ft.Text(_fmt2l(qty_call))),
                        ft.DataCell(ft.Text(_fmt2l(qty_put))),
                        ft.DataCell(ft.Text(_fmt_money(custo_oper))),

                    ],
                    on_select_changed=lambda e, c=call, p=put: on_row_select(e, c, p),
                )

            table.rows = [make_row(r) for r in linhas]
            table.visible = True

            # ---- Preencher dropdown único com os pares CALL - PUT (Option(text)) ----
            # ---- Preencher dropdown único com os pares CALL - PUT (Option(text)) ----
            labels = []
            for r in linhas:
                call = r.get("call")
                put = r.get("put")
                if call and put:
                    labels.append(f"{call} - {put}")

            labels = sorted(set(labels))
            print(f"[screener] pares encontrados: {len(labels)}", flush=True)

            if hasattr(page, "sim_dd_par"):
                page.sim_dd_par.options = [ft.dropdown.Option(lbl) for lbl in labels]
                # NÃO pré-seleciona: deixa em branco para forçar a escolha do usuário
                page.sim_dd_par.value = None
                page.sim_dd_par.update()
            # ------------------------------------------------------------------------

            busy.visible = False
            status.value = f"{len(linhas)} linhas ATM (2 vencimentos)."
            page.update()

        except Exception as ex:
            busy.visible = False
            status.value = ""
            show_snack(page, f"Erro no screener ATM: {ex}")
            page.update()

    btn_rodar = ft.FilledButton("Rodar screener", icon="search", on_click=on_screener)

    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Screener de Long Straddle", size=18),
                ft.Text("Informe Ticker para listar pares CALL/PUT e o Lote Total (múltiplo de 100).", size=12),
                ft.Row([tkr, lote_total_tf, tf_venc], spacing=10),
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
