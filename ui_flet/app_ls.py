# ui_flet/app_ls.py
import os
os.environ.setdefault("MPLBACKEND", "Agg")  # garante backend headless no servidor

import flet as ft
from typing import Dict, Any, List

from services.api import buscar_detalhes_opcao
from simulacoes.long_straddle import simular_long_straddle

CALLS_FIXAS = ["CMIGI119"]
PUTS_FIXAS  = ["CMIGU119"]

# --------- helpers ---------
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
    # para COMPRA priorize ASK; fallback LAST/CLOSE/BID (LAST pode não existir, mas não quebra)
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
    if centro <= 0:
        centro = 10.0
    pmin = max(0.0, centro * (1 - largura))
    pmax = centro * (1 + largura)
    passo = (pmax - pmin) / (n_pontos - 1)
    return [round(pmin + i * passo, 2) for i in range(n_pontos)]

def fallback_res(call: Dict[str, Any], put: Dict[str, Any]) -> Dict[str, Any]:
    # Caso a simulação não retorne dict, calculamos o essencial aqui
    strike_call = to_float(call.get("strike"))
    strike_put  = to_float(put.get("strike"))
    premio_call = preco_compra_premio(call)
    premio_put  = preco_compra_premio(put)
    # CORRIGIDO: removeu "base" indevida do int(...)
    cs_raw = call.get("contract_size") or put.get("contract_size") or 100
    cs = int(to_float(cs_raw) or 100)
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

# --------- app ---------
def main(page: ft.Page):
    page.title = "Simulador de Opções — Long Straddle (web)"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.scroll = ft.ScrollMode.AUTO
    page.appbar = ft.AppBar(title=ft.Text("Long Straddle — Seleção rápida"))

    dd_call = ft.Dropdown(
        label="CALL",
        options=[ft.dropdown.Option(v) for v in CALLS_FIXAS],
        value=CALLS_FIXAS[0],
        width=300
    )
    dd_put  = ft.Dropdown(
        label="PUT",
        options=[ft.dropdown.Option(v) for v in PUTS_FIXAS],
        value=PUTS_FIXAS[0],
        width=300
    )

    status_txt = ft.Text("", size=12)
    chart_container = ft.Container(width=620, height=350)

    def on_simular(_):
        call_symbol = dd_call.value
        put_symbol = dd_put.value
        if not call_symbol or not put_symbol:
            show_snack(page, "Selecione uma CALL e uma PUT.")
            return

        btn_simular.disabled = True
        status_txt.value = f"Simulando {call_symbol} x {put_symbol}..."
        page.update()

        try:
            # 1) Buscar dados completos
            call = buscar_detalhes_opcao(call_symbol)
            put  = buscar_detalhes_opcao(put_symbol)

            # 2) Simular SEM abrir janela do Matplotlib
            try:
                res = simular_long_straddle(call, put, renderizar=False)
            except TypeError:
                res = simular_long_straddle(call, put)
            except Exception:
                # fallback robusto
                res = fallback_res(call, put)

            # 3) Criar figura headless (via seu viz/payoff)
            from viz.payoff import plotar_payoff  # importa só aqui
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
                mostrar=False,
                fig_size=(5.0, 3.0),
                dpi=120,
                font_scale=0.85
            )

            # 4) Embutir figura no Flet (import aqui garante MPLBACKEND já setado)
            from flet.matplotlib_chart import MatplotlibChart
            chart_container.content = ft.Container(
                content=MatplotlibChart(fig),
                width=620, height=350, padding=0
            )

            status_txt.value = "Simulação concluída."
            page.update()

        except Exception as e:
            status_txt.value = ""
            show_snack(page, f"Erro: {e}")

        finally:
            btn_simular.disabled = False
            page.update()

    btn_simular = ft.ElevatedButton("Simular Long Straddle", icon="show_chart", on_click=on_simular)

    page.add(
        ft.Text("Selecione uma CALL e uma PUT e clique em Simular.", size=14),
        ft.Row([dd_call, dd_put], alignment=ft.MainAxisAlignment.START),
        ft.Row([btn_simular]),
        status_txt,
        chart_container,
    )

# opcional para rodar local
if __name__ == "__main__":
    ft.app(target=main)
