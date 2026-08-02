from django.apps import AppConfig


class MerchantAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "merchant_app"
    dpy_package = "merchant_app.package"
