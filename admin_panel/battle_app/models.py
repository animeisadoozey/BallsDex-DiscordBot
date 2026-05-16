from __future__ import annotations

from typing import Iterable

from django.db import models
from django.forms import ValidationError

from bd_models.models import Ball, BallInstance, Player, Special

class BattleBuff(models.Model):
    ball = models.OneToOneField(
        Ball,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Ball that will receive an increase"
    )
    special = models.OneToOneField(
        Special,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Specials that will receive an increase",
    )
    health = models.IntegerField(default=0, help_text="Amount of health to add")
    attack = models.IntegerField(default=0, help_text="Amount of attack to add")


    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        has_ball = self.ball is not None
        has_special = self.special is not None
        if not has_ball and not has_special:
            raise ValidationError(
                "You must provide either a ball or a special."
            )

        if has_ball and has_special:
            raise ValidationError(
                "You cannot set both a ball and a special."
            )

        return super().save(force_insert, force_update, using, update_fields)

    class Meta:
        db_table = "battlebuff"
        managed = True


class Battle(models.Model):
    date = models.DateTimeField(auto_now_add=True, editable=False)
    player1 = models.ForeignKey(Player, on_delete=models.CASCADE)
    player1_id: int
    player2 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="battle_player2_set")
    player2_id: int
    winner = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        related_name="battle_winner_set",
        null=True,
        blank=True
    )
    winner_id: int | None
    battleobject_set: models.QuerySet[BattleObject]
    finished = models.BooleanField(default=False)

    class Meta:
        managed = True
        db_table = "battle"
        indexes = [
            models.Index(fields=("player1_id",)),
            models.Index(fields=("player2_id",)),
            models.Index(fields=("winner_id",))
        ]


class BattleObject(models.Model):
    battle = models.ForeignKey(Battle, on_delete=models.CASCADE)
    battle_id: int
    ballinstance = models.ForeignKey(BallInstance, on_delete=models.CASCADE)
    ballinstance_id: int
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    player_id: int
    health = models.IntegerField(default=0)
    attack = models.IntegerField(default=0)

    class Meta:
        managed = True
        db_table = "battleobject"
        indexes = [
            models.Index(fields=("battle_id",)),
            models.Index(fields=("ballinstance_id",)),
            models.Index(fields=("player_id",))
        ]

class BattleBallRestriction(models.Model):
    ball = models.OneToOneField(Ball, on_delete=models.CASCADE, help_text="Ball that you want to ban.")

    class Meta:
        managed = True
        db_table = "battleballrestriction"
