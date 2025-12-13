from django.urls import path
from .views import long_straddle

urlpatterns = [
    path("ls/", long_straddle, name="ls"),
    path("long/", long_straddle, name="long_straddle"),
]
