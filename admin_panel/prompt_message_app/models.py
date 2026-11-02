from django.db import models

from bd_models.models import Ball


# Create your models here.
class BallPromptMessage(models.Model):
    class PromptType(models.IntegerChoices):
        CATCH = 1
        WRONG = 2
        SPAWN = 3
        SLOW = 4

    ball = models.ForeignKey(Ball, on_delete=models.CASCADE, related_name="prompts")
    message = models.TextField(help_text="The message to send")
    category = models.PositiveSmallIntegerField(help_text="Message category", choices=PromptType)
    rarity = models.FloatField(default=1.0, help_text="Weight of message.")

    class Meta:
        managed = True
        db_table = "ballpromptmessage"
        constraints = (
            models.UniqueConstraint(fields=("message", "category"), name="ball_message_category_unique_together"),
        )

    def __str__(self) -> str:
        return self.message
