# core/cache_keys.py

def ls_cache_key(ativo, horizonte, num_vencimentos):
    """
    Gera uma chave unificada de cache para o Long Straddle.
    Ignora parâmetros que não precisam gerar cache novo.
    """
    ativo = (ativo or "").upper().strip() or "LISTA_PADRAO"
    horizonte = (horizonte or "VENC").upper().strip()
    num_vencimentos = str(num_vencimentos or "1")
    return f"ls:{ativo}:{horizonte}:{num_vencimentos}"


def screener_cache_key(ticker, v1, v2, horizonte, crush_iv):
    """
    Gera chave unificada para o screener ATM de 2 vencimentos.
    """
    ticker = (ticker or "").upper().strip()
    horizonte = (horizonte or "VENC").upper().strip()
    crush_iv = float(crush_iv or 0.0)
    return f"screener:{ticker}:{v1}:{v2}:{horizonte}:{crush_iv}"
