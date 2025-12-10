# core/app_core.py
import time
import uuid
from datetime import date
from services.api import buscar_opcoes_ativo, get_spot_ativo_oficial
from simulacoes.atm_screener import screener_atm_dois_vencimentos


def atualizar_e_screener_atm_2venc(ticker: str, refresh: bool = False, params: dict | None = None) -> dict:
    """
    Camada fina acima do screener. Apenas loga o fluxo,
    dispara o screener e devolve o resultado.
    """
    exec_id = f"AC-{uuid.uuid4().hex[:6]}"
    t0 = time.perf_counter()
    ticker = (ticker or "").upper().strip()

    print(f"[{exec_id}] ▶ START atualizar_e_screener_atm_2venc ticker={ticker} refresh={refresh}", flush=True)

    # 1) Buscar opções
    t_api0 = time.perf_counter()
    try:
        ops = buscar_opcoes_ativo(ticker)
    except Exception as e:
        print(f"[{exec_id}] ❌ ERRO buscar_opcoes_ativo: {e}", flush=True)
        return {"atm": [], "due_dates": []}
    t_api1 = time.perf_counter()

    if not ops:
        print(f"[{exec_id}] ❌ API voltou vazia", flush=True)
        return {"atm": [], "due_dates": []}

    # 2) Spot oficial
    t_spot0 = time.perf_counter()
    try:
        spot = float(get_spot_ativo_oficial(ticker) or 0.0)
    except:
        spot = 0.0
    t_spot1 = time.perf_counter()

    # 3) Rodar screener (este fará logs SC-...)
    t_sc0 = time.perf_counter()
    res = screener_atm_dois_vencimentos(ticker, date.today())
    t_sc1 = time.perf_counter()

    linhas = res.get("atm", [])
    dues = res.get("due_dates", [])

    print(
        f"[{exec_id}] ✔ DONE ticker={ticker} | vencimentos={dues} | linhas={len(linhas)} | "
        f"API={t_api1 - t_api0:.3f}s | SPOT={t_spot1 - t_spot0:.3f}s | SCREENER={t_sc1 - t_sc0:.3f}s | "
        f"TOTAL={time.perf_counter() - t0:.3f}s",
        flush=True
    )

    return res
