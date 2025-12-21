from django.conf import settings
from django.db import models
from django.utils import timezone


class Role(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Subscription(models.Model):
    PLAN_CHOICES = (
        ("trial", "Trial"),
        ("pro", "Pro"),
    )

    STATUS_CHOICES = (
        ("active", "Active"),
        ("expired", "Expired"),
        ("blocked", "Blocked"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription",
    )

    plan = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES,
        default="trial",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    end_date = models.DateField()

    def is_active(self):
        return self.status == "active" and self.end_date >= timezone.now().date()


class PlanAssetList(models.Model):
    PLAN_CHOICES = (
        ("trial", "Trial"),
        ("pro", "Pro"),
    )

    plan = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES,
        unique=True,
    )

    assets = models.JSONField()

    class Meta:
        verbose_name = "Ativos do plano"
        verbose_name_plural = "Ativos do plano"

    def __str__(self):
        return f"Ativos do plano {self.plan}"


class Lead(models.Model):
    PLANO_CHOICES = (
        ("trial", "Trial"),
        ("pro", "Pro"),
    )

    STATUS_CHOICES = (
        ("novo", "Novo"),
        ("contatado", "Contatado"),
        ("convertido", "Convertido"),
    )

    nome = models.CharField(max_length=120)
    email = models.EmailField()
    whatsapp = models.CharField(max_length=20)
    cpf = models.CharField(max_length=14)
    plano_interesse = models.CharField(max_length=10, choices=PLANO_CHOICES)

    observacao = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="novo")

    ip_origem = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nome} - {self.email} ({self.plano_interesse})"
