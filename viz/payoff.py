# viz/payoff.py
import math
from typing import Iterable, Tuple, Optional
from matplotlib.ticker import FuncFormatter

def _fmt_brl(y, _pos=None):
    # Formata número como BRL: R$ 1.234,56
    s = f"{y:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"

def _safe_vline(ax, x, **kwargs):
    if x is None:
        return
    try:
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return
    except Exception:
        return
    ax.axvline(x, **kwargs)

def plotar_payoff(
    precos: Iterable[float],
    resultados: Iterable[float],
    preco_ativo: Optional[float] = None,
    be_inferior: Optional[float] = None,
    be_superior: Optional[float] = None,
    call_ticker: str = "",
    put_ticker: str = "",
    vencimento: str = "",
    *,
    estrategia_nome: str = "Long Straddle",
    salvar_em: Optional[str] = None,
    mostrar: bool = True,
    fig_size: Tuple[float, float] = (5.5, 3.2),  # menor por padrão
    dpi: int = 120,
    font_scale: float = 0.9
):
    """
    Plota a curva de P&L de uma estratégia de opções.

    - mostrar=True: usa pyplot e abre janela (CLI/terminal).
    - mostrar=False: cria uma Figure "headless" (sem abrir janela), ideal para Flet.

    Retorna: (fig, ax)
    """
    # Criação da figure
    if mostrar:
        import matplotlib.pyplot as plt  # backend interativo só quando precisa
        fig, ax = plt.subplots(figsize=fig_size, dpi=dpi)
    else:
        from matplotlib.figure import Figure  # headless (sem janela)
        fig = Figure(figsize=fig_size, dpi=dpi)
        ax = fig.add_subplot(111)

    # Garantir listas
    precos = list(precos or [])
    resultados = list(resultados or [])

    # Curva e linha de zero
    ax.plot(precos, resultados, label="P&L")
    ax.axhline(0, color="black", linestyle="--", linewidth=1)

    # Linhas verticais auxiliares
    _safe_vline(ax, preco_ativo, color="orange", linestyle="-",  linewidth=1, label="Preço do Ativo (Atual)")
    _safe_vline(ax, be_inferior, color="green",  linestyle="--", linewidth=1, label="BE Inferior")
    _safe_vline(ax, be_superior, color="blue",   linestyle="--", linewidth=1, label="BE Superior")

    # Título
    titulo_tickers = f"{call_ticker} / {put_ticker}".strip(" /")
    if titulo_tickers and vencimento:
        titulo = f"{estrategia_nome} – {titulo_tickers} – Venc.: {vencimento}"
    elif titulo_tickers:
        titulo = f"{estrategia_nome} – {titulo_tickers}"
    else:
        titulo = f"{estrategia_nome}"

    # Fontes
    fs_title  = 12 * font_scale
    fs_label  = 10 * font_scale
    fs_tick   = 9  * font_scale
    fs_legend = 9  * font_scale

    ax.set_title(titulo, fontsize=fs_title)
    ax.set_xlabel("Preço do Ativo", fontsize=fs_label)
    ax.set_ylabel("Resultado (R$)", fontsize=fs_label)
    ax.tick_params(labelsize=fs_tick)
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_formatter(FuncFormatter(_fmt_brl))

    # Limites Y com folga
    if resultados:
        y_min, y_max = min(resultados), max(resultados)
        if y_min == y_max:
            y_min -= 1.0
            y_max += 1.0
        pad = (y_max - y_min) * 0.10 or 1.0
        ax.set_ylim(y_min - pad, y_max + pad)

    ax.legend(fontsize=fs_legend)

    # Ajuste de layout e salvar (sem abrir janela)
    try:
        fig.tight_layout()
    except Exception:
        pass

    if salvar_em:
        fig.savefig(salvar_em, dpi=dpi, bbox_inches="tight")

    # Mostrar janela só no modo interativo (CLI)
    if mostrar:
        import matplotlib.pyplot as plt
        plt.show()

    return fig, ax
