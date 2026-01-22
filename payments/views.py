import json
import requests
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

MP_API_BASE = "https://api.mercadopago.com"


@csrf_exempt
def criar_assinatura(request):
    if request.method != "POST":
        return JsonResponse({"error": "Método inválido"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "JSON inválido"}, status=400)

    codigo = data.get("codigo")
    if not codigo:
        return JsonResponse({"error": "Código do plano ausente"}, status=400)

    PLANOS = {
        "BASICO_MENSAL": settings.MP_PLAN_BASICO_MENSAL,
        "BASICO_ANUAL": settings.MP_PLAN_BASICO_ANUAL,
        "PRO_MENSAL": settings.MP_PLAN_PRO_MENSAL,
        "PRO_ANUAL": settings.MP_PLAN_PRO_ANUAL,
        "TESTE": settings.MP_PLAN_TESTE,
    }

    plan_id = PLANOS.get(codigo)
    if not plan_id:
        return JsonResponse({"error": "Plano inválido"}, status=400)

    headers = {
        "Authorization": f"Bearer {settings.MP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    resp = requests.get(
        f"{MP_API_BASE}/preapproval_plan/{plan_id}",
        headers=headers,
        timeout=15,
    )

    resp.raise_for_status()
    data = resp.json()

    init_point = data.get("init_point")
    if not init_point:
        return JsonResponse({"error": "init_point não retornado pelo MP"}, status=500)

    return JsonResponse({"init_point": init_point})


@csrf_exempt
def webhook_mercadopago(request):
    # placeholder — será implementado depois
    return HttpResponse(status=200)
