import os

IGNORAR_DIRS = {
    ".git",
    ".idea",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
}

IGNORAR_ARQUIVOS = {
    ".DS_Store",
}

IGNORAR_EXTENSOES = {
    ".pyc",
    ".log",
    ".sqlite3",
}

def listar(caminho, nivel=0, max_nivel=5):
    if nivel > max_nivel:
        return

    prefixo = "    " * nivel

    try:
        itens = sorted(os.listdir(caminho))
    except PermissionError:
        return

    for nome in itens:
        if nome in IGNORAR_DIRS or nome in IGNORAR_ARQUIVOS:
            continue

        caminho_completo = os.path.join(caminho, nome)

        if os.path.isfile(caminho_completo):
            _, ext = os.path.splitext(nome)
            if ext in IGNORAR_EXTENSOES:
                continue

        print(f"{prefixo}{nome}")

        if os.path.isdir(caminho_completo):
            listar(caminho_completo, nivel + 1, max_nivel)

listar(".", max_nivel=6)
