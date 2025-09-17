# db/conexao.py
import os
import psycopg2

def conectar():
    host = os.environ.get("DB_HOST")                   # ex.: aws-0-sa-east-1.pooler.supabase.com
    port = int(os.environ.get("DB_PORT", "6543"))      # 6543 (transaction) ou 5432 (session)
    db   = os.environ.get("DB_NAME", "postgres")
    user = os.environ.get("DB_USER")                   # ex.: postgres.<project-id>
    pwd  = os.environ.get("DB_PASSWORD")

    if not all([host, user, pwd]):
        raise RuntimeError("Variáveis de ambiente do DB ausentes (DB_HOST, DB_USER, DB_PASSWORD).")

    return psycopg2.connect(
        host=host,
        port=port,
        dbname=db,
        user=user,
        password=pwd,
        sslmode="require",   # Supabase pooler requer SSL
    )
