from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.views.static import serve
from simulador_web.views import landing
from payments.webhooks import mercadopago_webhook

urlpatterns = [
    # Landing
    path("", landing, name="landing"),

    # App principal
    path("app/", include("simulador_web.urls")),

    # Admin
    path("admin/", admin.site.urls),

    # Login / Logout Django
    path("accounts/", include("django.contrib.auth.urls")),

    # Sitemap (servido via Django, SEM depender de static)
    path(
        "sitemap.xml",
        serve,
        {
            "document_root": settings.STATIC_ROOT,
            "path": "sitemap.xml",
        },
    ),

    path("payments/", include("payments.urls")),
    path("webhooks/mercado-pago/", mercadopago_webhook),
]
