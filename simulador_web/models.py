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


# =========================================================
# NOVO MODEL — HISTÓRICO DE IV ATM (LONG STRADDLE)
# =========================================================

class IvAtmHistorico(models.Model):
    ticker = models.CharField(max_length=20)
    trade_date = models.DateField()

    spot_price = models.DecimalField(max_digits=15, decimal_places=4)

    # CALL ATM
    call_symbol = models.CharField(max_length=30)
    call_due_date = models.DateField()
    call_days_to_maturity = models.IntegerField()
    call_premium = models.DecimalField(max_digits=15, decimal_places=6)
    call_volatility = models.DecimalField(max_digits=10, decimal_places=6)

    # PUT ATM
    put_symbol = models.CharField(max_length=30)
    put_due_date = models.DateField()
    put_days_to_maturity = models.IntegerField()
    put_premium = models.DecimalField(max_digits=15, decimal_places=6)
    put_volatility = models.DecimalField(max_digits=10, decimal_places=6)

    # Média diária
    iv_atm_mean = models.DecimalField(max_digits=10, decimal_places=6)

    # Auditoria
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iv_atm_historico"
        unique_together = ("ticker", "trade_date")
        indexes = [
            models.Index(fields=["ticker", "trade_date"]),
        ]

    def __str__(self):
        return f"{self.ticker} - {self.trade_date}"


class EarningsDate(models.Model):
    ticker = models.CharField(max_length=20)
    earnings_date = models.DateField()
    announcement_time = models.CharField(max_length=20)
    source = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("ticker", "earnings_date")
        indexes = [
            models.Index(fields=["ticker", "earnings_date"]),
        ]

    def __str__(self):
        return f"{self.ticker} - {self.earnings_date} ({self.announcement_time})"


    def __str__(self):
        return f"{self.ticker} - {self.earnings_date} ({self.announcement_time})"
