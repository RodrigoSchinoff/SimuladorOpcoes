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
