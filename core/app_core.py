# core/app_core.py
import os
ttl_min = int(os.getenv("TTL_MIN", "2"))

from etl.carregar_opcoes_db import inserir_opcoes_do_ativo
from simulacoes.ls_screener import screener_ls_por_ticker_vencimento


def atualizar_e_screener_ls(ticker: str, due_date: str) -> dict:
    """
    Atualiza o DB para o vencimento informado e roda o screener LS (leitura do DB).
    """
    inserir_opcoes_do_ativo(ticker, so_vencimento=due_date)
    return screener_ls_por_ticker_vencimento(ticker, due_date)


# --- [ATM] Screener 2 próximos vencimentos (terceira sexta) ---
def atualizar_e_screener_atm_2venc(ticker: str, refresh: bool = False) -> dict:
    from datetime import date
    import calendar

    from simulacoes.atm_screener import screener_atm_dois_vencimentos
    from db.conexao import conectar
    from repositories.opcoes_repo import precisa_refresh_por_data, tentar_lock_ticker, liberar_lock_ticker
    from services.api import buscar_opcoes_ativo  # payload de opções (fallback p/ spot)

    # -------- helpers --------
    def _third_friday(d: date) -> date:
        c = calendar.Calendar(firstweekday=calendar.MONDAY)
        fridays = [day for day in c.itermonthdates(d.year, d.month) if day.weekday() == 4 and day.month == d.month]
        return fridays[2]

    def _spot_consenso(lista) -> float | None:
        """
        Mediana dos spot_price no MAIOR timestamp (time == tmax) do payload.
        Se não houver filtro por tmax, usa mediana geral.
        """
        try:
            xs, ts = [], []
            for r in (lista or []):
                if isinstance(r, dict):
                    sp = r.get("spot_price")
                    tm = r.get("time")
                    if sp is not None:
                        xs.append(float(sp))
                    if tm is not None:
                        ts.append(int(tm))
            if not xs:
                return None
            if ts:
                tmax = max(ts)
                xs_tmax = [float(r["spot_price"]) for r in lista
                           if isinstance(r, dict) and r.get("spot_price") is not None and r.get("time") == tmax]
                if xs_tmax:
                    xs = xs_tmax
            xs.sort()
            n = len(xs)
            med = xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])
            return round(float(med), 2)
        except Exception:
            return None

    def _spot_preferir_bs(tkr: str, payload_opcoes) -> float | None:
        """
        1) Tenta pegar o spot do ATIVO via API de Black-Scholes já implementada.
           (Tentamos alguns nomes de função comuns; se não existir, ignoramos.)
        2) Se falhar, usa o consenso do payload de opções (mediana no último timestamp).
        """
        # tenta várias assinaturas possíveis sem quebrar seu código existente
        try:
            # services.api.get_spot_ativo_bs(ticker)  -> float
            from services.api import get_spot_ativo_bs
            v = float(get_spot_ativo_bs(tkr))
            if v > 0:
                return round(v, 2)
        except Exception:
            pass
        try:
            # services.api.spot_ativo_bs(ticker) -> float
            from services.api import spot_ativo_bs
            v = float(spot_ativo_bs(tkr))
            if v > 0:
                return round(v, 2)
        except Exception:
            pass
        try:
            # services.api.black_scholes_spot(ticker) -> float
            from services.api import black_scholes_spot
            v = float(black_scholes_spot(tkr))
            if v > 0:
                return round(v, 2)
        except Exception:
            pass

        # fallback: consenso do payload de opções
        return _spot_consenso(payload_opcoes)

    # dois próximos vencimentos (terceira sexta)
    hoje = date.today()
    tf_this = _third_friday(hoje)
    if tf_this >= hoje:
        y, m = (hoje.year + (1 if hoje.month == 12 else 0), 1 if hoje.month == 12 else hoje.month + 1)
        first = _third_friday(date(y, m, 1))
        y2, m2 = (first.year + (1 if first.month == 12 else 0), 1 if first.month == 12 else first.month + 1)
        ds = [first.strftime("%Y-%m-%d"), _third_friday(date(y2, m2, 1)).strftime("%Y-%m-%d")]
    else:
        y, m = (hoje.year + (1 if hoje.month == 12 else 0), 1 if hoje.month == 12 else hoje.month + 1)
        first = _third_friday(date(y, m, 1))
        y2, m2 = (first.year + (1 if first.month == 12 else 0), 1 if first.month == 12 else first.month + 1)
        ds = [first.strftime("%Y-%m-%d"), _third_friday(date(y2, m2, 1)).strftime("%Y-%m-%d")]

    # === TTL + LOCK por vencimento ===
    need_v1 = refresh or precisa_refresh_por_data(ticker, ds[0], max_age_minutes=ttl_min)
    need_v2 = refresh or precisa_refresh_por_data(ticker, ds[1], max_age_minutes=ttl_min)

    if need_v1 or need_v2:
        _conn_lock = conectar()
        if _conn_lock:
            try:
                if tentar_lock_ticker(_conn_lock, ticker):
                    try:
                        updated_any = False
                        if need_v1:
                            inserir_opcoes_do_ativo(ticker, so_vencimento=ds[0]); updated_any = True
                        if need_v2:
                            inserir_opcoes_do_ativo(ticker, so_vencimento=ds[1]); updated_any = True

                        if updated_any:
                            # payload de opções fresco (para fallback/consenso)
                            payload = buscar_opcoes_ativo(ticker.upper().strip())
                            # SPOT preferencial: API BS; fallback: consenso(payload)
                            spot_new = _spot_preferir_bs(ticker.upper().strip(), payload)

                            if spot_new is not None:
                                with _conn_lock.cursor() as cur:
                                    cur.execute(
                                        """
                                        UPDATE public.opcoes_do_ativo
                                           SET spot_price = %s,
                                               data_ultima_consulta = NOW()
                                         WHERE parent_symbol = %s
                                        """,
                                        (spot_new, ticker),
                                    )
                                _conn_lock.commit()
                    finally:
                        liberar_lock_ticker(_conn_lock, ticker)
            finally:
                try:
                    _conn_lock.close()
                except Exception:
                    pass
    # === FIM TTL + LOCK ===

    # Screener (leitura do DB)
    res = screener_atm_dois_vencimentos(ticker, hoje)

    # Fallback (caso venha vazio): 1 atualização global + spot preferencial BS
    if not (res or {}).get("atm"):
        _conn_lock = conectar()
        if _conn_lock:
            try:
                if tentar_lock_ticker(_conn_lock, ticker):
                    try:
                        inserir_opcoes_do_ativo(ticker)  # atualização global
                        payload = buscar_opcoes_ativo(ticker.upper().strip())
                        spot_new = _spot_preferir_bs(ticker.upper().strip(), payload)
                        if spot_new is not None:
                            with _conn_lock.cursor() as cur:
                                cur.execute(
                                    """
                                    UPDATE public.opcoes_do_ativo
                                       SET spot_price = %s,
                                           data_ultima_consulta = NOW()
                                     WHERE parent_symbol = %s
                                    """,
                                    (spot_new, ticker),
                                )
                            _conn_lock.commit()
                    finally:
                        liberar_lock_ticker(_conn_lock, ticker)
            finally:
                try:
                    _conn_lock.close()
                except Exception:
                    pass
        res = screener_atm_dois_vencimentos(ticker, hoje)

    return res
