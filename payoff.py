import matplotlib.pyplot as plt

def plotar_payoff(precos, resultados, preco_ativo, be_inferior, be_superior, call_ticker, put_ticker, vencimento):
    plt.figure(figsize=(10, 6))
    plt.plot(precos, resultados, label="P&L", marker='D')
    plt.axhline(0, color='black', linestyle='--')

    plt.axvline(preco_ativo, color='orange', linestyle='-', label="Preço do Ativo (Atual)")
    plt.axvline(be_inferior, color='green', linestyle='-', label="BE Inferior")
    plt.axvline(be_superior, color='blue', linestyle='-', label="BE Superior")

    plt.title(f"Long Straddle – {call_ticker} / {put_ticker} – Venc.: {vencimento}")
    plt.xlabel("Preço do Ativo")
    plt.ylabel("Resultado (R$)")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()
