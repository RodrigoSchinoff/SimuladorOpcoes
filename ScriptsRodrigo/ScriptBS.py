# ScriptBS.py
# Testa exatamente a mesma chamada de BS usada dentro do LS
# e imprime Delta, Gamma, Theta, Vega, Rho e demais campos.

from services.api import buscar_detalhes_opcao
from services.api_bs import bs_greeks

def testar_bs(symbol: str):
    print(f"\n=== Testando BS para opção: {symbol} ===")

    # --- 1) Buscar dados normais da opção (mesmo payload que o LS usa) ---
    d = buscar_detalhes_opcao(symbol)
    if not isinstance(d, dict):
        print("Erro: resposta inválida da API normal.")
        print(d)
        return

    print("\n=== Dados da opção (API normal) ===")
    for k, v in d.items():
        print(f"{k}: {v}")

    # --- 2) Preparar parâmetros EXACTAMENTE como o LS usa ---
    try:
        kind = d.get("type", "").upper()            # CALL ou PUT
        spot = float(d.get("spot_price") or 0)
        strike = float(d.get("strike") or 0)
        premium = float(d.get("ask") or d.get("last") or d.get("close") or 0)
        dtm = int(d.get("days_to_maturity") or 0)

        # volatilidade usada pelo LS: ele usa d["iv"] quando existe, senão 0
        vol = float(d.get("iv") or 0)

        due_date = d.get("due_date") or ""
        irate = 0.0
        amount = 100
    except Exception as ex:
        print("Erro preparando parâmetros:", ex)
        return

    print("\n=== Parâmetros enviados ao BS (exatamente como o LS) ===")
    print(f"kind={kind}  spotprice={spot}  strike={strike}")
    print(f"premium={premium}  dtm={dtm}  vol={vol}")
    print(f"due_date={due_date}  irate={irate}  amount={amount}")

    # --- 3) Chamar o BS exatamente como o LS chama ---
    try:
        resp = bs_greeks(
            symbol=symbol,
            kind=kind,
            spotprice=spot,
            strike=strike,
            premium=premium,
            dtm=dtm,
            vol=vol,
            due_date=due_date,
            irate=irate,
            amount=amount,
        )
    except Exception as ex:
        print("\nErro chamando BS:", ex)
        return

    print("\n=== Resposta BS (mesmos campos que aparecem no simulador) ===")
    for k, v in resp.items():
        print(f"{k}: {v}")

    print("\n=== Delta retornado ===")
    print(resp.get("delta"))


# ------------------------------------------------------------
# EXECUÇÃO
# ------------------------------------------------------------
if __name__ == "__main__":
    opcao = input("Digite o código da opção (ex: PETRL318): ").strip().upper()
    testar_bs(opcao)
