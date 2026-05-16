import asyncio
import datetime
from enum import IntEnum
import logging
import random
import string
from typing import TYPE_CHECKING, Literal

import discord
from discord.utils import format_dt
from tortoise import timezone
from tortoise.exceptions import BaseORMException, DoesNotExist

from ballsdex.core.boss_models import BossBall, BossHistory, BossPlayer
from ballsdex.core.dev import text_to_file
from ballsdex.core.models import BallInstance, Special
from ballsdex.core.utils.logging import log_action
from ballsdex.settings import settings

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
        self.instance = instance
        self.damage = 0
        self.dead = False
        self.won = False

    def __repr__(self):
        return f"<BossGamePlayer boss_player={self.boss_player.player.discord_id}>"

    async def save(self) -> BossHistory:
        """
        Save the stadistics from boss game.
        """
        await self.boss_player.refresh_from_db()
        self.boss_player.damage += self.damage
        if self.dead:
            self.boss_player.deaths += 1
        if self.won:
            self.boss_player.kills += 1
        await self.boss_player.save()
        history = BossHistory(
            boss=self.boss,
            player=self.boss_player,
            damage=self.damage,
            dead=self.dead,
            won=self.won
        )
        if self.instance:
            history.ball_instance = self.instance.instance
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
        buffs: bool = True
    ):
        self.guild_id = guild_id
        self.boss = boss
        self.type = type
        self.health = health
        self.attack = attack
        self.buffs = buffs
        self.task: asyncio.Task | None = None
        self.players: dict[int, BossGamePlayer] = {}
        self.view: "JoinGameView"

    def get_boss_image(self, type: Literal["start", "attack", "defense"]) -> discord.File:
        image: str
        match type:
            case "start":
                image = self.boss.start_image
            case "attack":
                image = self.boss.attack_image
            case "defense":
                image = self.boss.defense_image
            case _:
                image = self.boss.cached_ball.wild_card

        if image is None:
            image = self.boss.cached_ball.wild_card

        def generate_random_name():
            source = string.ascii_uppercase + string.ascii_lowercase + string.ascii_letters
            return "".join(random.choices(source, k=15))

        extension = image.split(".")[-1]
        file_location = "./admin_panel/media/" + image
        file_name = f"nt_{generate_random_name()}.{extension}"

        return discord.File(file_location, file_name)

    def get_player(self, discord_id: int) -> BossGamePlayer | None:
        return self.players.get(discord_id, None)

    async def _start(self):
        channel = self.view.original_message.channel
        last_player_hit: BossGamePlayer | None = None
        last_man_standing: BossGamePlayer | None = None
        round = 1
        try:
            while True:
                action = "attack" if self.type == BossGameType.last_man_standing else random.choice(["attack", "defense"])

                end_time = datetime.datetime.now() + datetime.timedelta(seconds=10)
                if action == "attack":
                    await channel.send(
                        content=(
                            f"# Round #{round}\n"
                            f"{self.boss.cached_ball.country} is preparing to attack!\n"
                            f"-# Round will start {format_dt(end_time, "R")}"
                        ),
                        file=self.get_boss_image("attack")
                    )
                else:
                    await channel.send(
                        content=(
                            f"# Round #{round}\n"
                            f"{self.boss.cached_ball.country} is preparing to defend!\n"
                            f"-# Round will start {format_dt(end_time, "R")}"
                        ),
                        file=self.get_boss_image("defense")
                    )
                await asyncio.sleep(10)

                if action == "defense":
                    global_damage_count = 0
                    log_info = ""
                    histories: list[BossHistory] = []
                    for player in self.get_players():
                        instance = player.instance
                        if not instance:
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
                        log_info += (
                            f"{player.boss_player.name}'s {description} has attacked and "
                            f"inflicted {damage} damage.\n"
                        )

                        if self.health <= 0:
                            last_player_hit = player
                            break

                    await BossHistory.bulk_create(histories)
                    await channel.send(
                        "-# Use `/boss ongoing` to check your stats in the boss.\n"
                        f"You have attacked the boss for {global_damage_count} damage!\n"
                        f"{self.boss.cached_ball.country} has **{self.health}** health.",
                        file=text_to_file(log_info, "defense.txt")
                    )

                    if self.health <= 0:
                        await asyncio.sleep(5)
                        break
                else:
                    dead_players: list[BossHistory] = []
                    global_deads = ""
                    for boss_player in self.get_players():
                        if not boss_player.instance:
                            boss_player.dead = True
                            dead_players.append(await boss_player.save())
                            global_deads += (
                                f"{boss_player.boss_player.name} has died because "
                                f"doesn't select an {settings.collectible_name} at time.\n"
                            )
                            continue

                        damage = random.randint(self.attack // 2, self.attack)
                        final_damage = min(damage, boss_player.instance.health)
                        boss_player.instance.health -= final_damage
                        if boss_player.instance.health <= 0:
                            boss_player.dead = True
                            dead_players.append(await boss_player.save())
                            global_deads += f"{boss_player.boss_player.name} has died!\n"
                            continue
                        global_deads += f"{boss_player.boss_player.name} survived, the boss inflicted {final_damage} damage.\n"

                    await BossHistory.bulk_create(dead_players)

                    dead_players_count = len(dead_players)
                    if dead_players_count > 0:
                        grammar = "person has" if dead_players_count == 1 else "people have"
                        await channel.send(
                            f"{dead_players_count} {grammar} died!\n"
                            f"{self.boss.cached_ball.country} has **{self.health}** health.",
                            file=text_to_file(global_deads, "attack.txt")
                        )
                    else:
                        await channel.send(
                            "No one died.\n"
                            f"{self.boss.cached_ball.country} has **{self.health}** health.",
                            file=text_to_file(global_deads, "attack.txt")
                        )

                    players = self.get_players()
                    if len(players) <= 0:
                        await asyncio.sleep(5)
                        break
                    elif self.type == BossGameType.last_man_standing and len(players) == 1:
                        last_man_standing = next(iter(players))
                        await asyncio.sleep(5)
                        break

                await asyncio.sleep(5)
                round += 1

            if self.type == BossGameType.last_hit:
                winner = last_player_hit
            elif self.type == BossGameType.most_damage:
                if self.players:
                    winner = max(self.get_players(), key=lambda p: p.damage)
                else:
                    winner = None
            elif self.type == BossGameType.least_damage:
                if self.players:
                    winner = min(self.get_players(), key=lambda p: p.damage)
                else:
                    winner = None
            elif self.type == BossGameType.last_man_standing:
                winner = last_man_standing
            else:
                winner = next(iter(self.get_players())) if self.players else None

            guild = self.view.original_message.guild
            assert guild
            if winner:
                await self.give_special(channel, winner)
                member = await guild.fetch_member(winner.boss_player.player.discord_id)
                embed = discord.Embed(title="Boss Defeated", color=discord.Color.orange())
                embed.description = (
                    f"The boss has been defeated by {member.display_name}! Congratulations to him/her!\n"
                    f"The boss {settings.collectible_name} has been given."
                )
                await channel.send(embed=embed)
                winner.won = True
                history = await winner.save()
                await history.save()
            else:
                embed = discord.Embed(title="Boss Won", color=discord.Color.orange())
                embed.description = "The boss exterminated all the players. Good luck for the next game."
                await channel.send(embed=embed)
        except asyncio.CancelledError:
            await channel.send("The boss game has been cancelled.")
            return
        except Exception:
            log.exception("Failed when boss game runs")
            await channel.send("Failed to continue the game, cancelling...")
            await self.stop()
            return
        finally:
            guild = self.view.original_message.guild
            assert guild
            self.view.cog.active_bosses.pop(guild.id, None)
        if self.task and not self.task.cancelled():
            self.task.cancel()

    def get_players(self) -> list[BossGamePlayer]:
        return list(filter(lambda x: not x.dead, self.players.values()))

    async def give_special(self, channel: discord.abc.Messageable, boss_player: BossGamePlayer):
        bot = self.view.cog.bot
        try:
            special = await Special.get(name="Boss")
        except DoesNotExist:
            await log_action(
                f"Failed to give the boss {settings.collectible_name} because there isn't any special "
                "named `Boss`. Please create it first.",
                bot,
            )
            return

        try:
            instance = await BallInstance.create(
                player=boss_player.boss_player.player,
                ball=self.boss.cached_ball,
                special=special,
                health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
                attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
                catch_date=timezone.now(),
            )
        except BaseORMException:
            log.exception(f"Failed to give the boss {settings.collectible_name}")
            await log_action(f"Failed to give the boss {settings.collectible_name}", bot)
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

    async def start(self):
        """
        Starts the boss game.
        """
        if self.task is not None:
            raise RuntimeError("There's already an ongoing boss game.")

        self.task = self.view.cog.bot.loop.create_task(self._start())

    async def stop(self):
        if self.task is None:
            return
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass
        guild = self.view.original_message.guild
        assert guild
        self.view.cog.active_bosses.pop(guild.id, None)