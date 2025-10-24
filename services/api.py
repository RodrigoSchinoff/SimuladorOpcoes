import requests

# Coloque aqui o seu token pessoal da Oplab
ACCESS_TOKEN = "SL8Wa37FGwhqW9L83BkY4dxkzTqSLF9OTTm1Y+a8XD3oxIdL+2XRGYoBfHxAxrdA--dXFDR6Vcn6A4QocfRWGyPg==--Zjk0ODhmYTNhZDRkMWFjZGMwMTQzYzk0ODE1YWY4Yjc="

HEADERS = {
    "Access-Token": ACCESS_TOKEN
}

BASE_URL = "https://api.oplab.com.br/v3/market/options"


def buscar_opcoes_ativo(ativo_base):
    """
    Retorna uma lista de opções (CALL e PUT) do ativo informado.
    """
    url = f"{BASE_URL}/{ativo_base}"
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Erro ao buscar opções de {ativo_base}: {response.status_code} - {response.text}")


def buscar_detalhes_opcao(symbol_opcao):
    """
    Retorna os detalhes de uma opção específica pelo símbolo.
    """
    url = f"{BASE_URL}/details/{symbol_opcao}"
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        # dados = response.json()
        # salvar_json_em_arquivo(dados, f"{symbol_opcao}.json")
        return response.json()
    else:
        raise Exception(f"Erro ao buscar detalhes da opção {symbol_opcao}: {response.status_code} - {response.text}")


import json
import os

def salvar_json_em_arquivo(dados, nome_arquivo):
    pasta = "respostas_json"
    os.makedirs(pasta, exist_ok=True)  # Cria pasta se não existir
    caminho = os.path.join(pasta, nome_arquivo)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)
    print(f"✅ JSON salvo em: {caminho}")


# --- Spot oficial do ativo (Oplab) ---
STOCK_URL = "https://api.oplab.com.br/v3/market/stocks/{symbol}?with_financials=false"

def get_spot_ativo_oficial(ticker: str) -> float | None:
    """
    Retorna o último preço do ATIVO (spot) pela API oficial (Oplab) usando o mesmo HEADERS.
    Ex.: PETR4 -> 29.98
    """
    if not ticker:
        return None
    url = STOCK_URL.format(symbol=ticker.upper().strip())
    try:
        r = requests.get(url, headers=HEADERS, timeout=4.0)
        if r.status_code != 200:
            return None
        data = r.json() or {}

        # tenta várias chaves no nível raiz
        candidates = []
        for k in ("lastPrice", "last", "price", "regularMarketPrice", "close", "spot"):
            v = data.get(k)
            try:
                v = float(v)
                if v > 0:
                    candidates.append(v)
            except Exception:
                pass

        # ou dentro de data["data"]
        if not candidates and isinstance(data.get("data"), dict):
            for k in ("lastPrice", "last", "price", "regularMarketPrice", "close", "spot"):
                v = data["data"].get(k)
                try:
                    v = float(v)
                    if v > 0:
                        candidates.append(v)
                except Exception:
                    pass

        if not candidates:
            return None
        return round(candidates[0], 2)
    except Exception:
        return None
