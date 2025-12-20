from django.urls import path
from .views import long_straddle
from . import views


urlpatterns = [
    path("ls/", long_straddle, name="ls"),
    path("long/", long_straddle, name="long_straddle"),
    path("sair/", views.sair, name="logout"),
    path("planos/", views.planos, name="planos"),

]
