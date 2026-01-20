import json
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .services.mercadopago_client import MercadoPagoClient
from .models import Assinatura


# =========================================
# NÃO USADO NO FLUXO DE CHECKOUT HOSPEDADO
# (mantido para compatibilidade)
# =========================================
@csrf_exempt
def criar_assinatura(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Método inválido")

    try:
        body = json.loads(request.body)
        codigo = body.get("codigo")  # ex: pro_mensal

        assinatura = MercadoPagoClient.criar_assinatura(codigo)

        Assinatura.objects.create(
            codigo=codigo,
            preapproval_id=assinatura.get("id"),
            status=assinatura.get("status"),
        )

        return JsonResponse({
            "init_point": assinatura.get("init_point")
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# =========================================
# WEBHOOK MERCADO PAGO (CHECKOUT HOSPEDADO)
# =========================================
@csrf_exempt
def webhook_mercadopago(request):
    """
    Recebe notificações de:
    - Assinaturas
    - Pagamentos recorrentes
    """
    try:
        payload = json.loads(request.body or "{}")
        print("WEBHOOK MP:", payload)

        # Estrutura típica do webhook
        action = payload.get("action")          # ex: subscription_preapproval.updated
        data = payload.get("data", {})
        preapproval_id = data.get("id")

        if not preapproval_id:
            return HttpResponse(status=200)

        # Busca a assinatura no MP para status real
        mp_data = MercadoPagoClient.buscar_assinatura(preapproval_id)
        status = mp_data.get("status")

        # Atualiza ou cria no banco
        assinatura, _ = Assinatura.objects.update_or_create(
            preapproval_id=preapproval_id,
            defaults={
                "status": status,
            }
        )

        # Aqui você decide o que fazer por status
        if status == "authorized":
            # TODO: liberar acesso ao usuário
            pass

        return HttpResponse(status=200)

    except Exception as e:
        print("WEBHOOK ERROR:", e)
        return HttpResponse(status=200)
