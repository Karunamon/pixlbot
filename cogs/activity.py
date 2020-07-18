import datetime
from typing import Union

import discord
from blitzdb import Document, FileBackend
from discord.ext import commands


class ActivityRecord(Document):
    pass


class Activity(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backend = FileBackend('./activity-db')
        self.backend.autocommit = True
        self.scanned = False
        bot.logger.info("Activity plugin ready")

    def _maintain(self, bot):
        """Query the database and apply any configured roles"""
        pass

    def _find_one(self, member: discord.Member) -> Union[ActivityRecord, None]:
        """Searches for a response in the DB, returning it if found, or None if it doesn't exist or there are multiples.
        This exists to tie up the Blitzdb boilerplate in one place."""
        try:
            comm = self.backend.get(ActivityRecord, {'author': member.id})
        except ActivityRecord.DoesNotExist:
            return None
        except ActivityRecord.MultipleDocumentsReturned:
            self.bot.logger.error(f"Discarding multiple results returned for '{member.display_name(member.id)}'")
            return None
        else:
            return comm

    async def on_ready(self):
        if not self.scanned:
            self.scanned = True
            g = self.bot.guilds[0]  # type: discord.Guild
            self.bot.logger.info(f"Beginning server scan. {len(g.members)} to update.")
            for m in g.members:
                m: discord.Member
                if not m.bot and m.id != self.bot.id:
                    activity_record = self._find_one(m)
                    if activity_record:
                        continue
                    else:
                        a = ActivityRecord(
                            {"author": m.id, "lastspeak": datetime.datetime.now()}
                        )
                        self.backend.save(a)

    @commands.Cog.listener()
    async def on_message(self, message: discord.message):
        if not self.bot.ready():
            return
        activity_record = self._find_one(message.author)
        activity_record["lastspeak"] = message.created_at
        self.backend.save(activity_record)
        pass


def setup(bot):
    bot.add_cog(Activity(bot))
