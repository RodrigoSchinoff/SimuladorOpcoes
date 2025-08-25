import psycopg2

def conectar():
    HOST = "aws-1-sa-east-1.pooler.supabase.com"   # Host do Pooler
    PORT = 6543                                    # Porta do Pooler
    DB   = "postgres"                              # Nome do banco
    USER = "postgres.uqyofheglfryfwpyaqis"         # Usuário do Pooler
    PASS = "AatR1701"                 # Sua senha (reset em Settings → Database se não lembrar)

    try:
        conn = psycopg2.connect(
            host=HOST,
            port=PORT,
            dbname=DB,
            user=USER,
            password=PASS,
            sslmode="require"   # Supabase exige SSL
        )
        print("✅ Conexão estabelecida com sucesso.")
        return conn
    except Exception as e:
        print("❌ Erro ao conectar ao banco de dados:", e)
        return None
