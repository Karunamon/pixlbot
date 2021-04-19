from typing import Union

import discord
import discord.ext.commands.context as context
from blitzdb import Document, FileBackend
from discord.ext import commands
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option

import util
from util import mkembed

respond_to = create_option(
    name="respond_to",
    option_type=3,
    description="Text to respond to",
    required=True
)
response = create_option(
    name="response",
    option_type=3,
    description="Text to reply with",
    required=True
)

restrict_user = create_option(
    name="restricted_user",
    option_type=6,
    description="The user(s) that the response applies to",
    required=False
)
restrict_channel = create_option(
    name="restricted_channel",
    option_type=7,
    description="The channel(s) that the response applies to",
    required=False
)


class ResponseCommand(Document):
    pass


class Responder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backend = FileBackend('db')
        self.backend.autocommit = True
        bot.logger.info("Responder plugin ready")

    def _find_one(self, name: str) -> Union[ResponseCommand, None]:
        """Searches for a response in the DB, returning it if found, or None if it doesn't exist or there are multiples.
        This exists to tie up the Blitzdb boilerplate in one place."""
        try:
            comm = self.backend.get(ResponseCommand, {'command': name})
        except ResponseCommand.DoesNotExist:
            return None
        except ResponseCommand.MultipleDocumentsReturned:
            self.bot.logger.error(f"_find_one discarding multiple results returned for '{name}'")
            return None
        else:
            return comm

    def _reply_allowed(self, comm: ResponseCommand, message: discord.Message) -> bool:
        """Determine whether a message can be replied to based on its attributes
        In general, if a user or channel restriction is set on a command, it can only be used when called in the
        listed channel or by the listed user.
        """
        self.bot.logger.debug(f"Restriction dump: {comm.get('restrictions')}")
        if not comm.get("restrictions"):
            # No restrictions on this command, we can respond without doing anything else.
            return True
        else:
            if comm["restrictions"].get("channels"):
                channels = comm["restrictions"]["channels"]
                if message.channel.id in channels:
                    return True
                else:
                    return False
            elif comm["restrictions"].get("users"):
                users = comm["restrictions"]["users"]
                if message.author.id in users:
                    return True
                else:
                    return False
            else:
                return True

    @cog_ext.cog_subcommand(base="Autoresponder", name="addresponse",
                            description="Adds an automatic response to certain text",
                            options=[respond_to, response], guild_ids=util.guilds)
    async def addresponse(self, ctx: SlashContext, respond_to: str, response: str):
        """Adds an automatic response to (name) as (response)
        The first word (name) is the text that will be replied to. Everything else is what it will be replied to with.
        If you want to reply to an entire phrase, enclose name in quotes."""
        if self._find_one(respond_to):
            await ctx.send(embed=mkembed('error', f"'{respond_to}' already exists."))
            return
        else:
            comm = ResponseCommand(
                {'command': respond_to, 'reply': response, 'creator_str': str(ctx.author), 'creator_id': ctx.author.id}
            )
            self.backend.save(comm)
            self.bot.logger.info(f"'{response}' was added by {ctx.author.display_name}")
            await ctx.send(embed=mkembed('done', "Autoresponse saved.", reply_to=respond_to, reply_with=response))

    @cog_ext.cog_subcommand(base="Autoresponder", name="delresponse",
                            description="Removes an automatic reponse from certain text",
                            options=[respond_to], guild_ids=util.guilds)
    async def delresponse(self, ctx: SlashContext, respond_to: str):
        """Removes an autoresponse.
        Only the initial creator of a response can remove it."""
        comm = self._find_one(respond_to)
        if not comm:
            await ctx.send(embed=mkembed('error', f"{respond_to} is not defined."))
            return
        elif not ctx.author.id == comm['creator_id']:
            await ctx.send(
                embed=mkembed('error', f"You are not the creator of {respond_to}. Ask {comm['creator_str']}"))
        else:
            self.backend.delete(comm)
            self.bot.logger.info(f"'{respond_to}' was deleted by {ctx.author.display_name}")
            await ctx.send(embed=mkembed('info', f"{respond_to} has been removed."))

    # @commands.command()
    # @cog_ext.cog_subcommand(base="Autoresponder", name="limit_user",
    #                         description="Limit a response to triggering on a certain user. Leave users blank to remove.",
    #                         options=[respond_to, restrict_user],
    #                         guild_ids=util.guilds)
    async def limitchannel(self, ctx: SlashContext, respond_to: str, **kwargs):
        comm = self._find_one(respond_to)
        if not comm:
            await ctx.send(embed=mkembed('error', f"'{respond_to}' does not exist."))
            return
        if not ctx.author.id == comm['creator_id']:
            await ctx.send(
                embed=mkembed('error', f"You are not the creator of '{respond_to}'. Ask {comm['creator_str']}"))
            return
        if len(kwargs) == 0:
            comm["restrictions"] = {}
            self.backend.save(comm)
            await ctx.send(embed=mkembed('done', f"All restrictions removed from {respond_to}"))
            return
        if kwargs['restrict_user']:
            if not comm.get("restrictions"):
                comm["restrictions"] = {}
            elif not comm["restrictions"].get("users"):
                comm["restrictions"]["users"] = []
            comm["restrictions"]["users"] = list(set(
                comm["restrictions"]["users"] + [u.id for u in restrict_user]
            ))
            self.backend.save(comm)
            display_users = [self.bot.get_user(u).display_name for u in comm["restrictions"]["users"]]
            await ctx.send(
                embed=mkembed('done', 'User restriction updated:', command=comm['command'], users=display_users)
            )
        if kwargs['restrict_channel']:
            if not comm.get("restrictions"):
                comm["restrictions"] = {}
            if not comm["restrictions"].get("channels"):
                comm["restrictions"]["channels"] = []
            comm["restrictions"]["channels"] = list(set(
                comm["restrictions"]["channels"] + [c.id for c in ctx.message.channel_mentions]
            ))
            display_channels = [self.bot.get_channel(c).name for c in comm["restrictions"]["channels"]]
            self.backend.save(comm)
            await ctx.send(
                embed=mkembed('done', 'Channel restriction updated:',
                              Command=comm['command'],
                              Channels=display_channels
                              )
            )

    @commands.command()
    async def responserestrictions(self, ctx: context, name: str):
        """Show the restriction list for a given command"""
        comm = self._find_one(name)
        if not comm:
            await ctx.send(embed=mkembed('error', f"{name} does not exist."))
            return
        await ctx.send(
            embed=mkembed('info', f"Information for `{name}`",
                          Reply=comm['reply'],
                          Restrictions=comm.get('restrictions', 'None'),
                          Creator=comm['creator_str']
                          )
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.message):
        comm = self._find_one(message.content)
        if comm and self._reply_allowed(comm, message):
            await message.channel.send(comm['reply'])


def setup(bot):
    bot.add_cog(Responder(bot))
