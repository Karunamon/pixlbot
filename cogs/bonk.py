import discord
from blitzdb import Document, FileBackend
from discord.ext import commands

import util


class BonkCount(Document):
    pass


class Bonk(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backend = FileBackend('db')
        self.backend.autocommit = True
        self.config = bot.config['Bonk']
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

    @staticmethod
    async def has_top_role(member: discord.Member, top: int = 3) -> bool:
        top_roles = sorted(member.guild.roles, key=lambda r: r.position, reverse=True)[:top]
        return any(role in member.roles for role in top_roles)

    @commands.message_command(name="Bonk this message", guild_ids=util.guilds)
    async def bonk(self, ctx: discord.ApplicationContext, message: discord.Message):
        await ctx.defer(ephemeral=True)
        if not await self.has_top_role(ctx.author):
            await ctx.respond("You must have one of the top roles in the server to use this command.",
                              ephemeral=True)
            return
        horny_channel: discord.TextChannel = self.bot.get_channel(self.config['channel'])  # nsfw-chat
        bonk_sticker: discord.Sticker = self.bot.get_sticker(self.config['sticker'])
        await message.reply(content=message.author.mention, stickers=[bonk_sticker])
        await horny_channel.send(f"{message.author.mention} (from {message.channel.mention}): {message.content}")
        e = util.mkembed('info',
                         f"**bonk**\n"
                         f"Your message was moved to {horny_channel.mention} for being excessively NSFW; "
                         "please remember to keep the non-NSFW parts of the server T-rated. This is a rule of the "
                         "server and not a joke.",
                         your_msg=message.content, from_channel=message.channel.mention, moved_by=ctx.author
                         )
        await message.author.send(embeds=[e])
        await message.delete()
        await ctx.respond('Bonk sent.')


def setup(bot):
    bot.add_cog(Bonk(bot))
