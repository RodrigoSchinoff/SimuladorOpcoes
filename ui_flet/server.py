# ui_flet/server.py
import os
import flet as ft
from .app_ls import main as app_main   # import relativo

if __name__ == "__main__":
    host = os.environ.get("FLET_SERVER_IP", "0.0.0.0")
    port = int(os.environ.get("PORT") or os.environ.get("FLET_SERVER_PORT") or 8550)
    ft.app(target=app_main, host=host, port=port, view=None)
