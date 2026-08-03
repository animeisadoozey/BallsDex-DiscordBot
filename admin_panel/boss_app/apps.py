from django.apps import AppConfig


class BossAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "boss_app"
    dpy_package = "boss_app.package"
