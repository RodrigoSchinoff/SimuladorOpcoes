# core/app_core.py
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
    # se precisar: from core.app_core import inserir_opcoes_do_ativo

    def _third_friday(d: date) -> date:
        c = calendar.Calendar(firstweekday=calendar.MONDAY)
        fridays = [dt for dt in c.itermonthdates(d.year, d.month) if dt.weekday() == 4 and dt.month == d.month]
        return fridays[2]

    hoje = date.today()
    tf_this = _third_friday(hoje)
    if tf_this >= hoje:
        y, m = (hoje.year + (1 if hoje.month == 12 else 0), 1 if hoje.month == 12 else hoje.month + 1)
        ds = [tf_this.strftime("%Y-%m-%d"), _third_friday(date(y, m, 1)).strftime("%Y-%m-%d")]
    else:
        y, m = (hoje.year + (1 if hoje.month == 12 else 0), 1 if hoje.month == 12 else hoje.month + 1)
        first = _third_friday(date(y, m, 1))
        y2, m2 = (first.year + (1 if first.month == 12 else 0), 1 if first.month == 12 else first.month + 1)
        ds = [first.strftime("%Y-%m-%d"), _third_friday(date(y2, m2, 1)).strftime("%Y-%m-%d")]

    # ⚠️ Só atualiza o DB se explicitamente pedido (refresh=True)
    if refresh:
        for d in ds:
            try:
                inserir_opcoes_do_ativo(ticker, so_vencimento=d)
            except Exception:
                pass

    return screener_atm_dois_vencimentos(ticker, hoje)
