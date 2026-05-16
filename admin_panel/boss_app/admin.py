from typing import TYPE_CHECKING

from django.contrib import admin

from boss_app.models import BossSettings, BossBall

if TYPE_CHECKING:
    from django.http import HttpRequest

@admin.register(BossSettings)
class BossSettingsAdmin(admin.ModelAdmin):
    save_on_top = True

    def has_add_permission(self, request: "HttpRequest") -> bool:
        return super().has_add_permission(request) and BossSettings.objects.first() is None

    def has_delete_permission(self, request: "HttpRequest", obj: BossSettings | None = None) -> bool:
        return False


@admin.register(BossBall)
class BossBallAdmin(admin.ModelAdmin):
    pass