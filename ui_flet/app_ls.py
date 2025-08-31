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

import traceback  # <-- ADICIONE ESTA LINHA

from services.api import buscar_detalhes_opcao
from simulacoes.long_straddle import simular_long_straddle
#from core.app_core import atualizar_e_screener_ls
from core.app_core import atualizar_e_screener_ls, atualizar_e_screener_atm_2venc

# from repositories.opcoes_repo import listar_vencimentos  # se quiser usar depois

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

def fmt_pct(x) -> str:
    try:    return f"{float(x):.2f}%".replace(".", ",")
    except: return "0,00%"

def fmt_brl(x) -> str:
    try:
        s = f"{float(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {s}"
    except:
        return "R$ 0,00"

# -------------- Painel: Simulador --------------
def build_simulador_panel(page):
    # Dropdowns SEM opções fixas; serão preenchidos pelo screener
    dd_call = ft.Dropdown(label="CALL", options=[], value=None, width=280)
    dd_put  = ft.Dropdown(label="PUT",  options=[], value=None, width=280)

    # Expor referências para outras partes da app (screener usa isso)
    page.sim_dd_call = dd_call
    page.sim_dd_put  = dd_put

    status_txt = ft.Text("", size=12)
    chart_container = ft.Container(width=700, height=380, padding=10, border_radius=12)

    def on_simular(_):
        call_symbol = dd_call.value
        put_symbol  = dd_put.value
        if not call_symbol or not put_symbol:
            show_snack(page, "Selecione uma CALL e uma PUT.")
            return

        print("[simulador] clicou simular", flush=True)
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

    # Botão começa desabilitado; o screener habilita quando preencher os dropdowns
    btn_simular = ft.FilledButton("Simular Long Straddle", icon="show_chart", on_click=on_simular, disabled=True)

    # Expor o handler para ser chamado pelo screener (se você desejar auto-simular)
    page.sim_on_simular = on_simular

    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Simulador Long Straddle", size=18),
                ft.Text("Escolha uma CALL e uma PUT e visualize o payoff.", size=12),
                ft.Row([dd_call, dd_put], spacing=12),
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

    tkr = ft.TextField(label="Ticker (ex.: PETR4)", width=220)

    # DatePicker
    dp = ft.DatePicker(first_date=date(2020, 1, 1), last_date=date(2035, 12, 31))
    if dp not in page.overlay:
        page.overlay.append(dp)
        page.update()

    tf_venc = ft.TextField(label="Vencimento", width=220, read_only=True, hint_text="YYYY-MM-DD")
    _H = 48
    _PAD = ft.padding.only(left=12, right=12, top=12, bottom=12)

    #tkr = ft.TextField(label="Ticker (ex.: PETR4)", width=220, height=_H, content_padding=_PAD)

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

    # >>> ADIÇÃO: área de saída onde o screener será listado
    # antes era: output = ft.Text(value="Resultados aparecerão aqui.\n", selectable=True)
    output = ft.Text(value="", selectable=True, visible=False)  # fica oculto; uso só para mensagens de erro

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

            # --- NOVAS COLUNAS ---
            ft.DataColumn(ft.Text("Prêmio CALL")),
            ft.DataColumn(ft.Text("Δ CALL")),
            ft.DataColumn(ft.Text("Prêmio PUT")),
            ft.DataColumn(ft.Text("Δ PUT")),
            # ----------------------

            ft.DataColumn(ft.Text("Vencimento")),
        ],
        rows=[],
        column_spacing=12,

    )
    table.visible = False

    # [PATCH-4] handler: carrega CALL/PUT da linha no simulador e troca de painel
    def on_row_select(e, call_symbol, put_symbol):
        try:
            dd_call = getattr(page, "sim_dd_call", None)
            dd_put = getattr(page, "sim_dd_put", None)
            sim_fn = getattr(page, "sim_on_simular", None)  # <- handler do simulador, exposto no build_simulador_panel

            if not (dd_call and dd_put):
                show_snack(page, "Não encontrei os campos do simulador.")
                return

            # garante que os valores existam nas opções do Dropdown
            def ensure_option(dd, val):
                if not val:
                    return
                existing = []
                for opt in dd.options:
                    k = getattr(opt, "key", None)
                    if k is None:
                        k = getattr(opt, "text", None)
                    existing.append(k)
                if val not in existing:
                    dd.options.append(ft.dropdown.Option(val))
                dd.value = val
                dd.update()

            ensure_option(dd_call, call_symbol)
            ensure_option(dd_put, put_symbol)

            show_snack(page, f"CALL {call_symbol} e PUT {put_symbol} carregadas no simulador.")

            # alterna para o painel do simulador (se exposto em page.go_simulador)
            go_sim = getattr(page, "go_simulador", None)
            if callable(go_sim):
                go_sim(None)

            # garante que a UI reflita os valores antes de simular
            page.update()

            # dispara a simulação automaticamente (se exposta em page.sim_on_simular)
            if callable(sim_fn):
                sim_fn(None)
            else:
                show_snack(page, "Clique em 'Simular Long Straddle' para rodar.")

        except Exception as ex:
            show_snack(page, f"Erro ao carregar no simulador: {ex}")

    def on_screener(_):
        try:
            t = (tkr.value or "").strip().upper()
            print(f"[screener] Rodar screener ATM (2 vencimentos): t={t}", flush=True)

            if not t:
                status.value = "Informe o Ticker."
                output.value = "⚠️ Informe o Ticker e clique em Rodar."
                output.visible = True
                table.rows = []
                page.update()
                return

            # helpers locais (padrão BR: vírgula como separador decimal)
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

            # NOVO: screener ATM (2 próximos vencimentos)
            res = atualizar_e_screener_atm_2venc(t)
            linhas = (res or {}).get("atm", [])
            if not linhas:
                output.value = "Nenhuma linha ATM encontrada."
                output.visible = True
                busy.visible = False
                status.value = ""
                page.update()
                return

            def make_row(r):
                call = r.get("call", "")
                put = r.get("put", "")

                # helpers com vírgula como separador decimal
                def _to_f(v):
                    try:
                        return float(v)
                    except Exception:
                        return 0.0

                def _fmt2(v):  # 2 casas, usa vírgula
                    return f"{_to_f(v):.2f}".replace(".", ",")

                def _fmt4(v):  # 4 casas, usa vírgula
                    return f"{_to_f(v):.4f}".replace(".", ",")

                def _fmt_pct(v):  # percentual com vírgula
                    try:
                        return f"{float(v):.2f}".replace(".", ",") + "%"
                    except Exception:
                        return ""

                return ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text("ATM")),  # Bucket
                        ft.DataCell(ft.Text(call)),  # CALL
                        ft.DataCell(ft.Text(put)),  # PUT
                        ft.DataCell(ft.Text(_fmt2(r.get("strike")))),  # Strike (R$)
                        ft.DataCell(ft.Text(_fmt_pct(r.get("be_pct")))),  # BE%
                        ft.DataCell(ft.Text(_fmt2(r.get("be_down")))),  # BE↓ (R$)
                        ft.DataCell(ft.Text(_fmt2(r.get("be_up")))),  # BE↑ (R$)
                        ft.DataCell(ft.Text(_fmt2(r.get("spot")))),  # Spot (R$)
                        ft.DataCell(ft.Text(_fmt4(r.get("premium_total")))),  # Prêmio Total (R$)

                        # Novas colunas (também com vírgula)
                        ft.DataCell(ft.Text(_fmt4(r.get("call_premio")))),  # Prêmio CALL (R$)
                        ft.DataCell(ft.Text(_fmt4(r.get("call_delta")) if r.get("call_delta") is not None else "")),
                        # Δ CALL
                        ft.DataCell(ft.Text(_fmt4(r.get("put_premio")))),  # Prêmio PUT (R$)
                        ft.DataCell(ft.Text(_fmt4(r.get("put_delta")) if r.get("put_delta") is not None else "")),
                        # Δ PUT

                        ft.DataCell(ft.Text(r.get("due_date", ""))),  # Vencimento
                    ],
                    on_select_changed=lambda e, c=call, p=put: on_row_select(e, c, p),
                )

            table.rows = [make_row(r) for r in linhas]
            table.visible = True

            # Preencher dropdowns com as opções retornadas pelo screener (sem fixos)
            calls_opts = sorted({r["call"] for r in linhas if r.get("call")})
            puts_opts = sorted({r["put"] for r in linhas if r.get("put")})

            page.sim_dd_call.options = [ft.dropdown.Option(s) for s in calls_opts]
            page.sim_dd_put.options = [ft.dropdown.Option(s) for s in puts_opts]

            # (opcional) selecionar a primeira combinação como padrão
            # if calls_opts and puts_opts:
            #     page.sim_dd_call.value = calls_opts[0]
            #     page.sim_dd_put.value  = puts_opts[0]

            btn_simular.disabled = False
            dropdowns_enable(True)

            busy.visible = False
            status.value = f"{len(linhas)} linhas ATM (2 vencimentos)."
            page.update()


        except Exception as ex:
            busy.visible = False
            status.value = ""
            show_snack(page, f"Erro no screener ATM: {ex}")
            page.update()

    #btn_screener = ft.FilledButton("Selecionar data", icon="event", on_click=abrir_calendario)
    btn_rodar     = ft.FilledButton("Rodar screener", icon="search", on_click=on_screener)

    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Screener de Long Straddle", size=18),
                ft.Text("Informe Ticker para listar pares CALL/PUT.", size=12),
                ft.Row([tkr, tf_venc], spacing=10),           # ambos 220px
                #ft.Row([btn_screener, btn_rodar], spacing=10),
                ft.Row([btn_rodar], spacing=10),
                status,
                busy,
                ft.Divider(),
                ft.Text("Resultado"),
                # >>> ADIÇÃO: exibição do resultado
                table,  # aparece só com dados
                output,  # aparece só p/ mensagens
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
    #screener_panel.visible = False  # começa no simulador
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
