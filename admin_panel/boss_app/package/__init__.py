import logging
from typing import TYPE_CHECKING

from .cog import Boss

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger(__name__)


async def setup(bot: "BallsDexBot"):
    from ..models import BossBall, boss_balls

    boss_balls.clear()
    async for boss_ball in BossBall.objects.all():
        boss_balls[boss_ball.pk] = boss_ball

    log.info(f"Cached {len(boss_balls)} boss balls")
    await bot.add_cog(Boss(bot))
