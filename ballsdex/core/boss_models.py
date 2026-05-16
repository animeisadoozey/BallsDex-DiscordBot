from typing import TYPE_CHECKING

from tortoise import models, fields

from ballsdex.core.models import balls

if TYPE_CHECKING:
    from ballsdex.core.models import Ball, BallInstance, Player

boss_balls: dict[int, "BossBall"] = {}

class BossSettings(models.Model):
    ping_role_id = fields.BigIntField(
        description="An optional role id to notify users when a boss game starts.",
        null=True,
        default=None
    )

    @classmethod
    async def load(cls):
        boss_settings, created = await cls.get_or_create(pk=1)
        return boss_settings

class BossBall(models.Model):
    ball_id: int

    ball: fields.OneToOneRelation["Ball"] = fields.OneToOneField(
        "models.Ball",
        on_delete=fields.CASCADE,
        description="Ball who will be boss"
    )
    start_image = fields.CharField(
        max_length=200,
        null=True,
        default=None,
        description="Image used when the boss will start."
    )
    attack_image = fields.CharField(
        max_length=200,
        null=True,
        default=None,
        description="Image used when the boss will attack."
    )
    defense_image = fields.CharField(
        max_length=200,
        null=True,
        default=None,
        description="Image used when the boss will defense."
    )
    credits = fields.CharField(max_length=64, description="Author of boss arts", null=True, default=None)


    @property
    def cached_ball(self) -> "Ball":
        return balls.get(self.ball_id, self.ball)


class BossPlayer(models.Model):
    player: fields.OneToOneRelation["Player"] = fields.OneToOneField(
        "models.Player",
        on_delete=fields.CASCADE
    )
    name = fields.CharField(max_length=64)
    deaths = fields.BigIntField(default=0)
    damage = fields.BigIntField(default=0)
    kills = fields.BigIntField(default=0)


class BossHistory(models.Model):
    boss: fields.ForeignKeyRelation[BossBall] = fields.ForeignKeyField(
        "models.BossBall",
        on_delete=fields.CASCADE
    )
    player: fields.ForeignKeyRelation[BossPlayer] = fields.ForeignKeyField(
        "models.BossPlayer",
        on_delete=fields.CASCADE
    )
    ball_instance: fields.ForeignKeyNullableRelation["BallInstance"] = fields.ForeignKeyField(
        "models.BallInstance",
        on_delete=fields.CASCADE,
        null=True,
        default=None
    )
    damage = fields.BigIntField(default=0)
    dead = fields.BooleanField(default=False)
    won = fields.BooleanField(default=False)
    date = fields.DatetimeField(auto_now_add=True)
