from django.contrib import admin
from django.urls import path, include
from simulador_web.views import landing

urlpatterns = [
    path("", landing, name="landing"),
    path("app/", include("simulador_web.urls")),
    path("admin/", admin.site.urls),

    # ✅ login/logout padrão do Django
    path("accounts/", include("django.contrib.auth.urls")),
]
