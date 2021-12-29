import asyncio
import re

import discord
import requests
from discord.ext import commands


class ImageGrabber(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config['ImageGrabber']
        self.bot.logger.info("ImageGrabber plugin ready")

    def archive_send(self, url: str) -> bool:
        result = requests.get('https://us-west2-rgbcast-nsfw.cloudfunctions.net/pixl-nsfwgrab',
                              params={'target': url})
        if result.ok:
            self.bot.logger.debug(f"Archived {url}")
            return True
        else:
            self.bot.logger.debug(f"Archive failed: {result.status_code} - {result.content}")
            return False

    @staticmethod
    async def add_status_react(message: discord.Message, status: bool = True):
        if status:
            await message.add_reaction('🆗')
        else:
            await message.add_reaction('🆖')

    async def handle_message(self, message: discord.Message):
        await asyncio.sleep(3)  # Wait for serverside embeds to populate
        if message.embeds:
            for e in message.embeds:
                if e.image:
                    await self.add_status_react(message, self.archive_send(e.image.url))
                elif e.url:
                    await self.add_status_react(message, self.archive_send(e.url))
        elif message.attachments:
            for a in message.attachments:
                await self.add_status_react(message, self.archive_send(a.url))
        else:
            urls = re.findall(
                r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))",
                message.content
            )
            for u in urls:
                if re.search(r'.+\.(png|gif|jpeg|jpg|bmp|mp4|m4v)$', message.content):
                    await self.add_status_react(message, self.archive_send(u))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild.id in self.config:
            if message.channel.id in self.config[message.guild.id]:
                await self.handle_message(message)


def setup(bot):
    bot.add_cog(ImageGrabber(bot))
