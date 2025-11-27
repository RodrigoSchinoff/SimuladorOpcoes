from django.urls import path
from .views import home, long_straddle

urlpatterns = [
    path('', home, name='home'),
    path('ls/', long_straddle, name='long_straddle'),
]
