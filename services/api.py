# --- PERF: sessão HTTP reutilizável com retries/timeouts ---
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_SESSION = requests.Session()
_RETRY = Retry(
    total=3, connect=3, read=3, backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"])
)
_ADAPTER = HTTPAdapter(max_retries=_RETRY, pool_connections=20, pool_maxsize=20)
_SESSION.mount("https://", _ADAPTER)
_SESSION.mount("http://", _ADAPTER)

_API_TIMEOUT = (3, 12)  # (connect, read) em segundos

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
    response = _SESSION.get(url, headers=HEADERS, timeout=_API_TIMEOUT)

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Erro ao buscar opções de {ativo_base}: {response.status_code} - {response.text}")


def buscar_detalhes_opcao(symbol_opcao):
    """
    Retorna os detalhes de uma opção específica pelo símbolo.
    """
    url = f"{BASE_URL}/details/{symbol_opcao}"
    response = _SESSION.get(url, headers=HEADERS, timeout=_API_TIMEOUT)

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
