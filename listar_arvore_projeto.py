import os

def listar(caminho, nivel=0, max_nivel=5):
    if nivel > max_nivel:
        return
    prefixo = "    " * nivel
    try:
        arquivos = sorted(os.listdir(caminho))
    except:
        return

    for nome in arquivos:
        caminho_completo = os.path.join(caminho, nome)
        print(f"{prefixo}{nome}")
        if os.path.isdir(caminho_completo):
            listar(caminho_completo, nivel + 1, max_nivel)

listar(".", max_nivel=6)
