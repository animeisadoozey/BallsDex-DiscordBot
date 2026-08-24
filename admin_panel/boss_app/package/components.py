import logging
from typing import TYPE_CHECKING

import discord
from discord.ui import ActionRow, Button, LayoutView, MediaGallery, TextDisplay

from ballsdex.core.utils.menus.old import ListPageSource, Pages
from bd_models.models import Player
from settings.models import settings

from ..models import BossHistory, BossPlayer
from .types import BossGamePlayer

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

    from .cog import Boss

log = logging.getLogger(__name__)


class JoinGameView(LayoutView):
    text = TextDisplay("")
    gallery = MediaGallery()
    row = ActionRow()

    def __init__(self, message: discord.Message, cog: "Boss", timeout: int = 180):
        self.cog = cog
        self.original_message = message
        self.time_join = timeout
        super().__init__(timeout=None)

    @row.button(style=discord.ButtonStyle.success, label="Join!")
    async def join_button(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        assert interaction.guild_id
        if not self.cog.exists_boss_game(interaction.guild_id):
            await interaction.response.send_message("There isn't an active boss game in the server.", ephemeral=True)
            return
        boss_game = self.cog.active_bosses[interaction.guild_id]
        if interaction.user.id in boss_game.players:
            await interaction.response.send_message("You've already joined to the boss game.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        boss_player, _ = await BossPlayer.objects.aget_or_create(
            player=player, defaults={"name": interaction.user.display_name}
        )

        boss_game.players[interaction.user.id] = BossGamePlayer(boss_game.boss, boss_player)
        await interaction.followup.send("You've joined to the boss game! Good luck.", ephemeral=True)
        return

    async def on_timeout(self):
        self.stop()
        for item in self.walk_children():
            if not isinstance(item, ActionRow):
                continue

            for row in item.walk_children():
                if not isinstance(row, Button):
                    continue

                row.disabled = True

        try:
            assert self.original_message.guild
            game = self.cog.active_bosses[self.original_message.guild.id]
            await self.original_message.edit(view=self)
            if len(game.players) < 0:
                await self.original_message.reply("No one players have joined, cancelling game...")
                self.cog.active_bosses.pop(self.original_message.guild.id, None)
        except Exception:
            log.exception("Failed to edit join message.")
            pass


class BossHistoryFormat(ListPageSource):
    def __init__(self, bot: "BallsDexBot", entries: list[BossHistory]):
        self.bot = bot
        super().__init__(entries, per_page=1)

    async def format_page(self, menu: Pages, page: BossHistory) -> discord.Embed:
        embed = discord.Embed(
            title=f"History #{page.pk:0X}: {page.boss.cached_ball.country}",
            color=discord.Color.blurple(),
            timestamp=page.date,
        )
        description = f"**Damage:** {page.damage}\n"
        if page.ball_instance:
            description += (
                f"**{settings.collectible_name.title()}:** "
                f"{page.ball_instance.description(bot=self.bot, include_emoji=True, short=True)}\n"
            )
        if page.won:
            description += "You won this boss.\n"
        else:
            description += "You lost this boss.\n"
        embed.description = description
        embed.set_footer(text=f"{menu.current_page + 1}/{menu.source.get_max_pages()} | Boss Date: ")
        return embed
