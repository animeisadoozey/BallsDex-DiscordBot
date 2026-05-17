import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

from ballsdex.core.models import BlacklistedID

if TYPE_CHECKING:
    import discord
    from ballsdex.core.bot import BallsDexBot

    from ballsdex.core.models import BallInstance, Player
    from ballsdex.core.battle_models import Battle

@dataclass(slots=True)
class BattleBall:
    instance: "BallInstance"
    health: int
    attack: int

    def __repr__(self):
        return f"<BattleBall instance={self.instance.description(short=True)} health={self.health} attack={self.attack}>"

    def copy(self) -> Self:
        return copy.deepcopy(self)

@dataclass(slots=True)
class BattleUser:
    user: "discord.User | discord.Member"
    player: "Player"
    proposal: list["BattleBall"] = field(default_factory=list)
    locked: bool = False
    cancelled: bool = False
    accepted: bool = False
    blacklisted: bool | None = None

    def copy(self) -> "BattleUser":
        return BattleUser(
            self.user,
            self.player,
            [x.copy() for x in self.proposal],
            self.locked,
            self.cancelled,
            self.accepted,
            self.blacklisted
        )

    @classmethod
    async def from_battle_model(
        cls, battle: "Battle", player: "Player", bot: "BallsDexBot", is_admin: bool = False
    ):
        proposal = await battle.battleobjects.filter(player=player).prefetch_related("ballinstance")
        user = await bot.fetch_user(player.discord_id)
        blacklisted = (
            await BlacklistedID.exists(discord_id=player.discord_id) if is_admin else None
        )
        return cls(
            user,
            player,
            [BattleBall(x.ballinstance, x.health, x.attack) for x in proposal],
            blacklisted=blacklisted
        )

