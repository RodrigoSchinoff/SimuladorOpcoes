from typing import Dict, Any, Tuple, List

from core.app_core import atualizar_e_screener_atm_2venc
from services.api import buscar_detalhes_opcao, get_spot_ativo_oficial


# Camada de acesso a dados de mercado para o Long Straddle.
# Usa o screener ATM e aplica o mesmo spot oficial usado no MVP.
def get_ls_options_for_ativo(
    ativo: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], float | None, List[Dict[str, Any]]]:
    ativo = (ativo or "").strip().upper()
    if not ativo:
        raise ValueError("Ticker do ativo não informado.")

    # Usa o screener ATM (mesmo core do MVP) para obter os pares CALL/PUT
    res = atualizar_e_screener_atm_2venc(ativo, refresh=False)
    linhas: List[Dict[str, Any]] = (res or {}).get("atm") or []

    if not linhas:
        raise ValueError(f"Nenhum par ATM encontrado para o ativo {ativo}.")

    # Spot oficial (mesmo do screener)
    try:
        spot_oficial = get_spot_ativo_oficial(ativo)
    except Exception:
        spot_oficial = None

    # Fallback: se não tiver spot_oficial, usa o spot da primeira linha
    if spot_oficial is None and linhas:
        try:
            s0 = linhas[0].get("spot")
            if s0 is not None:
                spot_oficial = float(s0)
        except Exception:
            spot_oficial = None

    # Força TODAS as linhas a usarem o mesmo spot + calcula %BE↓/%BE↑
    if spot_oficial is not None and spot_oficial > 0:
        s = float(spot_oficial)
        for r in linhas:
            r["spot"] = s
            try:
                be_down = r.get("be_down")
                be_up = r.get("be_up")
                if be_down is not None:
                    r["be_pct_down"] = ((float(be_down) / s) - 1.0) * 100.0
                if be_up is not None:
                    r["be_pct_up"] = ((float(be_up) / s) - 1.0) * 100.0
            except Exception:
                # se der qualquer problema, deixa sem %BE
                continue

    # Para a simulação, usamos a PRIMEIRA linha ATM (mesma lógica do topo da grade)
    linha_atm = linhas[0]
    call_symbol = linha_atm.get("call")
    put_symbol = linha_atm.get("put")

    if not call_symbol or not put_symbol:
        raise ValueError(f"Par CALL/PUT inválido para o ativo {ativo}.")

    # Busca detalhes das opções via API (mesmo fluxo do MVP)
    dados_call = buscar_detalhes_opcao(call_symbol)
    dados_put = buscar_detalhes_opcao(put_symbol)

    if not isinstance(dados_call, dict) or not isinstance(dados_put, dict):
        raise ValueError("Erro ao obter detalhes das opções (CALL/PUT).")

    # Se tiver spot oficial, sobrescreve o spot_price usado no LS
    if spot_oficial is not None:
        try:
            s = float(spot_oficial)
            dados_call["spot_price"] = s
            dados_put["spot_price"] = s
        except Exception:
            pass

    # Retorna: dados das opções, spot_oficial e TODAS as linhas ATM
    return dados_call, dados_put, spot_oficial, linhas
