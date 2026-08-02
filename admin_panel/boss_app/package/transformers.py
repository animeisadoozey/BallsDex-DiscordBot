from typing import Iterable

from discord import app_commands

from ballsdex.core.utils.transformers import TTLModelTransformer
from settings.models import settings

from ..models import BossBall, boss_balls


class BossBallTransformer(TTLModelTransformer[BossBall]):
    name = settings.collectible_name
    model = BossBall

    def key(self, model: BossBall) -> str:
        return model.cached_ball.country

    async def load_items(self) -> Iterable[BossBall]:
        return [x for x in boss_balls.values()]


BossBallTransform = app_commands.Transform[BossBall, BossBallTransformer]
