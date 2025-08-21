from db.conexao import conectar

def testar_conexao():
    try:
        conn = conectar()
        print("✅ Conexão bem-sucedida com o banco de dados PostgreSQL!")
        conn.close()
    except Exception as e:
        print("❌ Erro ao conectar ao banco de dados:", e)

if __name__ == "__main__":
    testar_conexao()
