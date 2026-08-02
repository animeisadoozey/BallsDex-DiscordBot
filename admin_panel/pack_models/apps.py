from django.apps import AppConfig


class PackModelsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pack_models"
    dpy_package = "pack_models.package"
