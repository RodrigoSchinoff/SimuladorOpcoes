# core/app_core.py
import time
import uuid
from datetime import date

from services.api import buscar_opcoes_ativo, get_spot_ativo_oficial
from simulacoes.atm_screener import screener_atm_dois_vencimentos


def atualizar_e_screener_atm_2venc(ticker: str, refresh: bool = False, params: dict | None = None) -> dict:
    exec_id = f"AC-{uuid.uuid4().hex[:6]}"
    t0 = time.perf_counter()

    print(f"[{exec_id}] START atualizar_e_screener_atm_2venc ticker={ticker} refresh={refresh}", flush=True)

    # ---------------------------------------
    # 1) BUSCA DIRETO DA API (SEM DB)
    # ---------------------------------------
    print(f"[{exec_id}] API_FETCH", flush=True)
    try:
        ops = buscar_opcoes_ativo(ticker.upper().strip())
    except Exception as e:
        print(f"[{exec_id}] ERRO API_FETCH {e}", flush=True)
        return {"atm": [], "due_dates": []}

    if not ops:
        print(f"[{exec_id}] API retornou 0 opções.", flush=True)
        return {"atm": [], "due_dates": []}

    # ---------------------------------------
    # 2) SPOT OFICIAL
    # ---------------------------------------
    try:
        spot = float(get_spot_ativo_oficial(ticker) or 0.0)
    except:
        spot = 0.0

    if spot <= 0:
        # fallback do screener
        try:
            from simulacoes.atm_screener import _spot_from_ops
            spot = _spot_from_ops(ops)
        except:
            pass

    print(f"[{exec_id}] SPOT = {spot}", flush=True)

    # ---------------------------------------
    # 3) EXECUTA SCREENER ORIGINAL (como antes)
    # ---------------------------------------
    print(f"[{exec_id}] BEFORE_SCREENER_CALC", flush=True)
    res = screener_atm_dois_vencimentos(ticker, date.today())

    if not res.get("atm"):
        print(f"[{exec_id}] NENHUMA LINHA ATM", flush=True)

    print(f"[{exec_id}] END atualizar_e_screener_atm_2venc total={time.perf_counter()-t0:.3f}s", flush=True)
    return res
