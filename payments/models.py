from django.db import models
from django.conf import settings

class Assinatura(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    codigo = models.CharField(max_length=30)  # ex: pro_mensal
    preapproval_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)
