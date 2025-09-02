# core/app_core.py
import os
ttl_min = int(os.getenv("TTL_MIN", "2"))

from etl.carregar_opcoes_db import inserir_opcoes_do_ativo
from simulacoes.ls_screener import screener_ls_por_ticker_vencimento

def atualizar_e_screener_ls(ticker: str, due_date: str) -> dict:
    # 1) Atualiza o banco com a API1 (UPSERT por symbol)
    inserir_opcoes_do_ativo(ticker, so_vencimento=due_date)
    # 2) Roda screener lendo só do DB
    return screener_ls_por_ticker_vencimento(ticker, due_date)

# --- [ATM] Screener 2 próximos vencimentos (terceira sexta) ---
def atualizar_e_screener_atm_2venc(ticker: str, refresh: bool = False) -> dict:
    from datetime import date
    import calendar
    from simulacoes.atm_screener import screener_atm_dois_vencimentos
    # imports locais para evitar mexer nos imports do topo
    from db.conexao import conectar
    from repositories.opcoes_repo import precisa_refresh, tentar_lock_ticker, liberar_lock_ticker
    # inserir_opcoes_do_ativo já está importada no topo do arquivo

    def _third_friday(d: date) -> date:
        c = calendar.Calendar(firstweekday=calendar.MONDAY)
        fridays = [dt for dt in c.itermonthdates(d.year, d.month) if dt.weekday() == 4 and dt.month == d.month]
        return fridays[2]

    hoje = date.today()
    tf_this = _third_friday(hoje)
    if tf_this >= hoje:
        y, m = (hoje.year + (1 if hoje.month == 12 else 0), 1 if hoje.month == 12 else hoje.month + 1)
        first = _third_friday(date(y, m, 1))
        y2, m2 = (first.year + (1 if first.month == 12 else 0), 1 if first.month == 12 else first.month + 1)
        ds = [first.strftime("%Y-%m-%d"), _third_friday(date(y2, m2, 1)).strftime("%Y-%m-%d")]
    else:
        # mês corrente já passou da terceira sexta → pega próximas duas
        y, m = (hoje.year + (1 if hoje.month == 12 else 0), 1 if hoje.month == 12 else hoje.month + 1)
        first = _third_friday(date(y, m, 1))
        y2, m2 = (first.year + (1 if first.month == 12 else 0), 1 if first.month == 12 else first.month + 1)
        ds = [first.strftime("%Y-%m-%d"), _third_friday(date(y2, m2, 1)).strftime("%Y-%m-%d")]

    # === TTL + LOCK: atualiza sob demanda (1x por ticker) ===
    # Se refresh=True → força atualização.
    # Se refresh=False → só atualiza se dado ausente/velho (TTL).
    if refresh or precisa_refresh(ticker, max_age_minutes=ttl_min):
        _conn_lock = conectar()
        if _conn_lock:
            try:
                if tentar_lock_ticker(_conn_lock, ticker):
                    try:
                        # Chamada única global (SEM filtrar por vencimento)
                        inserir_opcoes_do_ativo(ticker)
                    finally:
                        liberar_lock_ticker(_conn_lock, ticker)
                # Se não pegou lock, outro processo está atualizando; seguimos
            finally:
                try:
                    _conn_lock.close()
                except Exception:
                    pass
    # === FIM TTL + LOCK ===

    # Screener (leitura apenas do DB)
    res = screener_atm_dois_vencimentos(ticker, hoje)

    # Fallback (raro): se vier vazio, tenta 1 atualização global e reexecuta
    if not (res or {}).get("atm"):
        _conn_lock = conectar()
        if _conn_lock:
            try:
                if tentar_lock_ticker(_conn_lock, ticker):
                    try:
                        inserir_opcoes_do_ativo(ticker)  # única chamada global
                    finally:
                        liberar_lock_ticker(_conn_lock, ticker)
            finally:
                try:
                    _conn_lock.close()
                except Exception:
                    pass
        res = screener_atm_dois_vencimentos(ticker, hoje)

    return res
