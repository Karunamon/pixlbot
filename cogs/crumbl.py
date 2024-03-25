import asyncio
from datetime import datetime, timedelta
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


class CrumblWatch(commands.Cog):
    crumbl = SlashCommandGroup(
        name="crumbl", guild_ids=guilds, description="Crumbl Cookie Watcher"
    )

    def __init__(self, bot):
        self.bot = bot
        self.bot.logger.info("Starting CrumblWatch")
        self.backend = FileBackend("db")
        self.backend.autocommit = True

        # Specify the URL of the web page you want to scrape
        url = "https://crumblcookies.com/nutrition/regular"

        # Start the background task to monitor the website content
        self.bot.loop.create_task(self.check_website_content(url))

    async def get_b_element_content(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                html_content = await response.text()

        # Create a BeautifulSoup object to parse the HTML content
        soup = BeautifulSoup(html_content, "html.parser")

        # Find all <b> elements with the specified class
        b_elements = soup.find_all("b", class_="text-lg sm:text-xl")

        # Extract the content of each <b> element
        content = [element.get_text(strip=True) for element in b_elements]

        return content

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

            # If there is no last result saved or it's Sunday and after 6 PM
            if not last_result or (now.weekday() == 6 and now.hour >= 18):
                # Call the function to get the content of <b> elements
                b_content = await self.get_b_element_content(url)

                # If there is no last result saved, create a new one
                if not last_result:
                    last_result = CrumblFlavor(
                        {"id": "last_result", "flavors": b_content}
                    )
                    self.backend.save(last_result)

                # If the content has changed or it's the first scrape
                if b_content != last_result["flavors"]:
                    last_result["flavors"] = b_content
                    self.backend.save(last_result)

                    # Get all channels with notifications enabled
                    notification_channels = self.backend.filter(
                        CrumblNotificationChannel, {}
                    )

                    # Send the embed to each channel with notifications enabled
                    for channel_doc in notification_channels:
                        channel = self.bot.get_channel(channel_doc["channel_id"])
                        if channel:
                            embed = discord.Embed(
                                title="Crumbl Cookie Flavors",
                                description="The Crumbl Cookie flavors have changed!",
                                color=discord.Color.from_rgb(
                                    255, 192, 203
                                ),  # Pink color
                            )
                            embed.add_field(name="Flavors", value="\n".join(b_content))
                            await channel.send(embed=embed)

            # Wait for a certain interval before checking again
            await asyncio.sleep(3600)  # Check every hour

    @crumbl.command(
        name="enable",
        description="Enable Crumbl flavor change notifications for the current channel",
    )
    async def enable_notifications(self, ctx: ApplicationContext):
        channel_id = ctx.channel_id
        try:
            self.backend.get(CrumblNotificationChannel, {"channel_id": channel_id})
            await ctx.respond("Notifications are already enabled for this channel.")
        except CrumblNotificationChannel.DoesNotExist:
            notification_channel = CrumblNotificationChannel({"channel_id": channel_id})
            self.backend.save(notification_channel)
            await ctx.respond("Notifications enabled for this channel.")

    @crumbl.command(
        name="disable",
        description="Disable Crumbl flavor change notifications for the current channel",
    )
    async def disable_notifications(self, ctx: ApplicationContext):
        channel_id = ctx.channel_id
        try:
            notification_channel = self.backend.get(
                CrumblNotificationChannel, {"channel_id": channel_id}
            )
            self.backend.delete(notification_channel)
            await ctx.respond("Notifications disabled for this channel.")
        except CrumblNotificationChannel.DoesNotExist:
            await ctx.respond("Notifications are not enabled for this channel.")

    @crumbl.command(
        name="forceupdate",
        description="Force an immediate update and report of Crumbl Cookie flavors",
    )
    async def force_update(self, ctx: ApplicationContext):
        url = "https://crumblcookies.com/nutrition/regular"
        b_content = await self.get_b_element_content(url)

        # Update the last result
        try:
            last_result = self.backend.get(CrumblFlavor, {"id": "last_result"})
            last_result["flavors"] = b_content
        except CrumblFlavor.DoesNotExist:
            last_result = CrumblFlavor({"id": "last_result", "flavors": b_content})
        self.backend.save(last_result)

        # Get all channels with notifications enabled
        notification_channels = self.backend.filter(CrumblNotificationChannel, {})

        # Send the embed to each channel with notifications enabled
        for channel_doc in notification_channels:
            channel = self.bot.get_channel(channel_doc["channel_id"])
            if channel:
                embed = discord.Embed(
                    title="Crumbl Cookie Flavors (Forced Update)",
                    description="The Crumbl Cookie flavors have been forcefully updated!",
                    color=discord.Color.from_rgb(255, 192, 203),  # Pink color
                )
                embed.add_field(name="Flavors", value="\n".join(b_content))
                await channel.send(embed=embed)

        await ctx.respond(
            "Crumbl Cookie flavors have been forcefully updated and reported."
        )


def setup(bot):
    bot.add_cog(CrumblWatch(bot))
