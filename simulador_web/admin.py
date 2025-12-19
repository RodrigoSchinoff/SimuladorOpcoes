from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Subscription, Role
from .models import PlanAssetList

User = get_user_model()


class SubscriptionInline(admin.StackedInline):
    model = Subscription
    can_delete = False
    extra = 0


class CustomUserAdmin(UserAdmin):
    inlines = [SubscriptionInline]

    fieldsets = UserAdmin.fieldsets + (
        ("Assinatura", {"fields": ()}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        # garante que todo usuário tenha assinatura
        if not hasattr(obj, "subscription"):
            Subscription.objects.create(
                user=obj,
                end_date=timezone.now().date() + timezone.timedelta(days=30),
            )


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
admin.site.register(Role)
admin.site.register(PlanAssetList)
