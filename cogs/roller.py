import random

import discord
from discord.commands import Option, SlashCommandGroup
from discord.ext import commands

import util

dicegroup = SlashCommandGroup(name="dice", description="Random number generation")
dice_str = Option(str, name="dice_string", description="A dice string like 1d20 or 3d6+2")


class DiceRoll(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.bot.add_application_command(dicegroup)
        pass

    @dicegroup.command(name="roll", description="Roll some dice", options=[dice_str], guild_ids=util.guilds)
    async def roll(self, ctx: discord.ApplicationContext, dice_str: str):
        dicestr = ''.join(dice_str)
        total = 'Rolling ' + dicestr + ": **"
        mod = 0
        if dicestr.find('+', 0, -1) != -1:
            mod = int(dicestr.split('+')[1])
            dicestr = dicestr.split('+')[0]
        if dicestr.find('d', 0, -1) != -1:
            rolls = int(dicestr.split('d')[0])
            die = range(1, int(dicestr.split('d')[1]) + 1)
            dice = random.choices(die, k=rolls)
            total = total + str(sum(dice) + mod) + "** "
            if dice.__len__() > 1:
                total = total + str(dice)
            if mod > 0:
                total = total + " + " + str(mod)
        else:
            total = dicestr + " and also maybe specify some dice next time"
        await ctx.send(total)

    @dicegroup.command(name="coinflip", description="Flip a coin", guild_ids=util.guilds)
    async def flip(self, ctx: discord.ApplicationContext):
        r = random.randint(0, 1)
        if r:
            await ctx.send("Heads")
        else:
            await ctx.send("Tails")


def setup(bot):
    bot.add_cog(DiceRoll(bot))
