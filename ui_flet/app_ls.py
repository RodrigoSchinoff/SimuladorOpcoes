import flet as ft
from flet.matplotlib_chart import MatplotlibChart
from typing import Dict, Any, List
import traceback

from services.api import buscar_detalhes_opcao
from simulacoes.long_straddle import simular_long_straddle

CALLS_FIXAS = ["CMIGI119"]
PUTS_FIXAS  = ["CMIGU119"]

# --------- helpers locais (robustos) ---------
def show_snack(page: ft.Page, msg: str):
    page.snack_bar = ft.SnackBar(ft.Text(msg))
    page.snack_bar.open = True
    page.update()

def to_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default

def preco_compra_premio(leg: Dict[str, Any]) -> float:
    # preferir ASK; fallback em LAST/CLOSE/BID
    ask  = to_float(leg.get("ask"))
    last = to_float(leg.get("last"))
    close= to_float(leg.get("close"))
    bid  = to_float(leg.get("bid"))
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
    # Caso sua simulação não retorne dict, calculamos aqui o essencial
    strike_call = to_float(call.get("strike"))
    strike_put  = to_float(put.get("strike"))
    premio_call = preco_compra_premio(call)
    premio_put  = preco_compra_premio(put)
    cs          = int(to_float(call.get("contract_size") or put.get("contract_size") or 100, 100)) or 100
    spot        = to_float(call.get("spot_price") or put.get("spot_price"))
    venc        = call.get("due_date") or put.get("due_date") or ""

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

def make_figure_from_result(res: Dict[str, Any], call_symbol: str, put_symbol: str):
    # tamanho menor e DPI mais alto (melhor legibilidade)
    from matplotlib.figure import Figure
    import math

    FIG_W, FIG_H, DPI = 6.5, 4.0, 120
    fig = Figure(figsize=(FIG_W, FIG_H), dpi=DPI)
    ax = fig.add_subplot(111)

    precos = res["precos"]
    payoff = res["payoff"]
    ax.plot(precos, payoff, label="P&L")
    ax.axhline(0, color="black", linestyle="--", linewidth=1)

    def safe_vline(x, **kw):
        if x is None:
            return
        try:
            if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
                return
        except Exception:
            return
        ax.axvline(x, **kw)

    safe_vline(res.get("spot"),     color="orange", linestyle="-",  linewidth=1, label="Preço do Ativo (Atual)")
    safe_vline(res.get("be_down"),  color="green",  linestyle="--", linewidth=1, label="BE Inferior")
    safe_vline(res.get("be_up"),    color="blue",   linestyle="--", linewidth=1, label="BE Superior")

    titulo = f"{res.get('estrategia','Long Straddle')} – {call_symbol} / {put_symbol}"
    venc   = res.get("vencimento")
    if venc: titulo += f" – Venc.: {venc}"
    ax.set_title(titulo, fontsize=12)
    ax.set_xlabel("Preço do Ativo", fontsize=10)
    ax.set_ylabel("Resultado (R$)", fontsize=10)
    ax.tick_params(labelsize=9)
    ax.grid(True, alpha=0.3)

    if payoff:
        y_min, y_max = min(payoff), max(payoff)
        if y_min == y_max:
            y_min -= 1.0; y_max += 1.0
        pad = (y_max - y_min) * 0.10 or 1.0
        ax.set_ylim(y_min - pad, y_max + pad)

    ax.legend(fontsize=9)
    fig.tight_layout()
    return fig

# --------- app ---------
def main(page: ft.Page):
    page.title = "Simulador de Opções — Long Straddle (minimal)"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.scroll = "auto"

    dd_call = ft.Dropdown(label="CALL", options=[ft.dropdown.Option(v) for v in CALLS_FIXAS], value=CALLS_FIXAS[0], width=300)
    dd_put  = ft.Dropdown(label="PUT",  options=[ft.dropdown.Option(v) for v in PUTS_FIXAS],  value=PUTS_FIXAS[0],  width=300)

    status_txt = ft.Text("", size=12)
    #chart_container = ft.Container()
    chart_container = ft.Container(width=620, height=350)  # ajuste se quiser

    def set_busy(b: bool):
        btn_simular.disabled = b
        page.update()

    def on_simular(_):
        call_symbol = dd_call.value
        put_symbol = dd_put.value
        if not call_symbol or not put_symbol:
            page.snack_bar = ft.SnackBar(ft.Text("Selecione uma CALL e uma PUT."))
            page.snack_bar.open = True
            page.update()
            return

        btn_simular.disabled = True
        status_txt.value = f"Simulando {call_symbol} x {put_symbol}..."
        page.update()
        try:
            # 1) buscar dados completos das opções
            call = buscar_detalhes_opcao(call_symbol)
            put = buscar_detalhes_opcao(put_symbol)

            # 2) simular SEM abrir janela do Matplotlib
            try:
                res = simular_long_straddle(call, put, renderizar=False)
            except TypeError:
                res = simular_long_straddle(call, put)

            # 3) criar a Figure “headless” com tamanho menor
            from viz.payoff import plotar_payoff
            fig, _ = plotar_payoff(
                res["precos"],
                res["payoff"],
                res.get("spot"),
                res.get("be_down"),
                res.get("be_up"),
                call.get("symbol", ""),
                put.get("symbol", ""),
                res.get("vencimento", ""),
                estrategia_nome=res.get("estrategia", "Long Straddle"),
                mostrar=False,  # <- NÃO abre janela
                fig_size=(5.0, 3.0),  # <- menor
                dpi=120,
                font_scale=0.85
            )

            # 4) embutir no container (sem expand)
            from flet.matplotlib_chart import MatplotlibChart
            chart_container.content = ft.Container(
                content=MatplotlibChart(fig),
                width=620, height=350, padding=0
            )

            status_txt.value = "Simulação concluída."
            page.update()
        except Exception as e:
            status_txt.value = ""
            page.snack_bar = ft.SnackBar(ft.Text(f"Erro: {e}"))
            page.snack_bar.open = True
            page.update()
        finally:
            btn_simular.disabled = False
            page.update()

    btn_simular = ft.ElevatedButton("Simular Long Straddle", icon="show_chart", on_click=on_simular)

    page.add(
        ft.AppBar(title=ft.Text("Long Straddle — Seleção rápida")),
        ft.Text("Selecione uma CALL e uma PUT e clique em Simular.", size=14),
        ft.Row([dd_call, dd_put], alignment=ft.MainAxisAlignment.START),
        ft.Row([btn_simular]),
        status_txt,
        chart_container,
    )

if __name__ == "__main__":
    import sys
    if "--web" in sys.argv:
        ft.app(target=main, view=ft.WEB_BROWSER)
    else:
        ft.app(target=main)
