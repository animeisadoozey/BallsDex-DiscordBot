import datetime
from collections import defaultdict
from typing import TYPE_CHECKING, Optional, cast

import discord
from cachetools import TTLCache
from discord import app_commands
from discord.ext import commands
from discord.utils import MISSING
from django.db.models import Q

from ballsdex.core.utils.menus.old import Pages
from ballsdex.core.utils.sorting import FilteringChoices, SortingChoices, filter_balls, sort_balls
from ballsdex.core.utils.transformers import BallEnabledTransform, BallInstanceTransform, SpecialEnabledTransform
from bd_models.models import BallInstance, Player
from settings.models import settings

from ..models import Battle as BattleModel
from ..models import BattleBallRestriction, BattleBuff, BattleObject
from .display import BattleViewFormat
from .menu import BattleMenu, BattleViewMenu, BulkAddView
from .types import BattleBall, BattleUser

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class Battle(commands.GroupCog):
    """
    Start a battle with your friend and win!
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.battles: TTLCache[int, dict[int, list[BattleMenu]]] = TTLCache(maxsize=999999, ttl=1800)

    bulk = app_commands.Group(name="bulk", description="Bulk Commands")

    def get_battle(
        self,
        interaction: discord.Interaction["BallsDexBot"] | None = None,
        *,
        channel: discord.TextChannel | None = None,
        user: discord.User | discord.Member = MISSING,
    ) -> tuple[BattleMenu, BattleUser] | tuple[None, None]:
        """
        Find an ongoing battle for the given interaction.

        Parameters
        ----------
        interaction: discord.Interaction["BallsDexBot"]
            The current interaction, used for getting the guild, channel and author.

        Returns
        -------
        tuple[BattleMenu, BattleUser] | tuple[None, None]
            A tuple with the `BattleMenu` and `BattleUser` if found, else `None`.
        """
        guild: discord.Guild
        if interaction:
            guild = cast(discord.Guild, interaction.guild)
            channel = cast(discord.TextChannel, interaction.channel)
            user = interaction.user
        elif channel:
            guild = channel.guild
        else:
            raise TypeError("Missing interaction or channel")

        if guild.id not in self.battles:
            self.battles[guild.id] = defaultdict(list)
        if channel.id not in self.battles[guild.id]:
            return (None, None)
        to_remove: list[BattleMenu] = []
        for battle in self.battles[guild.id][channel.id]:
            if battle.current_view.is_finished() or battle.battler1.cancelled or battle.battler2.cancelled:
                # remove what was supposed to have been removed
                to_remove.append(battle)
                continue
            try:
                battler = battle._get_battler(user)
            except RuntimeError:
                continue
            else:
                break
        else:
            for battle in to_remove:
                self.battles[guild.id][channel.id].remove(battle)
            return (None, None)

        for battle in to_remove:
            self.battles[guild.id][channel.id].remove(battle)
        return (battle, battler)

    @app_commands.command()
    async def start(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User,
        duplicates: bool = True,
        amount: app_commands.Range[int, 3, 10] = 3,
        buffs: bool = True,
    ):
        """
        Starts a battle with the chosen user.

        Parameters
        ----------
        user: discord.User
            The user you want to battle with
        duplicates: bool
            Whether or not you want to allow duplicates in your battle
        amount: int
            The amount of countryballs needed for the battle. Minimum is 3, maximium is 10.
        buffs: bool
            Whether or not you want to allow buffs in your battle
        """
        if user.bot:
            await interaction.response.send_message("You cannot battle with bots.", ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message("You cannot battle with yourself.", ephemeral=True)
            return
        player1, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        player2, _ = await Player.objects.aget_or_create(discord_id=user.id)
        blocked = await player1.is_blocked(player2)
        blocked = await player1.is_blocked(player2)
        if blocked:
            await interaction.response.send_message(
                "You cannot begin a battle with a user that you have blocked.", ephemeral=True
            )
            return
        blocked2 = await player2.is_blocked(player1)
        if blocked2:
            await interaction.response.send_message(
                "You cannot begin a battle with a user that has blocked you.", ephemeral=True
            )
            return

        battle1, battler1 = self.get_battle(interaction)
        battle2, battler2 = self.get_battle(interaction, channel=interaction.channel)  # type: ignore
        if battle1 or battler1:
            await interaction.response.send_message("You already have an ongoing battle.", ephemeral=True)
            return
        if battle2 or battler2:
            await interaction.response.send_message(
                "The user you are trying to battle with is already in a battle.", ephemeral=True
            )
            return

        if player2.discord_id in self.bot.blacklist:
            await interaction.response.send_message("You cannot battle with a blacklisted user.", ephemeral=True)
            return

        model = await BattleModel.objects.acreate(player1=player1, player2=player2)
        menu = BattleMenu(
            self,
            interaction,
            BattleUser(interaction.user, player1),
            BattleUser(user, player2),
            duplicates,
            amount,
            buffs,
            model,
        )
        self.battles[interaction.guild.id][interaction.channel.id].append(menu)  # type: ignore
        await menu.start()
        await interaction.response.send_message("Battle started!", ephemeral=True)

    @app_commands.command()
    async def add(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Adds a ball to your battle proposal.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to add to your proposal
        special: Special
            Filter the results of autocompletion to a special event. Ignored afterwards.
        """
        if not countryball:
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        battle, battler = self.get_battle(interaction)
        if not battle or not battler:
            await interaction.followup.send("You do not have an ongoing battle.", ephemeral=True)
            return
        if battler.locked:
            await interaction.followup.send(
                "You have locked your proposal, it cannot be edited! "
                "You can click the cancel button to stop the battle instead.",
                ephemeral=True,
            )
            return
        if any(countryball.pk == ball.instance.pk for ball in battler.proposal):
            await interaction.followup.send(
                f"You already have this {settings.collectible_name} in your proposal.", ephemeral=True
            )
            return
        if not battle.duplicates and any(countryball.ball_id == ball.instance.ball_id for ball in battler.proposal):
            await interaction.followup.send(f"You've already added this {settings.collectible_name}", ephemeral=True)
            return

        if await BattleBallRestriction.objects.filter(ball=countryball.countryball).aexists():
            await interaction.followup.send(
                f"This {settings.collectible_name} isn't allowed in battle mode.", ephemeral=True
            )
            return

        if await countryball.is_locked():
            await interaction.followup.send(
                f"This {settings.collectible_name} is currently in an active battle, trade or donation, "
                "please try again later.",
                ephemeral=True,
            )
            return

        battleball = BattleBall(countryball, countryball.health, countryball.attack)
        if battle.buffs:
            buff = await BattleBuff.objects.filter(ball=countryball.countryball).afirst()

            if not buff:
                special = countryball.specialcard
                if special:
                    buff = await BattleBuff.objects.filter(special=special).afirst()
            if buff:
                battleball.health += buff.health
                battleball.attack += buff.attack

        await BattleObject.objects.acreate(
            battle=battle.model,
            ballinstance=countryball,
            player=battler.player,
            health=battleball.health,
            attack=battleball.attack,
        )
        await countryball.lock_for_trade()
        battler.proposal.append(battleball)
        await interaction.followup.send(f"{countryball.countryball.country} added.", ephemeral=True)

    @bulk.command(name="add")
    async def bulk_add(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallEnabledTransform | None = None,
        sort: SortingChoices | None = None,
        special: SpecialEnabledTransform | None = None,
        filter: FilteringChoices | None = None,
    ):
        """
        Bulk add countryballs to the ongoing battle, with paramaters to aid with searching.

        Parameters
        ----------
        countryball: Ball
            The countryball you would like to filter the results to
        sort: SortingChoices
            Choose how countryballs are sorted. Can be used to show duplicates.
        special: Special
            Filter the results to a special event
        filter: FilteringChoices
            Filter the results to a specific filter
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        battle, battler = self.get_battle(interaction)
        if not battle or not battler:
            await interaction.followup.send("You do not have an ongoing battle.", ephemeral=True)
            return
        if battler.locked:
            await interaction.followup.send(
                "You have locked your proposal, it cannot be edited! "
                "You can click the cancel button to stop the battle instead.",
                ephemeral=True,
            )
            return
        restricted_ball_ids = [x async for x in BattleBallRestriction.objects.values_list("ball_id", flat=True)]
        query = BallInstance.objects.filter(player__discord_id=interaction.user.id).exclude(
            tradeable=False, ball__tradeable=False, ball_id__in=restricted_ball_ids
        )
        if countryball:
            if await BattleBallRestriction.objects.filter(ball=countryball).aexists():
                await interaction.followup.send(
                    f"This {settings.collectible_name} isn't allowed in battle mode.", ephemeral=True
                )
                return
            query = query.filter(ball=countryball)
        if special:
            query = query.filter(special=special)
        if sort:
            query = sort_balls(sort, query)
        if filter:
            query = filter_balls(filter, query, interaction.guild_id)
        balls = cast(list[int], await query.values_list("id", flat=True))
        if not balls:
            await interaction.followup.send(f"No {settings.plural_collectible_name} found.", ephemeral=True)
            return

        view = BulkAddView(interaction, balls, self)
        await view.start(
            content=f"Select the {settings.plural_collectible_name} you want to add "
            "to your proposal, note that the display will wipe on pagination however "
            f"the selected {settings.plural_collectible_name} will remain."
        )

    @app_commands.command()
    async def remove(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Remove a countryball from what you proposed in the ongoing battle.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to remove from your proposal
        special: Special
            Filter the results of autocompletion to a special event. Ignored afterwards.
        """
        if not countryball:
            return

        battle, battler = self.get_battle(interaction)
        if not battle or not battler:
            await interaction.followup.send("You do not have an ongoing battle.", ephemeral=True)
            return
        if battler.locked:
            await interaction.followup.send(
                "You have locked your proposal, it cannot be edited! "
                "You can click the cancel button to stop the battle instead.",
                ephemeral=True,
            )
            return
        ball = next((ball for ball in battler.proposal if ball.instance.pk == countryball.pk), None)
        if not ball:
            await interaction.response.send_message(
                f"That {settings.collectible_name} is not in your proposal.", ephemeral=True
            )
            return
        battler.proposal.remove(ball)
        await interaction.response.send_message(f"{countryball.countryball.country} removed.", ephemeral=True)
        await countryball.unlock()

    @app_commands.command()
    async def cancel(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Cancel the ongoing battle.
        """
        battle, battler = self.get_battle(interaction)
        if not battle or not battler:
            await interaction.followup.send("You do not have an ongoing battle.", ephemeral=True)
            return

        if battle.battler1.accepted and battle.battler2.accepted:
            await interaction.followup.send("You can't cancel now; the battle has already gone through.")

        await battle.user_cancel(battler)
        await interaction.response.send_message("Battle cancelled.", ephemeral=True)

    @app_commands.command()
    async def view(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        View the countryballs added to an ongoing battle.
        """
        battle, battler = self.get_battle(interaction)
        if not battle or not battler:
            await interaction.followup.send("You do not have an ongoing battle.", ephemeral=True)
            return

        source = BattleViewMenu(interaction, [battle.battler1, battle.battler2], self)
        await source.start(content="Select a user to view their proposal.")

    @app_commands.command()
    @app_commands.choices(
        sorting=[
            app_commands.Choice(name="Most Recent", value="-date"),
            app_commands.Choice(name="Oldest", value="date"),
        ]
    )
    async def history(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        sorting: app_commands.Choice[str] | None = None,
        trade_user: discord.User | None = None,
        days: Optional[int] = None,
        countryball: BallEnabledTransform | None = None,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Show the history of your battles.

        Parameters
        ----------
        sorting: str | None
            The sorting order of the battles.
        trade_user: discord.User | None
            The user you want to see your battle history with.
        days: Optional[int]
            Retrieve battle history from last x days.
        countryball: BallEnabledTransform | None
            The countryball you want to filter the battle history by.
        special: SpecialEnabledTransform | None
            The special you want to filter the battle history by.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        user = interaction.user
        sort_value = sorting.value if sorting else "-date"

        if days is not None and days < 0:
            await interaction.followup.send(
                "Invalid number of days. Please provide a non-negative value.", ephemeral=True
            )
            return

        if trade_user:
            queryset = BattleModel.objects.filter(
                (Q(player1__discord_id=user.id, player2__discord_id=trade_user.id))
                | (Q(player1__discord_id=trade_user.id, player2__discord_id=user.id)),
                finished=True,
            )
        else:
            queryset = BattleModel.objects.filter(
                Q(player1__discord_id=user.id) | Q(player2__discord_id=user.id), finished=True
            )

        if days is not None and days > 0:
            end_date = datetime.datetime.now()
            start_date = end_date - datetime.timedelta(days=days)
            queryset = queryset.filter(date__range=(start_date, end_date))

        if countryball:
            queryset = queryset.filter(Q(battleobjects__ballinstance__ball=countryball)).distinct()
        if special:
            queryset = queryset.filter(Q(battleobjects__ballinstance__special=special)).distinct()

        history = [
            x
            async for x in queryset.prefetch_related(
                "player1", "player2", "battleobjects__ballinstance__ball", "battleobjects__ballinstance__special"
            ).order_by(sort_value)
        ]

        if not history:
            await interaction.followup.send("No history found.", ephemeral=True)
            return

        source = BattleViewFormat(history, interaction.user.name, self.bot)
        pages = Pages(source=source, interaction=interaction)
        await pages.start()
