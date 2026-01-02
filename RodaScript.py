from datetime import datetime, timezone, date
from pathlib import Path
from dotenv import load_dotenv
import calendar

# carrega .env
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from services.api import buscar_opcoes_ativo


def ts_fmt(ms):
    try:
        return datetime.fromtimestamp(int(ms)/1000, tz=timezone.utc) \
            .astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return str(ms)


def is_third_friday(d: date) -> bool:
    if d.weekday() != calendar.FRIDAY:
        return False

    first_day = d.replace(day=1)
    first_friday = first_day.replace(
        day=1 + (calendar.FRIDAY - first_day.weekday()) % 7
    )
    third_friday = first_friday.replace(day=first_friday.day + 14)
    return d == third_friday


ticker = "PETR4"
rows = buscar_opcoes_ativo(ticker)

# converte + filtra apenas mensais (3ª sexta)
rows_monthly = []
for r in rows:
    try:
        due = r.get("due_date")
        if isinstance(due, str):
            due = datetime.fromisoformat(due).date()

        if due and is_third_friday(due):
            rows_monthly.append(r)
    except Exception:
        continue


print(f"[API] total linhas={len(rows)} | mensais={len(rows_monthly)}")

# filtra spot/time válidos
rows_ok = [
    r for r in rows_monthly
    if r.get("spot_price") is not None and r.get("time") is not None
]

# ordena por time desc
rows_ok.sort(key=lambda r: r["time"], reverse=True)

print("\n[TOP mensais por time] spot | time | due | symbol")
for r in rows_ok[:8]:
    print(
        f"  {r['spot_price']} | "
        f"{ts_fmt(r['time'])} | "
        f"{r.get('due_date')} | "
        f"{r.get('symbol')}"
    )

# estatísticas
spots = [float(r["spot_price"]) for r in rows_ok]
if spots:
    print(
        f"\n[min,max,uniq]={min(spots)} .. {max(spots)} | "
        f"distintos={sorted(set(spots))}"
    )

# escolhido
if rows_ok:
    latest = rows_ok[0]
    print(
        f"\n[ESCOLHIDO] spot={latest['spot_price']} | "
        f"time={ts_fmt(latest['time'])} | "
        f"due={latest.get('due_date')} | "
        f"symbol={latest.get('symbol')}"
    )
else:
    print("\n[ESCOLHIDO] nenhum registro mensal válido.")
