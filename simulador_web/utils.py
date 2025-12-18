from django.shortcuts import redirect
from functools import wraps
import inspect
from asgiref.sync import sync_to_async


def subscription_required(view_func):

    def _check(request):
        if not request.user.is_authenticated:
            return "login"
        if not hasattr(request.user, "subscription"):
            return "expired"
        if not request.user.subscription.is_active():
            return "expired"
        return "ok"

    if inspect.iscoroutinefunction(view_func):
        @wraps(view_func)
        async def _wrapped(request, *args, **kwargs):
            status = await sync_to_async(_check)(request)

            if status == "login":
                # SEM mensagem
                return redirect("/accounts/login/?next=/app/ls/")

            if status == "expired":
                # sinaliza via querystring (SEM messages)
                return redirect("/?expired=1")

            return await view_func(request, *args, **kwargs)
        return _wrapped

    else:
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            status = _check(request)

            if status == "login":
                return redirect("/accounts/login/?next=/app/ls/")

            if status == "expired":
                return redirect("/?expired=1")

            return view_func(request, *args, **kwargs)
        return _wrapped
