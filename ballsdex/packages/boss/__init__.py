import logging
from typing import TYPE_CHECKING

from .cog import Boss

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger(__name__)


async def setup(bot: "BallsDexBot"):
    from ballsdex.core.boss_models import BossBall, boss_balls

    boss_balls.clear()
    for boss_ball in await BossBall.all():
        boss_balls[boss_ball.pk] = boss_ball

    log.info(f"Cached {len(boss_balls)} boss balls")
    await bot.add_cog(Boss(bot))
