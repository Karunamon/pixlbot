from aiohttp import ClientTimeout
import asyncio
from datetime import datetime
import pytz

import aiohttp
import discord
from blitzdb import Document, FileBackend
from bs4 import BeautifulSoup
from discord import ApplicationContext
from discord.commands import SlashCommandGroup
from discord.ext import commands

from util import guilds


class CrumblFlavor(Document):
    pass


class CrumblNotificationChannel(Document):
    pass


def ingredients_to_emoji(ingredients):
    emoji_map = {
        "Milk": "🥛",
        "Wheat": "🌾",
        "Egg": "🥚",
        "Soy": "🌱",
        "Tree Nuts": "🌰",
        "Peanuts": "🥜",
    }

    ingredient_list = ingredients.split(", ")
    emoji_list = [emoji_map.get(ingredient, "") for ingredient in ingredient_list]
    emoji_string = " ".join(emoji_list)

    return emoji_string


async def get_cookie_content(url) -> list[dict[str, str]]:
    async with aiohttp.ClientSession(timeout=ClientTimeout(total=60)) as session:
        async with session.get(url) as response:
            html_content = await response.text()

    soup = BeautifulSoup(html_content, "html.parser")

    names = [name.text.strip() for name in soup.select("b.text-lg.sm\:text-xl")]
    descriptions = [
        description.text.strip() for description in soup.select("p.text-sm.sm\:text-lg")
    ]
    ingredients = [
        ingredient.text.strip()
        for ingredient in soup.select(
            "div.border-t.border-solid.border-lightGray > span"
        )
    ]

    content = []
    if len(names) == len(descriptions) == len(ingredients):
        for name, description, ingredient in zip(names, descriptions, ingredients):
            cookie_flavor = {
                "name": name,
                "description": description,
                "ingredients": ingredient,
            }
            content.append(cookie_flavor)
    else:
        return [
            {
                "name": "Error",
                "description": "Something went wrong when going through the list of flavors. Please check the logs.",
                "ingredients": "",
            }
        ]

    return content


class CrumblWatch(commands.Cog):
    crumbl = SlashCommandGroup(
        name="crumbl", guild_ids=guilds, description="Crumbl Cookie Watcher"
    )

    def __init__(self, bot):
        self.bot = bot
        self.bot.logger.info("Starting CrumblWatch")
        self.backend = FileBackend("db")
        self.backend.autocommit = True
        self.url = "https://crumblcookies.com/nutrition/regular"

        # Start the background task to monitor the website content
        self.bot.loop.create_task(self.check_website_content(self.url))

    async def check_website_content(self, url):
        while True:
            # Get the current time in Mountain Time
            mountain_tz = pytz.timezone("US/Mountain")
            now = datetime.now(mountain_tz)

            # Check if there is a last result saved
            try:
                last_result = self.backend.get(CrumblFlavor, {"id": "last_result"})
            except CrumblFlavor.DoesNotExist:
                last_result = None

            # If there is no last result saved, or it's Sunday and after 6 PM
            if not last_result or (now.weekday() == 6 and now.hour >= 18):
                cookie_flavors = await get_cookie_content(url)

                # If there is no last result saved, create a new one
                if not last_result:
                    last_result = CrumblFlavor(
                        {"id": "last_result", "flavors": cookie_flavors}
                    )
                    self.backend.save(last_result)

                # If the content has changed or it's the first scrape
                if cookie_flavors != last_result["flavors"]:
                    last_result["flavors"] = cookie_flavors
                    self.backend.save(last_result)

                    await self.send_notices(cookie_flavors)

            # Wait for a certain interval before checking again
            await asyncio.sleep(3600)  # Check every hour

    async def send_notices(self, cookie_flavors):
        notification_channels = self.backend.filter(CrumblNotificationChannel, {})
        embed = discord.Embed(
            title="Crumbl Cookie Flavors",
            description="The Crumbl Cookie flavors have changed!",
            color=discord.Color.from_rgb(255, 192, 203),  # Pink color
        )
        for flavor in cookie_flavors:
            embed.add_field(
                name=flavor["name"],
                value=f"{flavor['description']}\n{flavor['ingredients']}",
            )
        for channel_doc in notification_channels:
            channel = self.bot.get_channel(channel_doc["channel_id"])
            try:
                await channel.send(embed=embed)
            except discord.NotFound:
                pass

    @crumbl.command(name="enable")
    async def enable_notifications(self, ctx: ApplicationContext):
        """Enable Crumbl flavor change notifications for the current channel"""

        channel_id = ctx.channel_id
        try:
            self.backend.get(CrumblNotificationChannel, {"channel_id": channel_id})
            await ctx.respond("Notifications are already enabled for this channel.")
        except CrumblNotificationChannel.DoesNotExist:
            notification_channel = CrumblNotificationChannel({"channel_id": channel_id})
            self.backend.save(notification_channel)
            await ctx.respond("Notifications enabled for this channel.")

    @crumbl.command(name="disable")
    async def disable_notifications(self, ctx: ApplicationContext):
        """Disable Crumbl flavor change notifications for the current channel"""

        channel_id = ctx.channel_id
        try:
            notification_channel = self.backend.get(
                CrumblNotificationChannel, {"channel_id": channel_id}
            )
            self.backend.delete(notification_channel)
            await ctx.respond("Notifications disabled for this channel.")
        except CrumblNotificationChannel.DoesNotExist:
            await ctx.respond("Notifications are not enabled for this channel.")

    @crumbl.command(name="forceupdate")
    async def force_update(self, ctx: ApplicationContext):
        """Force an immediate update and report of Crumbl Cookie flavors"""

        cookie_flavors = await get_cookie_content(self.url)
        try:
            last_result = self.backend.get(CrumblFlavor, {"id": "last_result"})
            last_result["flavors"] = cookie_flavors
        except CrumblFlavor.DoesNotExist:
            last_result = CrumblFlavor({"id": "last_result", "flavors": cookie_flavors})
        self.backend.save(last_result)

        await self.send_notices(cookie_flavors)
        await ctx.respond("Update has been sent.", ephemeral=True)


def setup(bot):
    bot.add_cog(CrumblWatch(bot))
