from typing import TYPE_CHECKING

from .cog import Pack
from ballsdex.core.pack_models import PackSettings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

async def setup(bot: "BallsDexBot"):
    settings = await PackSettings.load()
    await bot.add_cog(Pack(bot, settings))
