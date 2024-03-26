import re
from datetime import datetime, timedelta, timezone
from math import floor

import discord
from discord import ApplicationContext
from discord.commands import SlashCommandGroup
from discord.ext import commands

from util import guilds

zerotime = datetime(1984, 1, 1, 0, 0, 0, 0, tzinfo=timezone.utc)
zerof = 6011000000000


class FelysianClock(commands.Cog):
    fclock = SlashCommandGroup(
        name="fclock", guild_ids=guilds, description="Felysian time"
    )

    def __init__(self, bot):
        self.bot = bot
        self.bot.logger.info("chargin mah fatonic cannon")

    @fclock.command(
        name="now", guild_ids=guilds, description="Return current Felysian time"
    )
    async def now(self, ctx: ApplicationContext):
        await ctx.defer()
        timediff = datetime.now(timezone.utc) - zerotime
        secs = int(zerof + timediff.total_seconds())
        strsecs = str(secs)
        await ctx.respond(
            f"`{strsecs[0:4]}:{strsecs[4:7]}.{strsecs[7:10]}.{strsecs[10:13]}`"
        )

    @fclock.command(
        name="toearth",
        guild_ids=guilds,
        description="Return the Earth time from a given Felysian time",
    )
    async def toearth(
            self,
            ctx: ApplicationContext,
            date: discord.Option(str, "A Felysian time like 6012:207.604.595"),
    ):
        await ctx.defer()
        m = re.match(r"^\d{13}$|^\d{4}[:.]\d{3}.\d{3}.\d{3}$", date)
        if not m:
            await ctx.respond("Invalid date.")
            return
        givenf = int(re.sub(r"[:.]", "", m.string))
        tdf = zerof - givenf
        te = zerotime - timedelta(seconds=tdf)
        await ctx.respond(te.strftime(f"{date} is %A, %b %d %Y at %H:%M:%S"))


def setup(bot):
    bot.add_cog(FelysianClock(bot))
