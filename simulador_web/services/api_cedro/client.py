import asyncio
import websockets
import json

CEDRO_URL = "wss://api.cedrofinances.com.br/socket"   # exemplo; você substitui pelo URL real

class CedroSocketClient:
    """
    Cliente WebSocket simples para enviar um comando e receber uma mensagem.
    Sem streaming, apenas request/response.
    """

    def __init__(self, url=CEDRO_URL):
        self.url = url

    async def send_command(self, command: str):
        async with websockets.connect(self.url) as ws:
            await ws.send(command)
            response = await ws.recv()
            return json.loads(response)
