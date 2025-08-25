# core/app_core.py
from etl.carregar_opcoes_db import inserir_opcoes_do_ativo
from simulacoes.ls_screener import screener_ls_por_ticker_vencimento

def atualizar_e_screener_ls(ticker: str, due_date: str) -> dict:
    # 1) Atualiza o banco com a API1 (UPSERT por symbol)
    inserir_opcoes_do_ativo(ticker, so_vencimento=due_date)
    # 2) Roda screener lendo só do DB
    return screener_ls_por_ticker_vencimento(ticker, due_date)
