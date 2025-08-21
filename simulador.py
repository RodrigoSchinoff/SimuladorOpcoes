from payoff import plotar_payoff

def extrair_valor(valor):
    try:
        return float(valor) if valor is not None else 0.0
    except (ValueError, TypeError):
        return 0.0

def simular_long_straddle(dados_call, dados_put):
    strike_call = extrair_valor(dados_call.get("strike"))
    strike_put = extrair_valor(dados_put.get("strike"))
    preco_call = extrair_valor(dados_call.get("bid"))
    preco_put = extrair_valor(dados_put.get("bid"))
    preco_ativo = extrair_valor(dados_call.get("spot_price")) or extrair_valor(dados_put.get("spot_price"))
    vencimento = dados_call.get("due_date")

    custo_total = (preco_call + preco_put) * 100

    # 📊 Exibir dados no terminal para validação
    print("\n📦 JSON bruto da CALL:")
    print(dados_call)
    print("\n📦 JSON bruto da PUT:")
    print(dados_put)

    print("\n📊 Detalhes da Simulação:")
    print(f"CALL: {dados_call['symbol']}  | Strike: {strike_call:.2f}  | Prêmio (Bid): {preco_call:.2f}")
    print(f"PUT : {dados_put['symbol']}  | Strike: {strike_put:.2f}  | Prêmio (Bid): {preco_put:.2f}")
    print(f"Spot (Preço atual do ativo): {preco_ativo:.2f}")
    print(f"Vencimento: {vencimento}")
    print(f"Custo Total (CALL + PUT) x100: R$ {custo_total:.2f}")

    # Base do gráfico: média dos strikes
    strike_medio = (strike_call + strike_put) / 2
    precos = [round(strike_medio + i * 0.20, 2) for i in range(-25, 26)]
    resultados = []

    for preco in precos:
        lucro_call = max(0, preco - strike_call) * 100
        lucro_put = max(0, strike_put - preco) * 100
        payoff = lucro_call + lucro_put - custo_total
        resultados.append(payoff)

    be_inferior = round(strike_put - (preco_call + preco_put), 2)
    be_superior = round(strike_call + (preco_call + preco_put), 2)

    print(f"Break-even Inferior: R$ {be_inferior:.2f}")
    print(f"Break-even Superior: R$ {be_superior:.2f}\n")

    plotar_payoff(
        precos,
        resultados,
        preco_ativo,
        be_inferior,
        be_superior,
        dados_call["symbol"],
        dados_put["symbol"],
        vencimento
    )



def calcular_payoff_long_straddle(precos_ativos, strike_call, strike_put, premio_call, premio_put, lote=100):
    custo_total = (premio_call + premio_put) * lote
    resultado = []
    for preco in precos_ativos:
        lucro_call = max(preco - strike_call, 0) * lote
        lucro_put = max(strike_put - preco, 0) * lote
        payoff = lucro_call + lucro_put - custo_total
        resultado.append(payoff)
    return resultado

