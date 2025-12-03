import os
import cd3_connector

CEDRO_USER = os.getenv("CEDRO_USER")
CEDRO_PASS = os.getenv("CEDRO_PASS")


class CedroClientDebug:
    """
    Versão mínima, idêntica ao exemplo oficial da Cedro.
    Não tenta configurar host/porta nem nada extra.
    Apenas conecta, envia um SQT e imprime tudo que chegar.
    """

    def __init__(self):
        if not CEDRO_USER or not CEDRO_PASS:
            raise RuntimeError("CEDRO_USER/CEDRO_PASS não configurados no .env.")

        # MESMA ASSINATURA DO PDF:
        # CD3Connector(user, password, on_disconnect, on_message, on_connect)
        self._conn = cd3_connector.CD3Connector(
            CEDRO_USER,
            CEDRO_PASS,
            self._on_disconnect,
            self._on_message,
            self._on_connect,
        )

    def _on_connect(self):
        print(">>> CONNECT: conectado ao Crystal Difusor Cedro")
        # Comando exatamente como no exemplo do manual (case-insensitive)
        #self._conn.send_command("sqt petr4")
        self._conn.send_command("GSO 001 PETR4 12 2025")


    def _on_disconnect(self):
        print(">>> DISCONNECT: conexão encerrada")

    def _on_message(self, msg: str):
        # Aqui queremos ver o texto CRU que vem da Cedro
        print("RECEBIDO:", msg)

    def start(self):
        # Inicia a thread interna do conector
        self._conn.start()

    def stop(self):
        try:
            self._conn.stop()
        except Exception:
            pass
