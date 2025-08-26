# ui_flet/server.py
import flet as ft

# se no seu app_ls.py a função principal se chama "main"
from ui_flet.app_ls import main as app_main

# Se não existir "main(page)", veja as observações abaixo.
if __name__ == "__main__":
    ft.app(target=app_main)  # Flet sobe em modo Web no Render
