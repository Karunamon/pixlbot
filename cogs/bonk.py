import discord
from blitzdb import Document, FileBackend
from discord.ext import commands


class BonkCount(Document):
    pass


class Bonk(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backend = FileBackend('db')
        self.backend.autocommit = True
        bot.logger.info("horny jail ready!")

    def _find_or_make(self, uid: int) -> BonkCount:
        """Searches for an id in the DB, returning it if found, or a new one if not
        This exists to tie up the Blitzdb boilerplate in one place."""
        try:
            user = self.backend.get(BonkCount, {'uid': uid})
        except BonkCount.DoesNotExist:
            return BonkCount({'uid': uid})
        except BonkCount.MultipleDocumentsReturned as e:
            self.bot.logger.error(f"_find_or_make discarding multiple results returned for '{uid}'")
            raise e
        else:
            return user

    @staticmethod
    async def _getmsg(ctx: discord.ApplicationContext, msg_id: int,
                      channel: discord.TextChannel = None) -> discord.Message:
        if channel:
            return await channel.fetch_message(msg_id)
        else:
            return await ctx.channel.fetch_message(msg_id)

    @commands.message_command(name="Bonk this message", guild_ids=[709655247357739048])
    async def bonk(self, ctx: discord.ApplicationContext, message: discord.Message):
        await ctx.respond("bonk")
        horny_channel: discord.TextChannel = self.bot.get_channel(778310784450691142)  # nsfw-chat
        bonk_sticker: discord.Sticker = self.bot.get_sticker(943515690235752459)
        await message.reply(stickers=[bonk_sticker])
        await horny_channel.send(f"{message.author.mention} (from {message.channel.mention}): {message.content}")
        await message.author.send(f"Your message in {message.channel.mention} was moved to {horny_channel.mention} for "
                                  "excessive NSFW; please remember to keep the non-NSFW parts of the server T-rated.")
        await message.delete()


def setup(bot):
    bot.add_cog(Bonk(bot))
