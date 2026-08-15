import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import discord
from currency_app.models import CurrencySettings, MoneyInstance
from currency_app.models import Item as ItemModel
from discord import app_commands
from discord.ext import commands
from discord.utils import format_dt
from django.utils.timezone import get_default_timezone, now

from ballsdex.core.utils.menus.old import Pages
from bd_models.models import Ball, BallInstance, Player, Special, specials
from settings.models import settings

from ..models import PackResource, PackSettings
from .components import ShopMenuSource
from .transformers import ItemTransform

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class Pack(commands.GroupCog):
    """
    Claim a daily/weekly pack!
    """

    def __init__(self, bot: "BallsDexBot", settings: "PackSettings") -> None:
        self.bot = bot
        self.settings = settings

    @commands.group()
    async def pack(self, ctx: commands.Context["BallsDexBot"]):
        """
        Pack Prefix Commands.
        """
        pass

    @pack.command()
    @commands.is_owner()
    async def reloadconf(self, ctx: commands.Context["BallsDexBot"]):
        """
        Reload Pack Settings.
        """
        await self.settings.arefresh_from_db()
        await ctx.message.add_reaction("✅")

    @app_commands.command(name="daily")
    async def daily(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Claim your daily pack! (3 uses)
        """
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        resource, _ = await PackResource.objects.aget_or_create(player=player)
        if await resource.is_daily_on_cooldown():
            await interaction.response.send_message(
                f"You've used all daily packs. "
                f"Come back {format_dt(resource.daily_cooldown + timedelta(days=1), style='R')}!",  # type: ignore
                ephemeral=True,
            )
            return
        if self.settings.min_rarity_daily is None or self.settings.max_rarity_daily is None:
            await interaction.response.send_message(
                "Daily packs are not configured. Contact support if this persists.", ephemeral=True
            )
            return

        if resource.daily_cooldown is not None:
            await resource.remove_daily_cooldown()
        await interaction.response.defer()
        balls = [
            x
            async for x in Ball.objects.filter(
                enabled=True,
                tradeable=True,
                rarity__range=(self.settings.min_rarity_daily, self.settings.max_rarity_daily),
            )
        ]
        ball = await self._get_random_countryball(balls)
        rarity = ball.rarity
        instance = await BallInstance.objects.acreate(
            player=player,
            ball=ball,
            health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
            attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
        )
        embed = discord.Embed(title=f"🎁 You got {ball.country}!", color=discord.Color.gold())
        desc = f"📖 **Rarity:** {rarity}\n❤️ **Health:** {ball.health}\n⚔️ **Attack:** {ball.attack}\n"
        embed.description = desc
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        footer_text = (
            f"Uses: {resource.daily_uses}/3. Come back tomorrow."
            if resource.daily_uses >= 3
            else f"Uses: {resource.daily_uses}/3."
        )
        embed.set_footer(text=footer_text)
        try:
            with ThreadPoolExecutor() as pool:
                buffer = await interaction.client.loop.run_in_executor(pool, instance.draw_card)
            file = discord.File(buffer, "card.webp")
            embed.set_image(url="attachment://card.webp")
            await interaction.followup.send(embed=embed, file=file)
        except OSError:
            await interaction.followup.send(embed=embed)
        else:
            resource.daily_uses += 1
            if resource.daily_uses >= 3:
                await resource.set_daily_cooldown()
            await resource.asave(update_fields=("daily_uses",))

    @app_commands.command(name="weekly")
    async def weekly(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Claim your weekly pack!
        """
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        resource, _ = await PackResource.objects.aget_or_create(player=player)
        if await resource.is_weekly_on_cooldown():
            await interaction.response.send_message(
                f"You've used all weekly packs. "
                f"Come back {format_dt(resource.weekly_cooldown + timedelta(days=7), style='R')}!",  # type: ignore
                ephemeral=True,
            )
            return
        if self.settings.min_rarity_weekly is None or self.settings.max_rarity_weekly is None:
            await interaction.response.send_message(
                "Weekly packs are not configured. Contact support if this persists.", ephemeral=True
            )
            return

        if resource.weekly_cooldown is not None:
            await resource.remove_weekly_cooldown()
        await interaction.response.defer()
        balls = [
            x
            async for x in Ball.objects.filter(
                enabled=True,
                tradeable=True,
                rarity__range=(self.settings.min_rarity_weekly, self.settings.max_rarity_weekly),
            )
        ]
        ball = await self._get_random_countryball(balls)
        rarity = ball.rarity
        instance = await BallInstance.objects.acreate(
            player=player,
            ball=ball,
            health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
            attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
        )
        embed = discord.Embed(title=f"🎁 You got {ball.country}!", color=discord.Color.gold())
        desc = f"📖 **Rarity:** {rarity}\n❤️ **Health:** {ball.health}\n⚔️ **Attack:** {ball.attack}\n"
        embed.description = desc
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text="Come back next week for another pack!")
        try:
            with ThreadPoolExecutor() as pool:
                buffer = await interaction.client.loop.run_in_executor(pool, instance.draw_card)
            file = discord.File(buffer, "card.webp")
            embed.set_image(url="attachment://card.webp")
            await interaction.followup.send(embed=embed, file=file)
        except OSError:
            await interaction.followup.send(embed=embed)
        else:
            resource.weekly_uses += 1
            await resource.set_weekly_cooldown()
            await resource.asave(update_fields=("weekly_uses",))

    @app_commands.command()
    async def shop(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Check available packs in the shop.
        """
        await interaction.response.defer(thinking=True)
        currency_settings = await CurrencySettings.aload()
        packs = [x async for x in ItemModel.objects.order_by("prize").prefetch_related("balls", "special").all()]

        if not packs:
            await interaction.followup.send(f"{settings.bot_name} doesn't have any packs to buy.")
            return

        source = ShopMenuSource(packs, self.bot, currency_settings)
        pages = Pages(source, interaction=interaction, compact=True)
        await pages.start()

    @app_commands.command()
    async def buy(self, interaction: discord.Interaction["BallsDexBot"], pack: ItemTransform):
        """
        Buy a pack.

        Parameters
        ----------
        pack: Item
            The item to buy.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        currency_settings = await CurrencySettings.aload()
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        currency_emoji = self.bot.get_emoji(currency_settings.emoji_id) if currency_settings.emoji_id else ""

        balls = [x async for x in pack.balls.all()]
        if balls:
            ball = random.choice([x.cached_ball for x in balls])
        else:
            balls = [
                x
                async for x in Ball.objects.filter(
                    enabled=True, tradeable=True, rarity__range=(pack.minimum_rarity, pack.maximum_rarity)
                )
            ]
            ball = await self._get_random_countryball(balls)
        special = pack.special or self.get_random_special()
        rarity = ball.rarity
        instance = await BallInstance.objects.acreate(
            player=player,
            ball=ball,
            special=special,
            health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
            attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
        )
        embed = discord.Embed(title=f"🎁 You got {ball.country}!", color=discord.Color.gold())
        desc = f"📖 **Rarity:** {rarity}\n❤️ **Health:** {ball.health}\n⚔️ **Attack:** {ball.attack}\n"
        if special:
            desc += f"⚡ **Special:** {special.name}\n"
        embed.description = desc
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        try:
            with ThreadPoolExecutor() as pool:
                buffer = await interaction.client.loop.run_in_executor(pool, instance.draw_card)
            file = discord.File(buffer, "card.webp")
            embed.set_image(url="attachment://card.webp")
            await interaction.followup.send(embed=embed, file=file)
        except OSError:
            await interaction.followup.send(embed=embed)
            return
        else:
            instance, _ = await MoneyInstance.objects.aget_or_create(player=player)

            if pack.prize:
                if instance.amount < pack.prize:
                    emoji = self.bot.get_emoji(pack.emoji_id) if pack.emoji_id else ""
                    await interaction.followup.send(
                        f"You don't enough {currency_emoji} {currency_settings.name} to buy "
                        f"**{emoji} {pack.name}**\n"
                        f"Your actual balance: "
                        f"**{currency_emoji} {instance.amount:,} {currency_settings.display_name(instance.amount)}**"
                    )
                    return

                instance.amount -= pack.prize
                await instance.asave(update_fields=("amount",))

    @app_commands.command()
    @app_commands.checks.cooldown(1, 86400, key=lambda i: i.user.id)
    async def coin_daily(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Claim your daily payment.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        currency_settings = await CurrencySettings.aload()
        currency_emoji = self.bot.get_emoji(currency_settings.emoji_id) if currency_settings.emoji_id else ""
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        instance, _ = await MoneyInstance.objects.aget_or_create(player=player)

        instance.amount += 1500
        await instance.asave(update_fields=("amount",))

        await interaction.followup.send(
            "You've claimed  "
            f"**{currency_emoji} 1,500 {currency_settings.display_name(1500)}**! "
            f"Now you have **{instance.amount:,}**. Come back tomorrow!"
        )

    @app_commands.command()
    async def coin_balance(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Check your actual coin balance.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        currency_settings = await CurrencySettings.aload()
        currency_emoji = self.bot.get_emoji(currency_settings.emoji_id) if currency_settings.emoji_id else ""
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        instance, _ = await MoneyInstance.objects.aget_or_create(player=player)

        await interaction.followup.send(
            f"You have **{currency_emoji} {instance.amount:,} {currency_settings.display_name(instance.amount)}**"
        )
        return

    async def _get_random_countryball(self, countryballs: list[Ball]) -> Ball:
        if not countryballs:
            raise RuntimeError("No ball to spawn")
        rarities = [x.rarity for x in countryballs]
        cb = random.choices(population=countryballs, weights=rarities, k=1)[0]
        return cb

    def get_random_special(self) -> Special | None:
        population = [
            x
            for x in specials.values()
            # handle null start/end dates with infinity times
            if (x.start_date or datetime.min.replace(tzinfo=get_default_timezone()))
            <= now()
            <= (x.end_date or datetime.max.replace(tzinfo=get_default_timezone()))
        ]

        if not population:
            return None

        common_weight: float = 1 - sum(x.rarity for x in population)

        if common_weight < 0:
            common_weight = 0

        weights = [x.rarity for x in population] + [common_weight]
        # None is added representing the common countryball
        special: Special | None = random.choices(population=population + [None], weights=weights, k=1)[0]

        return special
