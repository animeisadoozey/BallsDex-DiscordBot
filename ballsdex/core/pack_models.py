from datetime import timedelta
from typing import TYPE_CHECKING
from tortoise import models, fields, timezone

if TYPE_CHECKING:
    from .models import Player

class PackResource(models.Model):
    player: fields.OneToOneRelation["Player"] = fields.OneToOneField(
        "models.Player", 
        on_delete=fields.CASCADE, 
        related_name="pack_resource"
    )
    daily_uses = fields.IntField(default=0)
    weekly_uses = fields.IntField(default=0)
    daily_cooldown = fields.DatetimeField(null=True)
    weekly_cooldown = fields.DatetimeField(null=True)

    async def set_daily_cooldown(self):
        self.daily_cooldown = timezone.now()
        await self.save(update_fields=("daily_cooldown",))
    
    async def set_weekly_cooldown(self):
        self.weekly_cooldown = timezone.now()
        await self.save(update_fields=("weekly_cooldown",))
    
    async def remove_daily_cooldown(self):
        self.daily_cooldown = None
        self.daily_uses = 0
        await self.save(update_fields=("daily_cooldown", "daily_uses"))
    
    async def remove_weekly_cooldown(self):
        self.weekly_cooldown = None
        self.weekly_uses = 0
        await self.save(update_fields=("weekly_cooldown", "weekly_uses"))

    async def is_daily_on_cooldown(self) -> bool:
        await self.refresh_from_db(fields=("daily_cooldown",))
        self.daily_cooldown
        return self.daily_cooldown is not None and (self.daily_cooldown + timedelta(days=1)) > timezone.now()

    async def is_weekly_on_cooldown(self) -> bool:
        await self.refresh_from_db(fields=("weekly_cooldown",))
        self.weekly_cooldown
        return self.weekly_cooldown is not None and (self.weekly_cooldown + timedelta(weeks=1)) > timezone.now()


class PackSettings(models.Model):
    min_rarity_daily = fields.FloatField(description="Lowest rarity that can appear in daily packs.")
    max_rarity_daily = fields.FloatField(description="Highest rarity that can appear in daily packs.")
    min_rarity_weekly = fields.FloatField(description="Lowest rarity that can appear in weekly packs.")
    max_rarity_weekly = fields.FloatField(description="Highest rarity that can appear in weekly packs.")

    @classmethod
    async def load(cls):
        obj, _ = await cls.get_or_create(
            pk=1,
            defaults={
                "min_rarity_daily": 50.0,
                "max_rarity_daily": 100.0,
                "min_rarity_weekly": 1.0,
                "max_rarity_weekly": 50.0,
            }
        )
        return obj