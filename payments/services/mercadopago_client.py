import os
import requests
from .pricing import PRICING

MP_API_BASE = "https://api.mercadopago.com"
ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")


class MercadoPagoClient:

    @staticmethod
    def criar_assinatura(codigo_preco: str):
        if codigo_preco not in PRICING:
            raise ValueError("Plano inválido")

        cfg = PRICING[codigo_preco]

        payload = {
            "reason": f"Algop {cfg['plano'].capitalize()} ({cfg['tipo']})",
            "payer_email": "rodrigo.scholiveira@gmail.com",  # TESTE
            "auto_recurring": {
                "frequency": cfg["frequencia"],
                "frequency_type": "months",
                "transaction_amount": cfg["valor"],
                "currency_id": "BRL",
            },
            "back_url": "https://algop.com.br/retorno-pagamento/",
        }

        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

        resp = requests.post(
            f"{MP_API_BASE}/preapproval",
            json=payload,
            headers=headers,
            timeout=15,
        )

        print("MP STATUS:", resp.status_code)
        print("MP BODY:", resp.text)

        resp.raise_for_status()
        return resp.json()

