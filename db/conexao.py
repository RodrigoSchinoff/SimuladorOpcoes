# db/conexao.py
import os
import psycopg2
from psycopg2.pool import SimpleConnectionPool

__all__ = ["conectar"]

# DATABASE_URL do Render/Supabase (use o endpoint "pooler" do Supabase se houver)
_DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or ""
)

if not _DATABASE_URL:
    # fallback por variáveis separadas, se você usa assim localmente
    _HOST = os.getenv("DB_HOST", "localhost")
    _PORT = int(os.getenv("DB_PORT", "5432"))
    _NAME = os.getenv("DB_NAME", "postgres")
    _USER = os.getenv("DB_USER", "postgres")
    _PASS = os.getenv("DB_PASSWORD", "")
    _DATABASE_URL = f"postgresql://{_USER}:{_PASS}@{_HOST}:{_PORT}/{_NAME}"

_CONNECT_KW = {
    "connect_timeout": int(os.getenv("PG_CONNECT_TIMEOUT", "5")),
    "application_name": os.getenv("PG_APP_NAME", "simulador_opcoes"),
    # ajuste sslmode conforme sua infra (Render/Supabase geralmente requer 'require')
    "sslmode": os.getenv("PG_SSLMODE", "require"),
}

_POOL = None

def _init_pool():
    global _POOL
    if _POOL is None:
        _POOL = SimpleConnectionPool(
            minconn=int(os.getenv("PG_MINCONN", "1")),
            maxconn=int(os.getenv("PG_MAXCONN", "10")),
            dsn=_DATABASE_URL,
            **_CONNECT_KW
        )

class _PooledConn:
    __slots__ = ("_pool", "_conn")
    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn
    def cursor(self, *a, **k):
        return self._conn.cursor(*a, **k)
    def commit(self):
        return self._conn.commit()
    def rollback(self):
        return self._conn.rollback()
    def close(self):
        if self._pool and self._conn:
            self._pool.putconn(self._conn)
            self._conn = None
            self._pool = None

def conectar():
    global _POOL
    if _POOL is None:
        _init_pool()
    try:
        raw = _POOL.getconn()
        return _PooledConn(_POOL, raw)
    except Exception:
        # fallback sem pool (último recurso)
        return psycopg2.connect(_DATABASE_URL, **_CONNECT_KW)
