import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import discord
from battle_app.models import BattleBallRestriction, BattleBuff
from cachetools import TTLCache
from discord import app_commands
from discord.ext import commands
from discord.utils import format_dt

from ballsdex.core.utils import checks
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.menus.old import Pages
from ballsdex.core.utils.transformers import BallInstanceTransform
from bd_models.models import GuildConfig, Player
from settings.models import settings

from ..models import BossBall, BossHistory, BossPlayer, BossSettings, boss_balls
from .components import BossHistoryFormat, JoinGameView
from .transformers import BossBallTransform
from .types import BossGame, BossGameBall, BossGameType

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger(__name__)


class Boss(commands.GroupCog):
    """
    Fight and defeat countryball boss!
    """

    def __init__(self, bot: "BallsDexBot") -> None:
        self.bot = bot
        self.active_bosses: TTLCache[int, BossGame] = TTLCache(maxsize=999999, ttl=1800)
        self.boss_settings: BossSettings | None = None

    admin = app_commands.Group(
        name="admin",
        description="Boss admin commands",
        allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=False),
        allowed_installs=app_commands.AppInstallationType(guild=True, user=False),
        default_permissions=discord.Permissions(administrator=True),
    )

    async def cog_load(self):
        guilds = [
            discord.Object(guild_id)
            async for guild_id in GuildConfig.objects.filter(admin_command_synced=True).values_list(
                "guild_id", flat=True
            )
        ]
        self.bot.tree.remove_command(self.admin.name)
        self.bot.tree.add_command(self.admin, guilds=guilds, override=True)
        if self.app_command:
            self.bot.tree.remove_command(self.app_command.name)
            self.bot.tree.add_command(self.app_command, guilds=guilds, override=True)

    @commands.group()
    async def boss(self, ctx: commands.Context["BallsDexBot"]):
        pass

    @boss.command()
    @commands.is_owner()
    async def reloadcache(self, ctx: commands.Context["BallsDexBot"]):
        """
        Reload boss models cache.
        """
        boss_balls.clear()
        async for boss_ball in BossBall.objects.all():
            boss_balls[boss_ball.pk] = boss_ball

        log.info(f"Cached {len(boss_balls)} boss balls")
        await ctx.message.add_reaction("✅")

    @admin.command(name="start")
    @checks.app_check(checks.is_staff())
    async def admin_start(
        self,
        interaction: discord.Interaction,
        boss: BossBallTransform,
        type: BossGameType,
        health: int,
        attack: int,
        time_join: int,
        buffs: bool = True,
    ):
        """
        Starts a boss game.

        Parameters
        ----------
        boss: BossBall
            The countryball that will be the boss.
        type: BossGameType
            The win condition type.
        health: int
            Initial health of the boss
        attack: int
            Initial attack of the boss
        time_join: int
            Time (in seconds) allowed to join the boss game.
        buffs: bool
            Whether or not you want to allow buffs in the boss.
        """
        guild = interaction.guild
        assert guild
        if guild.unavailable:
            await interaction.response.send_message(
                "The server is unavailable to the bot and will not work properly. "
                "Kicking and readding the bot may fix this.",
                ephemeral=True,
            )
            return
        channel = interaction.channel
        if not isinstance(channel, discord.abc.Messageable):
            await interaction.response.send_message(
                "This channel isn't a valid channel to start a boss game.", ephemeral=True
            )
            return

        if self.exists_boss_game(guild.id):
            await interaction.response.send_message(
                "There's already an active boss game in the server.", ephemeral=True
            )
            return

        settings = await self.load_boss_settings()
        boss_game = BossGame(guild.id, boss, type, health, attack, buffs)
        duration = timedelta(seconds=time_join)
        end_time = datetime.now() + duration

        message = await channel.send(content="⌛ Starting Boss...")
        await asyncio.sleep(1.5)
        view = JoinGameView(message, self, time_join)
        boss_game.view = view
        self.active_bosses[guild.id] = boss_game
        role = guild.get_role(settings.ping_role_id or 0)
        select_mention = self.select.extras.get("mention", "`/boss select`")
        view.text.content = (
            f"A boss fight has appeared, fight and win! Once you've joined, use {select_mention}\n"
            f"It will start in {format_dt(end_time, 'R')}.\n\n"
            "# Information\n"
            f"> Win Condition: {type.name}\n"
        )
        if boss.credits:
            view.text.content += f"> Artwork Credits: {boss.credits}\n"
        image_art = boss_game.get_boss_image("start")
        view.gallery.add_item(media=image_art)

        await message.edit(content=None, view=view, attachments=[image_art])
        if role:
            if role.is_default():
                await message.reply(content=role.name)
            else:
                await message.reply(content=role.mention)
        self.bot.loop.create_task(view.start_game_countdown())
        return

    @admin.command(name="stop")
    @checks.app_check(checks.is_staff())
    async def admin_stop(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Stop the ongoing boss game.
        """
        assert interaction.guild_id
        if not self.exists_boss_game(interaction.guild_id):
            await interaction.response.send_message("There isn't an active boss game in the server.", ephemeral=True)
            return
        game = self.active_bosses[interaction.guild_id]
        await interaction.response.send_message("Done! The boss game is finishing in a few moments...", ephemeral=True)
        if game.task and not game.task.done():
            await game.stop()
        self.active_bosses.pop(interaction.guild_id, None)
        await interaction.edit_original_response(content="Boss has been cancelled.")

    @app_commands.command()
    async def ongoing(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Show your stats in the current boss game.
        """
        assert interaction.guild_id
        if not self.exists_boss_game(interaction.guild_id):
            await interaction.response.send_message("There isn't an active boss game in the server.", ephemeral=True)
            return
        game = self.active_bosses[interaction.guild_id]
        player = game.get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("You aren't in the boss game.", ephemeral=True)
            return
        embed = discord.Embed(title=f"{player.boss_player.name}'s stats", color=discord.Color.blurple())
        description = f"**Damage:** {player.damage}\n**Dead:** {'Yes' if player.dead else 'No'}\n"
        if player.current_instance:
            description += (
                f"**{settings.collectible_name.title()}:** "
                f"{player.current_instance.instance.description(bot=self.bot, include_emoji=True, short=True)}"
            )
        embed.description = description
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command()
    async def history(self, interaction: discord.Interaction["BallsDexBot"], boss: BossBallTransform | None = None):
        """
        Show your boss history.

        Parameters
        ----------
        boss: BossBall
            Filter history by a specific boss ball.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            player = await Player.objects.aget(discord_id=interaction.user.id)
            boss_player = await BossPlayer.objects.aget(player=player)
        except (Player.DoesNotExist, BossPlayer.DoesNotExist):
            await interaction.followup.send("You don't have any boss records.")
            return

        query = BossHistory.objects.prefetch_related("boss", "ball_instance").filter(player=boss_player)
        if boss:
            query = query.filter(boss=boss)
        histories = [x async for x in query]
        if not histories:
            await interaction.followup.send("You don't have any boss records.")
            return

        source = BossHistoryFormat(self.bot, histories)
        paginator = Pages(source, interaction=interaction, compact=True)
        await paginator.start()

    @app_commands.command()
    async def select(self, interaction: discord.Interaction["BallsDexBot"], countryball: BallInstanceTransform):
        """
        Select a countryball that will fight in the boss game.

        Parameters
        ----------
        countryball: BallInstance
            The countryball that will fight.
        """
        if not countryball:
            return
        assert interaction.guild_id
        if not self.exists_boss_game(interaction.guild_id):
            await interaction.response.send_message("There isn't an active boss game in the server.", ephemeral=True)
            return

        game = self.active_bosses[interaction.guild_id]
        player = game.get_player(interaction.user.id)

        if not game.pick_time:
            await interaction.response.send_message(
                f"It's not the time to select a {settings.collectible_name}", ephemeral=True
            )
            return

        if not player:
            await interaction.response.send_message("You aren't in the boss game or you have died.", ephemeral=True)
            return

        if player.picked:
            await interaction.response.send_message(
                f"You have selected an {settings.collectible_name}.", ephemeral=True
            )
            return

        if await countryball.is_locked():
            await interaction.response.send_message(
                f"This {settings.collectible_name} is currently locked for a trade. Please try again later.",
                ephemeral=True,
            )
            return

        ball = countryball.countryball
        restricted = await BattleBallRestriction.objects.filter(ball=ball).aexists()
        if not ball.enabled or restricted:
            await interaction.followup.send(
                f"This {settings.collectible_name} isn't allowed in battle mode.", ephemeral=True
            )
            return

        if any(x.pk == countryball.pk for x in player.instances):
            await interaction.response.send_message(
                f"You've already selected this {settings.collectible_name} before.", ephemeral=True
            )
            return

        view = ConfirmChoiceView(
            interaction,
            accept_message=f"Confirmed, adding {settings.collectible_name}...",
            cancel_message="Request cancelled.",
        )
        description = countryball.description(bot=self.bot, include_emoji=True)
        await interaction.response.send_message(
            f"Are you sure you want to add {description} in the game? You won't be able to change it later.",
            view=view,
            ephemeral=True,
        )
        await view.wait()
        if not view.value:
            return

        boss_ball = BossGameBall(countryball, countryball.health, countryball.attack)
        if game.buffs:
            buff = await BattleBuff.objects.filter(ball=countryball.countryball).afirst()

            if not buff:
                special = countryball.specialcard
                if special:
                    buff = await BattleBuff.objects.filter(special=special).afirst()
            if buff:
                boss_ball.health += buff.health
                boss_ball.attack += buff.attack
        player.current_instance = boss_ball
        player.instances.append(boss_ball.instance)
        player.picked = True
        await interaction.followup.send(f"{settings.collectible_name.title()} selected.", ephemeral=True)
        return

    @app_commands.command()
    async def stats(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        View your boss stats.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            player = await Player.objects.aget(discord_id=interaction.user.id)
            boss_player = await BossPlayer.objects.aget(player=player)
        except (Player.DoesNotExist, BossPlayer.DoesNotExist):
            await interaction.followup.send("You don't have any boss records.")
            return

        embed = discord.Embed(title=f"{interaction.user.display_name}'s Stats", color=discord.Color.blurple())
        embed.add_field(name="☠️ Total Deaths", value=f"{boss_player.deaths:,}")
        embed.add_field(name="⚔️ Total Damage", value=f"{boss_player.damage:,}")
        embed.add_field(name="👑 Total Kills", value=f"{boss_player.kills:,}")
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    def exists_boss_game(self, guild_id: int):
        return guild_id in self.active_bosses

    async def load_boss_settings(self):
        if self.boss_settings is not None:
            await self.boss_settings.arefresh_from_db()
        else:
            self.boss_settings = await BossSettings.aload()
        return self.boss_settings
