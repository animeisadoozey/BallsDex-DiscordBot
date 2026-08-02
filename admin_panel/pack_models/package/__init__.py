from typing import TYPE_CHECKING

from ..models import PackSettings
from .cog import Pack

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    settings = await PackSettings.aload()
    await bot.add_cog(Pack(bot, settings))
