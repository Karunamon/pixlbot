from datetime import datetime
from typing import List, Optional

import dateparser
import discord
import pytz
from recurrent.event_parser import RecurringEvent
from dateutil import rrule
from blitzdb import Document, FileBackend
from discord import SlashCommandGroup, Option
from discord.ext import commands, tasks

import util
from util import mkembed


class ReminderEntry(Document):
    pass


class ReminderInteractedUser(Document):
    pass


async def _send_disclaimer(
    user: discord.Member, new: bool, ctx: discord.ApplicationContext
) -> bool:
    try:
        await user.send(
            "Hey I have to let you know since you just used reminders for the first time, reminders are a "
            "best-effort service. Do not rely on them for anything critical or life-threatening. Discord "
            "occasionally eats messages and glitches sometimes happen."
        )
        if new:
            await user.send(
                "Also, this tool assumes UTC/GMT times. If you want to set your time zone so you don't "
                "have to think about this in the future, please see the `/reminder timezone` command."
            )
    except discord.Forbidden:
        await ctx.respond(
            "Private messages from server members seem to be disabled. Please enable this setting to receive "
            "reminders. You will need to try again.",
            ephemeral=True,
        )
        return False
    return True


def _parse_convert_dates(when, now, tz):
    """
    Parses a date string, relative date, or recurrent date into localized times, formatted into epoch times

    :type when: str
    :type now: datetime
    :param when: The input date string or recurring event string.
    :param now: The current date and time (naïve) used to calculate recurrent events.
    :param tz: The time zone to apply to the dates.
    :return: A tuple representing the localized current time, reminder time, and a list of instance times as timestamps
    :rtype: tuple[int, int, list[int]]
    :raises ValueError:  if the provided time string cannot be parsed
    """
    reminder_time = dateparser.parse(when)  # Time zone naïve
    recurring_handler = RecurringEvent(now_date=now)
    instances = []

    first_time = reminder_time if reminder_time else recurring_handler.parse(when)
    if first_time is None:
        raise ValueError("Unable to convert provided date")
    if isinstance(first_time, str):
        # If it's a string, it must be a reoccurring event. Convert to a datetime.
        rr = rrule.rrulestr(first_time)
        instances = list(rr)
        first_time = rr.after(now)
        if instances:
            del instances[0]

    # Apply user time zone to current time and reminder times
    localized_now = tz.localize(now)
    localized_first_time = tz.localize(first_time)
    instances = [tz.localize(t) for t in instances]

    # Since we have zone-aware times, conversion to timestamp implicitly converts to UTC
    return (
        int(localized_now.timestamp()),
        int(localized_first_time.timestamp()),
        [int(x.timestamp()) for x in instances],
    )


class Reminder(commands.Cog):
    reminder = SlashCommandGroup(
        "reminder", "Set reminders for yourself or publicly", guild_ids=util.guilds
    )
    local_tzinfo = datetime.now().astimezone().tzinfo

    def __init__(self, bot):
        self.bot = bot
        self.backend = FileBackend("db")
        self.backend.autocommit = True
        self.check_reminders.start()
        bot.logger.info("Reminder ready")

    async def init_user(
        self, ctx: discord.ApplicationContext
    ) -> Optional[ReminderInteractedUser]:
        # noinspection PyTypeChecker
        user: discord.Member = ctx.author
        try:
            interacted = self.backend.get(ReminderInteractedUser, {"user_id": user.id})
        except ReminderInteractedUser.DoesNotExist:
            if not await _send_disclaimer(user, True, ctx):
                return None
            interacted = ReminderInteractedUser(
                {"user_id": user.id, "tz": "UTC", "disclaimed": True}
            )
            self.backend.save(interacted)
        if not interacted.disclaimed:
            if not await _send_disclaimer(user, False, ctx):
                return None
            interacted.disclaimed = True
            self.backend.save(interacted)
        return interacted

    def get_user_tz(self, uid: int):
        user = self.backend.get(ReminderInteractedUser, {"user_id": uid})
        return pytz.timezone(user.tz)

    def reschedule_reminder(self, reminder: ReminderEntry, new_time=0):
        """Reschedule the provided reminder. If any timestamp is provided, the reminder time will be set to that
        timestamp, otherwise the reminder's instances list will be popped
        """
        if not reminder.instances and not new_time:
            raise ValueError("Invalid reschedule: no recurrence and no timestamp given")
        if new_time:
            reminder.time = new_time
        else:
            reminder.time = reminder.instances.pop(0)
        self.backend.save(reminder)

    async def get_due_reminders(self) -> List[ReminderEntry]:
        """Retrieves a list of all reminders due to be delivered (has a UNIX timestamp now or in the past)"""
        now_timestamp = int(datetime.now(tz=self.local_tzinfo).timestamp())
        return self.backend.filter(ReminderEntry, {"time": {"$lte": now_timestamp}})

    async def send_reminders(self, reminders: List[ReminderEntry]):
        for reminder in reminders:
            channel = await self.bot.fetch_channel(reminder.channel_id)
            user = await self.bot.fetch_user(reminder.user_id)
            tz = self.get_user_tz(user.id)
            created = datetime.fromtimestamp(reminder.created, tz).strftime("%c %Z")
            # TODO: Toss reminders when the creator is no longer in the public channel
            try:
                if reminder.location == "private":
                    await user.send(
                        f"On {created}, you asked to be reminded: {reminder.text}"
                    )
                else:
                    await channel.send(
                        f"On {created}, {user.mention} asked to be reminded: {reminder.text}"
                    )
            except discord.DiscordException as e:
                reminder.fails += 1
                self.bot.logger.error(
                    f"Reminder delivery failed: {e}, Failure count {reminder.fails}"
                )
                if reminder.fails >= 3:
                    self.backend.delete(reminder)
                    return
                else:
                    self.reschedule_reminder(reminder, reminder.time + 600)
                    return

            if reminder.nag:
                self.reschedule_reminder(reminder, reminder.time + 60)
            elif reminder.instances:
                self.reschedule_reminder(reminder)
            else:
                self.backend.delete(reminder)

    @tasks.loop(seconds=10)
    async def check_reminders(self):
        reminders = await self.get_due_reminders()
        await self.send_reminders(reminders)

    @reminder.command(guild_ids=util.guilds)
    async def add(
        self,
        ctx: discord.ApplicationContext,
        when: Option(
            str,
            "Time (2020-01-01 15:00:00 UTC) / relative (in 5 minutes) / recurring (Every Friday at 1pm)",
            required=True,
        ),
        what: str,
        where: Option(
            str,
            "Deliver this reminder in public (this channel) or private DM",
            choices=["public", "private"],
            required=True,
        ),
    ):
        """Adds a reminder"""
        await ctx.defer(ephemeral=True)
        if not await self.init_user(ctx):
            return
        user_timezone = self.get_user_tz(ctx.author.id)
        now: datetime = datetime.now()

        try:
            now_ts, reminder_ts, instances = _parse_convert_dates(
                when, now, user_timezone
            )
        except ValueError:
            await ctx.respond(
                embed=mkembed("error", "Could not understand the time format."),
                ephemeral=True,
            )
            return

        reminder = ReminderEntry(
            {
                "time": reminder_ts,
                "created": now_ts,
                "text": what,
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "location": where,
                "nag": False,  # TODO
                "instances": instances,
                "fails": 0,
            }
        )
        friendly = datetime.fromtimestamp(reminder_ts, user_timezone).strftime("%c %Z")
        self.backend.save(reminder)
        await ctx.respond(
            embed=mkembed("done", f"Reminder set for {friendly}"),
            ephemeral=True,
        )

    @reminder.command(guild_ids=util.guilds)
    async def clear(self, ctx: discord.ApplicationContext):
        """Removes all your reminders"""
        user_id = ctx.author.id
        for reminder in self.backend.filter(ReminderEntry, {"user_id": user_id}):
            self.backend.delete(reminder)
        await ctx.respond(
            embed=mkembed("done", "All your reminders have been cleared."),
            ephemeral=True,
        )

    @reminder.command(guild_ids=util.guilds)
    async def timezone(
        self,
        ctx: discord.ApplicationContext,
        zone: Option(str, description="A time zone name like 'America/Chicago'"),
    ):
        """Set your time zone for reminder messages"""
        user = await self.init_user(ctx)
        try:
            pytz.timezone(zone)
        except pytz.UnknownTimeZoneError:
            await ctx.respond(
                embed=mkembed(
                    "error",
                    "I could not recognize that time zone",
                    footer="Use an identifier from https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
                ),
                ephemeral=True,
            )
            return
        else:
            user.tz = zone
            self.backend.save(user)
            await ctx.respond(
                embed=mkembed("done", "Time zone updated successfully", zone=zone),
                ephemeral=True,
            )

    @reminder.command(guild_ids=util.guilds)
    async def list(self, ctx: discord.ApplicationContext):
        """Lists all your active reminders"""
        user_id = ctx.author.id
        reminders = self.backend.filter(ReminderEntry, {"user_id": user_id})

        if not reminders:
            await ctx.respond("You have no reminders set.", ephemeral=True)
            return
        tz = self.get_user_tz(user_id)
        embed = discord.Embed(title=f"Your reminders ({len(reminders)} total)")

        for reminder in reminders:
            time = datetime.fromtimestamp(reminder.time, tz).strftime("%c %Z")
            text = (
                reminder.text
                if not reminder.instances
                else reminder.text + f" (Future instances: {len(reminder.instances)})"
            )
            embed.add_field(name=time, value=text, inline=False)

        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(Reminder(bot))
