# ui_flet/server.py
import flet as ft
from .app_ls import main as app_main   # <— import relativo

if __name__ == "__main__":
    ft.app(target=app_main)
