import datetime

import discord
from blitzdb import Document, FileBackend
from discord.ext import commands

import util


class BonkCount(Document):
    pass


class Bonk(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backend = FileBackend("db")
        self.backend.autocommit = True
        self.config = bot.config["Bonk"]
        bot.logger.info("horny jail ready!")

    def _find_or_make(self, uid: int) -> BonkCount:
        """Searches for an id in the DB, returning it if found, or a new one if not
        This exists to tie up the Blitzdb boilerplate in one place."""
        try:
            user = self.backend.get(BonkCount, {"uid": uid})
        except BonkCount.DoesNotExist:
            return BonkCount({"uid": uid, "incidents": []})
        except BonkCount.MultipleDocumentsReturned as e:
            self.bot.logger.error(
                f"_find_or_make discarding multiple results returned for '{uid}'"
            )
            raise e
        else:
            return user

    def _inc_bonk(self, bonker: discord.Member, bonkee: discord.Message):
        user = self._find_or_make(bonkee.author.id)
        user["incidents"].append(
            {
                "ts": datetime.datetime.now().isoformat(),
                "bonker": bonker.name,
                "content": bonkee.content,
                "location": bonkee.channel.id,
            }
        )
        self.backend.save(user)

    @commands.message_command(name="Bonk this message", guild_ids=util.guilds)
    async def bonk(self, ctx: discord.ApplicationContext, message: discord.Message):
        await ctx.defer(ephemeral=True)
        sc = self.config.get(ctx.guild_id)
        if not sc:
            await ctx.respond("Bonk not set up for this server.")
            return
        # noinspection PyTypeChecker
        # This can only ever be a Member since we are operating on a guild channel
        if not util.has_roles(ctx.author, self.bot.config["admin_roles"]):
            await ctx.respond("Access denied")
            return
        horny_channel: discord.TextChannel = self.bot.get_channel(sc["channel"])
        bonk_sticker: discord.Sticker = self.bot.get_sticker(sc["sticker"])
        await message.reply(content=message.author.mention, stickers=[bonk_sticker])
        await horny_channel.send(
            f"{message.author.mention} (from {message.channel.mention}): {message.content}"
        )
        e = util.mkembed(
            "info",
            f"**bonk**\n"
            f"Your message was moved to {horny_channel.mention} for being excessively NSFW; "
            "please remember to keep the non-NSFW parts of the server T-rated. This is a rule of the "
            "server and not a joke.",
            your_msg=message.content,
            from_channel=message.channel.mention,
            moved_by=ctx.author,
        )
        await message.author.send(embeds=[e])
        # noinspection PyTypeChecker
        self._inc_bonk(ctx.author, message)
        await message.delete()
        await ctx.respond("Bonk sent.")


def setup(bot):
    bot.add_cog(Bonk(bot))
