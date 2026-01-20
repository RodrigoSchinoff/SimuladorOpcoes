from django.urls import path
from .views import criar_assinatura
from .webhooks import mercadopago_webhook

urlpatterns = [
    path("assinatura/criar/", criar_assinatura),
    path("webhooks/mercado-pago/", mercadopago_webhook),
]
