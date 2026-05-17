from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise import models, fields
from tortoise.contrib.postgres.indexes import PostgreSQLIndex

if TYPE_CHECKING:
    from ballsdex.core.models import Ball, BallInstance, Player, Special

class BattleBuff(models.Model):
    ball: fields.OneToOneNullableRelation["Ball"] = fields.OneToOneField(
        "models.Ball",
        on_delete=fields.CASCADE,
        null=True,
        default=None,
        description="Ball that will receive an increase"
    )
    special: fields.OneToOneNullableRelation["Special"] = fields.OneToOneField(
        "models.Special",
        on_delete=fields.CASCADE,
        null=True,
        default=None,
        description="Specials that will receive an increase",
    )
    health = fields.IntField(default=0, description="Amount of health to add")
    attack = fields.IntField(default=0, description="Amount of attack to add")


class Battle(models.Model):
    date = fields.DatetimeField(auto_now_add=True)
    player1: fields.ForeignKeyRelation["Player"] = fields.ForeignKeyField(
        "models.Player", related_name="battles"
    )
    player2: fields.ForeignKeyRelation["Player"] = fields.ForeignKeyField(
        "models.Player", related_name="battles2"
    )
    winner: fields.ForeignKeyRelation["Player"] = fields.ForeignKeyField(
        "models.Player", related_name="wins"
    )
    battleobjects: fields.ReverseRelation[BattleObject]
    finished = fields.BooleanField(default=False)

    class Meta:
        indexes = [
            PostgreSQLIndex(fields=("player1_id",)),
            PostgreSQLIndex(fields=("player2_id",)),
            PostgreSQLIndex(fields=("winner_id",)),
        ]

class BattleObject(models.Model):
    battle: fields.ForeignKeyRelation["Battle"] = fields.ForeignKeyField(
        "models.Battle", on_delete=fields.CASCADE, related_name="battleobjects"
    )
    ballinstance: fields.ForeignKeyRelation["BallInstance"] = fields.ForeignKeyField(
        "models.BallInstance", on_delete=fields.CASCADE, related_name="battleobjects"
    )
    player: fields.ForeignKeyRelation["Player"] = fields.ForeignKeyField(
        "models.Player", on_delete=fields.CASCADE, related_name="battleobjects"
    )
    health = fields.IntField(default=0)
    attack = fields.IntField(default=0)

    class Meta:
        indexes = [
            PostgreSQLIndex(fields=("battle_id",)),
            PostgreSQLIndex(fields=("ballinstance_id",)),
            PostgreSQLIndex(fields=("player_id",)),
        ]


class BattleBallRestriction(models.Model):
    ball: fields.OneToOneRelation["Ball"] = fields.OneToOneField(
        "models.Ball",
        on_delete=fields.CASCADE,
        description="Ball that you want to ban."
    )

