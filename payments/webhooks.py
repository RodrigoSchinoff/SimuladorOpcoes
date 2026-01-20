import json
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Assinatura
import requests
import os

MP_TOKEN = os.getenv("MP_ACCESS_TOKEN")

@csrf_exempt
def mercadopago_webhook(request):
    data = json.loads(request.body or "{}")

    preapproval_id = data.get("data", {}).get("id")
    if not preapproval_id:
        return HttpResponse(status=200)

    resp = requests.get(
        f"https://api.mercadopago.com/preapproval/{preapproval_id}",
        headers={"Authorization": f"Bearer {MP_TOKEN}"},
        timeout=10,
    )

    if resp.status_code == 200:
        status = resp.json().get("status")
        Assinatura.objects.filter(preapproval_id=preapproval_id).update(status=status)

    return HttpResponse(status=200)
