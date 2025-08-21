from api import buscar_opcoes_ativo, buscar_detalhes_opcao
from simulador import simular_long_straddle
# from simulador import calcular_payoff_long_straddle
# from payoff import plotar_payoff

print("Menu:")
print("1 - Buscar opções por ativo")
print("2 - Buscar detalhes de uma opção específica")
print("3 - Simular Long Straddle")
escolha = input("Escolha uma opção: ")

if escolha == "1":
    ativo_base = input("Digite o ticker do ativo (ex: PETR4): ").strip().upper()
    try:
        opcoes = buscar_opcoes_ativo(ativo_base)
        for i, op in enumerate(opcoes):
            print(f"{i+1}. {op['symbol']} | Tipo: {op['type']} | Strike: {op['strike']} | Bid: {op['bid']}")
    except Exception as e:
        print("Erro:", e)

elif escolha == "2":
    symbol_opcao = input("Digite o código da opção (ex: PETRE100): ").strip().upper()
    try:
        detalhes = buscar_detalhes_opcao(symbol_opcao)
        print("Detalhes da opção:")
        for k, v in detalhes.items():
            print(f"{k}: {v}")
    except Exception as e:
        print("Erro:", e)

elif escolha == "3":
    try:
        call_symbol = 'CMIGI119' #input("Digite o código da CALL: ").strip().upper()
        put_symbol = 'CMIGU119' #input("Digite o código da PUT: ").strip().upper()

        call = buscar_detalhes_opcao(call_symbol)
        put = buscar_detalhes_opcao(put_symbol)

        simular_long_straddle(call, put)  # ✅ Essa função já cuida de tudo, inclusive do gráfico

    except Exception as e:
        print("Erro ao simular:", e)

else:
    print("Opção inválida.")
