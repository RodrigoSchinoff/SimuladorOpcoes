from django.contrib import admin
from django.urls import path, include
from simulador_web.views import landing

urlpatterns = [
    path("", landing, name="landing"),          # LANDING PAGE
    path("app/", include("simulador_web.urls")),# APLICAÇÃO
    path("admin/", admin.site.urls),
]
