import os
import threading
from queue import Queue, Empty
from typing import List, Dict, Any

import cd3_connector

CEDRO_USER = os.getenv("CEDRO_USER", "")
CEDRO_PASS = os.getenv("CEDRO_PASS", "")
TIMEOUT_CONNECT = 5.0
TIMEOUT_CMD = 5.0


class CedroClient:
    """
    Wrapper mínimo em cima do CD3Connector oficial da Cedro.
    Abre conexão, envia comandos (SQT / GSO) e coleta mensagens em fila.
    """

    def __init__(self):
        if not CEDRO_USER or not CEDRO_PASS:
            raise RuntimeError("Credenciais Cedro não configuradas (CEDRO_USER / CEDRO_PASS).")

        self._queue: Queue[str] = Queue()
        self._connected = threading.Event()
        self._conn = cd3_connector.CD3Connector(
            CEDRO_USER,
            CEDRO_PASS,
            self._on_disconnect,
            self._on_message,
            self._on_connect,
        )

    # ------------------------------------------------------------------
    # Callbacks do CD3Connector
    # ------------------------------------------------------------------
    def _on_connect(self):
        self._connected.set()

    def _on_disconnect(self):
        self._connected.clear()

    def _on_message(self, msg: str):
        # cada msg é uma linha de texto do Crystal
        self._queue.put(msg)

    # ------------------------------------------------------------------
    # Controle de vida
    # ------------------------------------------------------------------
    def start(self):
        self._conn.start()
        if not self._connected.wait(TIMEOUT_CONNECT):
            raise RuntimeError("Timeout conectando no servidor Cedro.")

    def stop(self):
        try:
            self._conn.stop()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Utilitários de leitura
    # ------------------------------------------------------------------
    def _get_next_msg(self, timeout: float = TIMEOUT_CMD) -> str | None:
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    # ------------------------------------------------------------------
    # Comandos SQT / GSO
    # ------------------------------------------------------------------
    def get_spot(self, ativo: str) -> float:
        """
        SQT <ativo> N  -> snapshot de cotação.
        Usa índice 2 (último preço) conforme documentação do SQT. :contentReference[oaicite:1]{index=1}
        """
        cmd = f"SQT {ativo.upper()} N"
        self._conn.send_command(cmd)

        # esperamos a primeira linha T:<ativo>:...
        while True:
            msg = self._get_next_msg()
            if msg is None:
                raise RuntimeError("Timeout aguardando resposta SQT.")
            if not msg.startswith("T:"):
                continue

            parts = msg.strip("!\r\n").split(":")
            # formato: T, ATIVO, HORA, idx, val, idx, val...
            # índice 2 = último preço (doc SQT, campo 2). :contentReference[oaicite:2]{index=2}
            i = 3
            last_price = None
            while i + 1 < len(parts):
                idx = parts[i]
                val = parts[i + 1]
                if idx == "2":
                    try:
                        last_price = float(val)
                    except Exception:
                        last_price = None
                    break
                i += 2

            if last_price is None:
                raise RuntimeError(f"Não foi possível extrair preço do SQT para {ativo}.")
            return last_price

    def get_gso(self, req_id: str, ativo: str, mes: int, ano: int) -> List[Dict[str, Any]]:
        """
        GSO <id> <ativo> <mês> <ano>
        Retorno: linhas "GSO:<id>:<ativo>:<opcao>:<tipo>" e por fim "GSO:<id>:<ativo>:END". (doc GSO)  :contentReference[oaicite:3]{index=3}
        """
        cmd = f"GSO {req_id} {ativo.upper()} {mes:02d} {ano}"
        self._conn.send_command(cmd)

        opcoes: List[Dict[str, Any]] = []

        while True:
            msg = self._get_next_msg()
            if msg is None:
                raise RuntimeError("Timeout aguardando resposta GSO.")

            msg = msg.strip()
            if not msg.startswith("GSO:"):
                continue

            parts = msg.split(":")
            # esperado: GSO, id, ativo, campo4, campo5
            if len(parts) < 4:
                continue

            if parts[3] == "END":
                # fim da lista
                break

            # GSO:001:PETR4:PETRJ93:C
            if len(parts) >= 5:
                symbol = parts[3]
                tipo = parts[4]  # C ou P
                opcoes.append(
                    {
                        "symbol": symbol,
                        "tipo": tipo,
                    }
                )

        return opcoes


# ----------------------------------------------------------------------
# Função de alto nível usada pelo Django
# ----------------------------------------------------------------------
def get_snapshot_ls(ativo: str, venc_atual_yyyymm: str, venc_prox_yyyymm: str) -> dict:
    """
    Executa SQT N (spot) + GSO (vencimento atual e próximo) e retorna
    um pacote simples com as informações necessárias para o LS.

    OBS.: aqui ainda retornamos apenas os símbolos das opções; preços/strikes
    serão obtidos depois via SQT por opção (em etapa futura do LS).
    """

    if len(venc_atual_yyyymm) != 6 or len(venc_prox_yyyymm) != 6:
        raise ValueError("Vencimentos devem estar no formato YYYYMM (ex.: 202510).")

    ano_atual = int(venc_atual_yyyymm[0:4])
    mes_atual = int(venc_atual_yyyymm[4:6])
    ano_prox = int(venc_prox_yyyymm[0:4])
    mes_prox = int(venc_prox_yyyymm[4:6])

    client = CedroClient()
    try:
        client.start()

        spot = client.get_spot(ativo)
        opcoes_atual = client.get_gso("001", ativo, mes_atual, ano_atual)
        opcoes_prox = client.get_gso("002", ativo, mes_prox, ano_prox)

        return {
            "ativo": ativo.upper(),
            "spot": spot,
            "venc_atual": venc_atual_yyyymm,
            "venc_prox": venc_prox_yyyymm,
            "opcoes_atual": opcoes_atual,
            "opcoes_prox": opcoes_prox,
        }
    finally:
        client.stop()
