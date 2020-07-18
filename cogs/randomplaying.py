import asyncio
import random

import discord
from discord.ext import commands


class RandomNowPlaying(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config['RandomNowPlaying']
        bot.loop.create_task(self._setnowplaying())
        bot.logger.info("Random Now Playing plugin ready")

    async def _setnowplaying(self):
        await self.bot.wait_until_ready()
        while self.bot.is_ready():
            await self.bot.change_presence(activity=discord.Game(name=random.sample(self.config['items'], 1)[0]))
            interval = random.randint(self.config['intervalmin'], self.config['intervalmax'])
            self.bot.logger.debug(f"Sleeping for {interval} seconds")
            await asyncio.sleep(interval)

    async def on_ready(self):
        """Now playing status is lost on reconnect, so we force it to update."""
        await self._setnowplaying()


def setup(bot):
    bot.add_cog(RandomNowPlaying(bot))
