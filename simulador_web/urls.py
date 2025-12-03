from django.urls import path
from .views import cedro_teste, cedro_debug, long_straddle, home

urlpatterns = [
    path("", home, name="home"),
    path("long-straddle/", long_straddle, name="long_straddle"),

    # ROTA DE TESTE CEDRO (não afeta o LS)
    path("cedro/teste/<str:ativo>/", cedro_teste, name="cedro_teste"),
    path("cedro/debug/", cedro_debug),
]
