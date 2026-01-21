import json
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt


# =========================================
# CRIAR ASSINATURA (CHECKOUT HOSPEDADO)
# =========================================
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

    init_point = (
        "https://www.mercadopago.com.br/subscriptions/checkout"
        f"?preapproval_plan_id={plan_id}"
    )

    return JsonResponse({"init_point": init_point})


# =========================================
# WEBHOOK MERCADO PAGO
# =========================================
@csrf_exempt
def webhook_mercadopago(request):
    try:
        payload = json.loads(request.body or "{}")
        print("WEBHOOK MP:", payload)

        return HttpResponse(status=200)

    except Exception as e:
        print("WEBHOOK ERROR:", e)
        return HttpResponse(status=200)
