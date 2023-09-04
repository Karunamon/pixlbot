from datetime import datetime
from typing import List

import dateparser
import discord
from blitzdb import Document, FileBackend
from discord import SlashCommandGroup, Option
from discord.ext import commands, tasks

import util
from util import mkembed


class ReminderEntry(Document):
    pass


class ReminderInteractedUser(Document):
    pass


class Reminder(commands.Cog):
    reminder = SlashCommandGroup(
        "reminder", "Set reminders for yourself or publicly", guild_ids=util.guilds
    )

    def __init__(self, bot):
        self.bot = bot
        self.backend = FileBackend("db")
        self.backend.autocommit = True
        self.check_reminders.start()
        bot.logger.info("Reminder ready")

    async def do_disclaimer(self, ctx: discord.ApplicationContext) -> bool:
        # noinspection PyTypeChecker
        user: discord.Member = ctx.author
        interacted = self.backend.filter(ReminderInteractedUser, {"user_id": user.id})
        if not interacted:
            try:
                await user.send(
                    "Hey I have to let you know since you just set a reminder for the first time, reminders are a "
                    "best-effort service. Do not rely on it for anything critical or life-threatening. Discord "
                    "occasionally eats messages and glitches sometimes happen."
                )
            except discord.Forbidden:
                await ctx.respond(
                    "Private messages from server members seem to be disabled. Please enable this setting to receive "
                    "reminders. You will need to try setting your last reminder again.",
                    ephemeral=True,
                )
                return False
            new_user = ReminderInteractedUser({"user_id": user.id})
            self.backend.save(new_user)
            return True
        else:
            return True

    async def fetch_reminders(self) -> List[ReminderEntry]:
        """Retrieves a list of all reminders which are due to be delivered (has a UNIX timestamp in the past)"""
        now_unix = int(datetime.utcnow().timestamp())
        return self.backend.filter(ReminderEntry, {"time": {"$lte": now_unix}})

    async def send_reminders(self, reminders: List[ReminderEntry]):
        for reminder in reminders:
            channel = self.bot.get_channel(reminder["channel_id"])
            user = self.bot.get_user(reminder["user_id"])
            if reminder["location"] == "private":
                await user.send(
                    f"On {reminder['created']} UTC you asked to be reminded: {reminder['text']}"
                )
            else:
                await channel.send(
                    f"On {reminder['created']} UTC, {user.mention} asked to be reminded: {reminder['text']}"
                )
            self.backend.delete(reminder)

    @tasks.loop(seconds=10)
    async def check_reminders(self):
        reminders = await self.fetch_reminders()
        await self.send_reminders(reminders)

    @reminder.command(name="add", guild_ids=util.guilds)
    async def add(
        self,
        ctx: discord.ApplicationContext,
        time: Option(
            str,
            "When to be reminded. Absolute with time zone (2020-01-01 15:00:00 UTC) or relative (in 5 minutes)",
            required=True,
        ),
        text: str,
        location: Option(
            str,
            "Deliver this reminder in public (this channel) or private DM",
            choices=["public", "private"],
            required=True,
        ),
    ):
        """Adds a reminder"""
        reminder_time = dateparser.parse(time, settings={"TIMEZONE": "UTC"})

        if not reminder_time:
            await ctx.respond(
                embed=mkembed("error", "Could not understand the time format."),
                ephemeral=True,
            )
            return

        reminder_time_unix = int(reminder_time.timestamp())

        if not await self.do_disclaimer(ctx):
            return

        reminder = ReminderEntry(
            {
                "time": reminder_time_unix,
                "created": datetime.utcnow(),
                "text": text,
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "location": location,
                "nag": False,
            }
        )
        self.backend.save(reminder)
        await ctx.respond(
            embed=mkembed("done", f"Reminder set for {reminder_time} UTC"),
            ephemeral=True,
        )

    @reminder.command(name="clear", guild_ids=util.guilds)
    async def clear(self, ctx: discord.ApplicationContext):
        """Removes all reminders"""
        user_id = ctx.author.id
        for reminder in self.backend.filter(ReminderEntry, {"user_id": user_id}):
            self.backend.delete(reminder)
        await ctx.respond(
            embed=mkembed("done", "All your reminders have been cleared."),
            ephemeral=True,
        )


def setup(bot):
    bot.add_cog(Reminder(bot))
