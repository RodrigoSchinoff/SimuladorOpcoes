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
    import calendar, os

    from simulacoes.atm_screener import screener_atm_dois_vencimentos
    from db.conexao import conectar
    from repositories.opcoes_repo import precisa_refresh_por_data, tentar_lock_ticker, liberar_lock_ticker
    from services.api import buscar_opcoes_ativo  # payload de opções (fallback p/ spot)

    # === TTL central (evita refresh constante) ===
    try:
        ttl_min = int(os.getenv("TTL_SCREENER_MIN", "10"))  # ajuste via env se quiser
    except Exception:
        ttl_min = 10

    # --- DEBUG: início ---
    import time, uuid
    exec_id = f"AC-{uuid.uuid4().hex[:6]}"
    t0 = time.perf_counter()
    print(f"[{exec_id}] START atualizar_e_screener_atm_2venc ticker={ticker} refresh={refresh} ttl_min={ttl_min}", flush=True)
    # --- DEBUG: fim ---

    # -------- helpers --------
    def _third_friday(d: date) -> date:
        c = calendar.Calendar(firstweekday=calendar.MONDAY)
        fridays = [day for day in c.itermonthdates(d.year, d.month) if day.weekday() == 4 and day.month == d.month]
        return fridays[2]

    def _spot_consenso(lista) -> float | None:
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
        try:
            from services.api import get_spot_ativo_bs
            v = float(get_spot_ativo_bs(tkr))
            if v > 0:
                return round(v, 2)
        except Exception:
            pass
        try:
            from services.api import spot_ativo_bs
            v = float(spot_ativo_bs(tkr))
            if v > 0:
                return round(v, 2)
        except Exception:
            pass
        try:
            from services.api import black_scholes_spot
            v = float(black_scholes_spot(tkr))
            if v > 0:
                return round(v, 2)
        except Exception:
            pass
        return _spot_consenso(payload_opcoes)

    # dois próximos vencimentos (ALINHADO com o screener)
    def _next_two_third_fridays(today: date):
        tf = _third_friday(today)
        if tf >= today:
            v1 = tf
            y = today.year + (1 if today.month == 12 else 0)
            m = 1 if today.month == 12 else today.month + 1
            v2 = _third_friday(date(y, m, 1))
        else:
            y = today.year + (1 if today.month == 12 else 0)
            m = 1 if today.month == 12 else today.month + 1
            v1 = _third_friday(date(y, m, 1))
            y2 = v1.year + (1 if v1.month == 12 else 0)
            m2 = 1 if v1.month == 12 else v1.month + 1
            v2 = _third_friday(date(y2, m2, 1))
        return v1, v2

    hoje = date.today()
    v1, v2 = _next_two_third_fridays(hoje)
    ds = [v1.strftime("%Y-%m-%d"), v2.strftime("%Y-%m-%d")]
    print(f"[{exec_id}] DATES_ALIGNED {ds}", flush=True)

    # === TTL + LOCK por vencimento ===
    t_need = time.perf_counter()
    need_v1 = (True if refresh else precisa_refresh_por_data(ticker, ds[0], max_age_minutes=ttl_min))
    need_v2 = (True if refresh else precisa_refresh_por_data(ticker, ds[1], max_age_minutes=ttl_min))
    print(f"[{exec_id}] NEED_REFRESH v1={need_v1} v2={need_v2} dt={time.perf_counter()-t_need:.3f}s", flush=True)

    if need_v1 or need_v2:
        t_lock = time.perf_counter()
        _conn_lock = conectar()
        print(f"[{exec_id}] LOCK_CONNECT ok={bool(_conn_lock)} dt={time.perf_counter()-t_lock:.3f}s", flush=True)
        if _conn_lock:
            try:
                t_try = time.perf_counter()
                got = tentar_lock_ticker(_conn_lock, ticker)
                print(f"[{exec_id}] TRY_LOCK got={got} dt={time.perf_counter()-t_try:.3f}s", flush=True)
                if got:
                    try:
                        updated_any = False
                        if need_v1:
                            t_u1 = time.perf_counter()
                            inserir_opcoes_do_ativo(ticker, so_vencimento=ds[0]); updated_any = True
                            print(f"[{exec_id}] UPDATE_V1 done dt={time.perf_counter()-t_u1:.3f}s", flush=True)
                        if need_v2:
                            t_u2 = time.perf_counter()
                            inserir_opcoes_do_ativo(ticker, so_vencimento=ds[1]); updated_any = True
                            print(f"[{exec_id}] UPDATE_V2 done dt={time.perf_counter()-t_u2:.3f}s", flush=True)

                        if updated_any:
                            t_payload = time.perf_counter()
                            payload = buscar_opcoes_ativo(ticker.upper().strip())
                            spot_new = _spot_preferir_bs(ticker.upper().strip(), payload)
                            print(f"[{exec_id}] PAYLOAD+SPOT spot_new={spot_new} dt={time.perf_counter()-t_payload:.3f}s", flush=True)

                            if spot_new is not None:
                                t_upd = time.perf_counter()
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
                                print(f"[{exec_id}] UPDATE_SPOT commit dt={time.perf_counter()-t_upd:.3f}s", flush=True)
                    finally:
                        liberar_lock_ticker(_conn_lock, ticker)
                        print(f"[{exec_id}] UNLOCK", flush=True)
            finally:
                try:
                    _conn_lock.close()
                except Exception:
                    pass
    # === FIM TTL + LOCK ===

    # Screener (leitura do DB)
    t_sc1 = time.perf_counter()
    print(f"[{exec_id}] BEFORE_SCREENER_DB_READ", flush=True)
    res = screener_atm_dois_vencimentos(ticker, hoje)
    print(f"[{exec_id}] AFTER_SCREENER_DB_READ dt={time.perf_counter()-t_sc1:.3f}s "
          f"atm_len={len((res or {}).get('atm', []))}", flush=True)

    # Fallback (caso venha vazio): 1 atualização global + spot preferencial BS
    if not (res or {}).get("atm"):
        print(f"[{exec_id}] EMPTY_ATM -> GLOBAL_REFRESH", flush=True)
        t_lock2 = time.perf_counter()
        _conn_lock = conectar()
        print(f"[{exec_id}] LOCK_CONNECT2 ok={bool(_conn_lock)} dt={time.perf_counter()-t_lock2:.3f}s", flush=True)
        if _conn_lock:
            try:
                t_try2 = time.perf_counter()
                got2 = tentar_lock_ticker(_conn_lock, ticker)
                print(f"[{exec_id}] TRY_LOCK2 got={got2} dt={time.perf_counter()-t_try2:.3f}s", flush=True)
                if got2:
                    try:
                        t_u_all = time.perf_counter()
                        inserir_opcoes_do_ativo(ticker)  # atualização global
                        print(f"[{exec_id}] UPDATE_ALL done dt={time.perf_counter()-t_u_all:.3f}s", flush=True)

                        t_payload2 = time.perf_counter()
                        payload = buscar_opcoes_ativo(ticker.upper().strip())
                        spot_new = _spot_preferir_bs(ticker.upper().strip(), payload)
                        print(f"[{exec_id}] PAYLOAD2+SPOT spot_new={spot_new} dt={time.perf_counter()-t_payload2:.3f}s", flush=True)

                        if spot_new is not None:
                            t_upd2 = time.perf_counter()
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
                            print(f"[{exec_id}] UPDATE_SPOT2 commit dt={time.perf_counter()-t_upd2:.3f}s", flush=True)
                    finally:
                        liberar_lock_ticker(_conn_lock, ticker)
                        print(f"[{exec_id}] UNLOCK2", flush=True)
            finally:
                try:
                    _conn_lock.close()
                except Exception:
                    pass

        t_sc2 = time.perf_counter()
        print(f"[{exec_id}] BEFORE_SCREENER_DB_READ_AGAIN", flush=True)
        res = screener_atm_dois_vencimentos(ticker, hoje)
        print(f"[{exec_id}] AFTER_SCREENER_DB_READ_AGAIN dt={time.perf_counter()-t_sc2:.3f}s "
              f"atm_len={len((res or {}).get('atm', []))}", flush=True)

    # --- DEBUG: fim da função ---
    print(f"[{exec_id}] END atualizar_e_screener_atm_2venc total={time.perf_counter()-t0:.3f}s", flush=True)
    # --- DEBUG ---

    return res
