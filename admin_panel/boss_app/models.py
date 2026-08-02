import re

from asgiref.sync import sync_to_async
from django.core.validators import RegexValidator
from django.db import models

from bd_models.models import Ball, BallInstance, Player, balls

DISCORD_ID_RE = re.compile(r"^\d{17,20}$")
boss_balls: dict[int, "BossBall"] = {}


class BossSettings(models.Model):
    """
    Singleton model.
    """

    ping_role_id = models.BigIntegerField(
        help_text="An optional role id to notify users when a boss game starts.",
        validators=(RegexValidator(DISCORD_ID_RE, message="Only Discord Role ID are supported."),),
        null=True,
        blank=True,
    )

    @classmethod
    def load(cls):
        boss_settings, created = cls.objects.get_or_create(pk=1)
        return boss_settings

    @classmethod
    async def aload(cls):
        return await sync_to_async(cls.load)()

    def __str__(self):
        return "Boss Settings"

    class Meta:
        managed = True
        db_table = "bosssettings"
        verbose_name_plural = "BossSettings"


class BossBall(models.Model):
    ball = models.OneToOneField(Ball, on_delete=models.CASCADE, help_text="Ball who will be boss")
    ball_id: int
    start_image = models.ImageField(
        max_length=200, null=True, blank=True, help_text="Image used when the boss will start."
    )
    attack_image = models.ImageField(
        max_length=200, null=True, blank=True, help_text="Image used when the boss will attack."
    )
    defense_image = models.ImageField(
        max_length=200, null=True, blank=True, help_text="Image used when the boss will defense."
    )
    credits = models.CharField(max_length=64, help_text="Author of boss arts", null=True, blank=True)

    @property
    def cached_ball(self) -> "Ball":
        return balls.get(self.ball_id) or self.ball

    class Meta:
        managed = True
        db_table = "bossball"


class BossPlayer(models.Model):
    player = models.OneToOneField(Player, on_delete=models.CASCADE)
    name = models.CharField(max_length=64)
    deaths = models.PositiveBigIntegerField(default=0)
    damage = models.PositiveBigIntegerField(default=0)
    kills = models.PositiveBigIntegerField(default=0)

    class Meta:
        managed = True
        db_table = "bossplayer"


class BossHistory(models.Model):
    boss = models.ForeignKey(BossBall, on_delete=models.CASCADE)
    player = models.ForeignKey(BossPlayer, on_delete=models.CASCADE)
    ball_instance = models.ForeignKey(BallInstance, on_delete=models.CASCADE, null=True, blank=True)
    damage = models.PositiveBigIntegerField(default=0)
    dead = models.BooleanField(default=False)
    won = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = True
        db_table = "bosshistory"
