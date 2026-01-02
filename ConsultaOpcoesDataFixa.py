from datetime import datetime, timezone, date
from pathlib import Path
from dotenv import load_dotenv
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from services.api import buscar_opcoes_ativo


def ts_fmt(ms):
    try:
        return datetime.fromtimestamp(int(ms)/1000, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return str(ms)


def to_date(x):
    if isinstance(x, date):
        return x
    if isinstance(x, str):
        # aceita "YYYY-MM-DD" e "YYYY-MM-DDTHH:MM:SS"
        return datetime.fromisoformat(x[:10]).date()
    return None


ticker = "PETR4"
TARGET_DUE = date(2026, 1, 15)  # <<<<< FORÇA o vencimento desejado

rows = buscar_opcoes_ativo(ticker)

# conta vencimentos disponíveis (pra você ver o que a OPLAB está entregando)
dues = [to_date(r.get("due_date")) for r in rows if isinstance(r, dict)]
counts = Counter([d for d in dues if d])
print("\n[DUE DATES - TOP 15]")
for d, c in counts.most_common(15):
    print(f"  {d} -> {c} linhas")

# filtra só o vencimento alvo
rows_due = [r for r in rows if to_date(r.get("due_date")) == TARGET_DUE]
print(f"\n[FILTRO] due={TARGET_DUE} | linhas={len(rows_due)}")

# filtra spot/time válidos e ordena
rows_ok = [r for r in rows_due if r.get("spot_price") is not None and r.get("time") is not None]
rows_ok.sort(key=lambda r: r["time"], reverse=True)

print("\n[TOP por time - SOMENTE due fixo] spot | time | symbol | strike")
for r in rows_ok[:12]:
    print(f"  {r.get('spot_price')} | {ts_fmt(r.get('time'))} | {r.get('symbol')} | {r.get('strike')}")

# strikes únicos (sem tentar converter ainda)
strikes_raw = sorted({r.get("strike") for r in rows_due if r.get("strike") is not None})
print(f"\n[STRIKES RAW] qtd={len(strikes_raw)} | primeiros={strikes_raw[:12]} | últimos={strikes_raw[-12:]}")
