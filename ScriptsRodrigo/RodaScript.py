from datetime import datetime, timezone
from services.api import buscar_opcoes_ativo

def ts_fmt(ms):
    try:
        return datetime.fromtimestamp(int(ms)/1000, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except:
        return str(ms)

ticker = "PETR4"
rows = buscar_opcoes_ativo(ticker)

# filtra linhas com spot_price válido
rows_ok = [r for r in rows if isinstance(r, dict) and r.get("spot_price") is not None and r.get("time") is not None]

print(f"[API] total linhas={len(rows)} | com spot/time={len(rows_ok)}")

# ordena por time desc e mostra top 8
rows_ok.sort(key=lambda r: r.get("time") or 0, reverse=True)
print("\n[TOP por time] spot | time | symbol")
for r in rows_ok[:8]:
    print(f"  {r.get('spot_price')} | {ts_fmt(r.get('time'))} | {r.get('symbol')}")

# estatísticas rápidas
spots = [float(r["spot_price"]) for r in rows_ok]
if spots:
    print(f"\n[min,max,uniq]={min(spots)} .. {max(spots)} | distintos={sorted(set(spots))}")

# registro ‘mais recente’ pela nossa lógica atual
if rows_ok:
    latest = rows_ok[0]
    print(f"\n[ESCOLHIDO] spot={latest['spot_price']} | time={ts_fmt(latest['time'])} | symbol={latest.get('symbol')}")
else:
    print("\n[ESCOLHIDO] nenhum registro com spot/time.")
