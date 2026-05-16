from django.contrib import admin

from .models import BattleBuff, BattleBallRestriction

@admin.register(BattleBuff)
class BattleBuffAdmin(admin.ModelAdmin):
    pass


@admin.register(BattleBallRestriction)
class BattleBallRestrictionAdmin(admin.ModelAdmin):
    pass
