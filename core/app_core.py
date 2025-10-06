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
# core/app_core.py
import os
ttl_min = int(os.getenv("TTL_MIN", "2"))

from etl.carregar_opcoes_db import inserir_opcoes_do_ativo
from simulacoes.ls_screener import screener_ls_por_ticker_vencimento

def atualizar_e_screener_ls(ticker: str, due_date: str) -> dict:
    inserir_opcoes_do_ativo(ticker, so_vencimento=due_date)
    return screener_ls_por_ticker_vencimento(ticker, due_date)

# --- [ATM] Screener 2 próximos vencimentos (terceira sexta) ---
def atualizar_e_screener_atm_2venc(ticker: str, refresh: bool = False) -> dict:
    from datetime import date
    import calendar
    from simulacoes.atm_screener import screener_atm_dois_vencimentos
    from db.conexao import conectar
    from repositories.opcoes_repo import precisa_refresh_por_data, tentar_lock_ticker, liberar_lock_ticker
    from services.api import buscar_opcoes_ativo

    def _third_friday(d: date) -> date:
        c = calendar.Calendar(firstweekday=calendar.MONDAY)
        fridays = [dt for dt in c.itermonthdates(d.year, d.month) if dt.weekday() == 4 and dt.month == d.month]
        return fridays[2]

    # --- helper robusto p/ spot: mediana dos spots nas amostras mais recentes (janela de 60s) ---
    def _spot_fresco_from_payload(lista) -> float | None:
        try:
            vals = []
            for r in (lista or []):
                if isinstance(r, dict) and r.get("spot_price") is not None:
                    v = float(r["spot_price"])
                    t = int(r.get("time") or 0)
                    if v > 0:
                        vals.append((v, t))
            if not vals:
                return None
            tmax = max(t for _, t in vals)
            recent = [v for v, t in vals if (tmax - t) <= 60_000] or [v for v, _ in vals]
            recent.sort()
            return float(recent[len(recent)//2])  # mediana
        except Exception:
            return None

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

                        # --- SPOT: sempre da API, robusto por mediana recente ---
                        if updated_any:
                            payload = buscar_opcoes_ativo(ticker.upper().strip())
                            spot_new = _spot_fresco_from_payload(payload)

                            # --- SPOT: ler da API e propagar para o ticker inteiro (determinístico) ---
                            if updated_any:
                                dados = buscar_opcoes_ativo(ticker.upper().strip())
                                spot_new = None
                                rec = None
                                if isinstance(dados, list) and dados:
                                    try:
                                        rec = max(
                                            (r for r in dados if
                                             isinstance(r, dict) and r.get("spot_price") is not None),
                                            key=lambda r: (r.get("time") or 0)
                                        )
                                        spot_new = float(rec.get("spot_price"))
                                    except Exception:
                                        for r in dados:
                                            v = r.get("spot_price")
                                            if v is not None:
                                                try:
                                                    spot_new = float(v);
                                                    break
                                                except Exception:
                                                    pass
                                if spot_new is not None:
                                    # >>> INSERIR LOG AQUI (ANTES DO UPDATE) <<<
                                    from datetime import datetime, timezone
                                    def _ts(ms):
                                        try:
                                            return datetime.fromtimestamp((ms or 0) / 1000,
                                                                          tz=timezone.utc).astimezone().strftime(
                                                "%Y-%m-%d %H:%M:%S %Z")
                                        except:
                                            return str(ms)

                                    print(
                                        f"[SPOT] API spot_new={spot_new} | max(time)={_ts(rec.get('time') if rec else None)}",
                                        flush=True)

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
                            # --- FIM SPOT ---

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
                try: _conn_lock.close()
                except Exception: pass
    # === FIM TTL + LOCK ===

    # Screener (leitura do DB)
    res = screener_atm_dois_vencimentos(ticker, hoje)

    # Fallback (se vier vazio)
    if not (res or {}).get("atm"):
        _conn_lock = conectar()
        if _conn_lock:
            try:
                if tentar_lock_ticker(_conn_lock, ticker):
                    try:
                        inserir_opcoes_do_ativo(ticker)
                        payload = buscar_opcoes_ativo(ticker.upper().strip())
                        spot_new = _spot_fresco_from_payload(payload)
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
                try: _conn_lock.close()
                except Exception: pass
        res = screener_atm_dois_vencimentos(ticker, hoje)

    return res
