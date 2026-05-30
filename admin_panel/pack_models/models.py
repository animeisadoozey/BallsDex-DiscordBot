from django.db import models
from django.db.models import Q, F

from bd_models.models import Player

class PackResource(models.Model):
    player = models.OneToOneField(
        Player, 
        on_delete=models.CASCADE, 
        related_name="pack_resource"
    )
    daily_uses = models.PositiveIntegerField(default=0)
    weekly_uses = models.PositiveIntegerField(default=0)
    daily_cooldown = models.DateTimeField(null=True, blank=True)
    weekly_cooldown = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "packresource"
        managed = True


class PackSettings(models.Model):
    min_rarity_daily = models.FloatField(help_text="Lowest rarity that can appear in daily packs.")
    max_rarity_daily = models.FloatField(help_text="Highest rarity that can appear in daily packs.")
    min_rarity_weekly = models.FloatField(help_text="Lowest rarity that can appear in weekly packs.")
    max_rarity_weekly = models.FloatField(help_text="Highest rarity that can appear in weekly packs.")

    class Meta:
        db_table = "packsettings"
        managed = True
        constraints = [
            models.CheckConstraint(
                condition=Q(min_rarity_daily__gte=0),
                name="packsettings_min_rarity_daily_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(max_rarity_daily__gte=0),
                name="packsettings_max_rarity_daily_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(min_rarity_weekly__gte=0),
                name="packsettings_min_rarity_weekly_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(max_rarity_weekly__gte=0),
                name="packsettings_max_rarity_weekly_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(min_rarity_daily__lte=F("max_rarity_daily")),
                name="packsettings_daily_min_lte_max",
            ),
            models.CheckConstraint(
                condition=Q(min_rarity_weekly__lte=F("max_rarity_weekly")),
                name="packsettings_weekly_min_lte_max",
            ),
        ]