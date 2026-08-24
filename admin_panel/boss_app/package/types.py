import asyncio
import datetime
import logging
import random
import string
from enum import IntEnum
from typing import TYPE_CHECKING, Literal

import discord
from discord.utils import format_dt
from django.utils import timezone

from ballsdex.core.dev import text_to_file
from bd_models.models import BallInstance, Special
from settings.models import settings

from ..models import BossBall, BossHistory, BossPlayer

if TYPE_CHECKING:
    from .components import JoinGameView

log = logging.getLogger(__name__)


class BossGameBall:
    def __init__(self, instance: BallInstance, health: int, attack: int):
        self.instance = instance
        self.health = health
        self.attack = attack


class BossGamePlayer:
    def __init__(self, boss: BossBall, boss_player: BossPlayer, instance: BossGameBall | None = None):
        self.boss = boss
        self.boss_player = boss_player
        self.current_instance = instance
        self.instances: list[BallInstance] = []
        self.picked = False
        self.damage = 0
        self.dead = False
        self.won = False

    def __repr__(self):
        return f"<BossGamePlayer boss_player={self.boss_player.player.discord_id}>"

    async def save(self) -> BossHistory:
        """
        Save the stadistics from boss game.
        """
        await self.boss_player.arefresh_from_db()
        self.boss_player.damage += self.damage
        if self.dead:
            self.boss_player.deaths += 1
        if self.won:
            self.boss_player.kills += 1
        await self.boss_player.asave()
        history = BossHistory(boss=self.boss, player=self.boss_player, damage=self.damage, dead=self.dead, won=self.won)
        if self.current_instance:
            history.ball_instance = self.current_instance.instance
        return history


class BossGameType(IntEnum):
    last_hit = 1
    most_damage = 2
    least_damage = 3
    last_man_standing = 4


class BossGame:
    def __init__(
        self,
        guild_id: int,
        boss: BossBall,
        type: BossGameType,
        health: int,
        attack: int,
        round_start_cooldown: int = 30,
        buffs: bool = True,
    ):
        self.guild_id = guild_id
        self.boss = boss
        self.type = type
        self.health = health
        self.attack = attack
        self.buffs = buffs
        self.round_start_cooldown = round_start_cooldown
        self.players: dict[int, BossGamePlayer] = {}
        self.view: "JoinGameView"
        self.channel = self.view.original_message.channel
        self.pick_time: bool = True
        self.active_round: bool = False
        self.round: int = 0
        self.winner: BossGamePlayer | None = None

    def get_boss_image(self, type: Literal["start", "attack", "defense"]) -> discord.File:
        image: str
        match type:
            case "start":
                image = self.boss.start_image.path
            case "attack":
                image = self.boss.attack_image.path
            case "defense":
                image = self.boss.defense_image.path
            case _:
                image = self.boss.cached_ball.wild_card.path

        if image is None:
            image = self.boss.cached_ball.wild_card.path

        def generate_random_name():
            source = string.ascii_uppercase + string.ascii_lowercase + string.ascii_letters
            return "".join(random.choices(source, k=15))

        extension = image.split(".")[-1]
        file_name = f"nt_{generate_random_name()}.{extension}"

        return discord.File(image, file_name)

    def get_player(self, discord_id: int) -> BossGamePlayer | None:
        return self.players.get(discord_id, None)

    async def start_round(self) -> bool:
        if self.health <= 0 or self.active_round:
            return True

        self.active_round = True
        self.round += 1
        action = "attack" if self.type == BossGameType.last_man_standing else random.choice(["attack", "defense"])

        end_time = datetime.datetime.now() + datetime.timedelta(seconds=self.round_start_cooldown)
        if action == "attack":
            await self.channel.send(
                content=(
                    f"# Round #{self.round}\n"
                    f"{self.boss.cached_ball.country} is preparing to attack!\n"
                    f"Renember, you need to select a new {settings.collectible_name} "
                    "every round or you'll be eliminated (To select one, use `/boss select`)\n"
                    f"-# Round will start {format_dt(end_time, 'R')}"
                ),
                file=self.get_boss_image("attack"),
            )
        else:
            await self.channel.send(
                content=(
                    f"# Round #{self.round}\n"
                    f"{self.boss.cached_ball.country} is preparing to defend!\n"
                    f"Renember, you need to select a new {settings.collectible_name} "
                    "every round or you'll be eliminated (To select one, use `/boss select`)\n"
                    f"-# Round will start {format_dt(end_time, 'R')}"
                ),
                file=self.get_boss_image("defense"),
            )

        await asyncio.sleep(self.round_start_cooldown)
        self.pick_time = False

        if action == "defense":
            global_damage_count = 0
            log_info = ""
            histories: list[BossHistory] = []
            for player in self.get_players():
                instance = player.current_instance
                if not instance or not player.picked:
                    player.dead = True
                    histories.append(await player.save())
                    log_info += (
                        f"{player.boss_player.name} has died because "
                        f"doesn't select an {settings.collectible_name} at time.\n"
                    )
                    continue

                damage = min(self.health, random.randint(instance.attack // 2, instance.attack))
                self.health -= damage
                player.damage += damage
                global_damage_count += damage

                description = instance.instance.description(short=True)
                log_info += f"{player.boss_player.name}'s {description} has attacked and inflicted {damage} damage.\n"

                if self.health <= 0:
                    if self.type == BossGameType.last_hit:
                        self.winner = player
                    elif self.type == BossGameType.most_damage:
                        self.winner = max(self.get_players(), key=lambda p: p.damage)
                    elif self.type == BossGameType.least_damage:
                        self.winner = min(self.get_players(), key=lambda p: p.damage)
                    return True

            await BossHistory.objects.abulk_create(histories)
            await self.channel.send(
                "-# Use `/boss ongoing` to check your stats in the boss.\n"
                f"You have attacked the boss for {global_damage_count} damage!\n"
                f"{self.boss.cached_ball.country} has **{self.health}** health.",
                file=text_to_file(log_info, "defense.txt"),
            )
        else:
            dead_players: list[BossHistory] = []
            global_deads = ""
            for boss_player in self.get_players():
                instance = boss_player.current_instance
                if not instance or not boss_player.picked:
                    boss_player.dead = True
                    dead_players.append(await boss_player.save())
                    global_deads += (
                        f"{boss_player.boss_player.name} has died because "
                        f"doesn't select an {settings.collectible_name} at time.\n"
                    )
                    continue

                damage = random.randint(self.attack // 2, self.attack)
                final_damage = min(damage, instance.health)
                if instance.health <= damage:
                    boss_player.dead = True
                    dead_players.append(await boss_player.save())
                    global_deads += f"{boss_player.boss_player.name} has died!\n"
                    continue
                global_deads += f"{boss_player.boss_player.name} survived, the boss inflicted {final_damage} damage.\n"

            await BossHistory.objects.abulk_create(dead_players)

            dead_players_count = len(dead_players)
            if dead_players_count > 0:
                grammar = "person has" if dead_players_count == 1 else "people have"
                await self.channel.send(
                    f"{dead_players_count} {grammar} died!\n"
                    f"{self.boss.cached_ball.country} has **{self.health}** health.",
                    file=text_to_file(global_deads, "attack.txt"),
                )
            else:
                await self.channel.send(
                    f"No one died.\n{self.boss.cached_ball.country} has **{self.health}** health.",
                    file=text_to_file(global_deads, "attack.txt"),
                )

        players = self.get_players()
        if len(players) <= 0:
            return True

        if self.type == BossGameType.last_man_standing and len(players) == 1:
            self.winner = next(iter(players))
            return True

        for player in self.players.values():
            player.picked = False
        self.pick_time = True
        return False

    def get_players(self) -> list[BossGamePlayer]:
        return list(filter(lambda x: not x.dead, self.players.values()))

    async def give_special(self, channel: discord.abc.Messageable, boss_player: BossGamePlayer):
        bot = self.view.cog.bot
        try:
            special = await Special.objects.aget(name="Boss")
        except Special.DoesNotExist:
            log.warning(
                f"Failed to give the boss {settings.collectible_name} because there isn't any special "
                "named `Boss`. Please create it first.",
                extra={"webhook": True},
            )
            return

        try:
            instance = await BallInstance.objects.acreate(
                player=boss_player.boss_player.player,
                ball=self.boss.cached_ball,
                special=special,
                health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
                attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
                catch_date=timezone.now(),
            )
        except Exception:
            log.exception(f"Failed to give the boss {settings.collectible_name}", extra={"webhook": True})
            return
        else:
            user = await bot.fetch_user(boss_player.boss_player.player.discord_id)
            try:
                await user.send(
                    "Congratulations! You have won the boss game! "
                    f"The boss {settings.collectible_name} has been added to your inventory now.\n"
                    f"{instance.description(include_emoji=True, bot=bot)}"
                )
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                await channel.send(
                    f"The boss {settings.collectible_name} was successfully given but I couldn't notify "
                    f"to {user.mention}"
                )
                return
