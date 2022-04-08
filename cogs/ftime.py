import re
from datetime import datetime, timedelta
from math import floor

import discord
from discord import ApplicationContext
from discord.commands import SlashCommandGroup
from discord.ext import commands

from util import guilds

zerotime = datetime(1984, 1, 1, 0, 0, 0, 0)
zerof = 6011000000000


class FelysianClock(commands.Cog):
    fclock = SlashCommandGroup(name='fclock', guild_ids=guilds, description='Felysian time')

    def __init__(self, bot):
        self.bot = bot
        self.bot.logger.info('chargin mah fatonic cannon')

    @fclock.command(name='now', guild_ids=guilds, description="Return current Felysian time")
    async def now(self, ctx: ApplicationContext):
        await ctx.defer()
        timediff = datetime.now() - zerotime
        secs = floor(zerof + timediff.total_seconds())
        strsecs = str(secs)
        await ctx.respond(f"`{strsecs[0:4]}:{strsecs[4:7]}.{strsecs[7:10]}.{strsecs[10:13]}`")

    @fclock.command(name='toearth', guild_ids=guilds, description="Return the Earth time from a given Felysian time")
    async def toearth(self, ctx: ApplicationContext,
                      date: discord.Option(str, 'A felysian time like 6012:207.604.595')):
        await ctx.defer(ephemeral=True)
        m = re.match(r'^\d{13}$', date) or re.match(r'^\d{4}[:.]\d{3}.\d{3}.\d{3}$', date)
        if not m:
            await ctx.respond('Invalid date.')
            return
        givenf = int(m.string.replace(':', '').replace('.', ''))
        tdf = zerof - givenf
        te = zerotime - timedelta(seconds=tdf)
        await ctx.respond(te.strftime("%A %d-%b-%Y at %H:%M:%S"))


def setup(bot):
    bot.add_cog(FelysianClock(bot))
