from django.urls import path
from .views import long_straddle

urlpatterns = [
    path("", long_straddle, name="long_straddle"),  # /  -> LS
    path("ls/", long_straddle, name="ls"),          # /ls/ -> LS (atalho)
]
