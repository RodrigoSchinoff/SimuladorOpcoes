import psycopg2


def conectar():
    return psycopg2.connect(
        host="db.uqyofheglfryfwpyaqis.supabase.co",
        port=5432,
        dbname="postgres",
        user="postgres",
        password="AatR1701"
    )

postgresql://postgres:[YOUR-PASSWORD]@db.uqyofheglfryfwpyaqis.supabase.co:5432/postgres