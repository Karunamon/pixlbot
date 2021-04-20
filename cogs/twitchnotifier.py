import ssl
from typing import Optional
from typing import TYPE_CHECKING

import discord
from blitzdb import Document, FileBackend
from discord.ext import commands
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option
from twitchAPI.twitch import Twitch
from twitchAPI.twitch import TwitchBackendException
from twitchAPI.webhook import TwitchWebHook

import util
from util import mkembed

if TYPE_CHECKING:
    from main import PixlBot


class TwitchWatchedUser(Document):
    pass


twitch_name = create_option(
    name="twitch_name",
    option_type=3,
    description="Twitch channel name to watch",
    required=True
)
notify_channel = create_option(
    name="notify_channel",
    option_type=7,
    description="Channel to send notification messages to",
    required=True
)
notify_text = create_option(
    name="notify_text",
    option_type=3,
    description="Template of the notification message",
    required=True
)


class TwitchNotifier(commands.Cog):
    def __init__(self, bot):
        self.bot: 'PixlBot' = bot
        self.config = bot.config['TwitchNotifier']
        self.backend = FileBackend('db')
        self.backend.autocommit = True
        self.bot.logger.info("Twitch notifier plugin ready")
        self.uuids = []
        self.online_uuids = []
        self.sslcontext = ssl.SSLContext()
        self.sslcontext.load_cert_chain(self.config['cert_path'], self.config['key_path'])
        self._twitch_init_()

    def _twitch_init_(self):
        self.bot.logger.info("Registering with Twitch...")
        self.twitch = Twitch(self.config['id'], self.config['secret'])
        self.twitch.authenticate_app([])
        self.bot.logger.info(f"Registering webhook endpoint {self.config['myurl']} ...")
        self.hook = TwitchWebHook(self.config['myurl'], self.config['id'],
                                  self.config['port'], ssl_context=self.sslcontext)
        self.hook.authenticate(self.twitch)
        self.bot.logger.info("Clearing all hook subscriptions...")
        self.hook.unsubscribe_all(self.twitch)  # Clear all subs on startup
        self.hook.start()
        self._register_all()

    def _login_to_id(self, name: str) -> Optional[str]:
        """Returns the twitch ID for a given login name, or None if the name couldn't be resolved."""
        try:
            res: dict = self.twitch.get_users(logins=[name])
        except TwitchBackendException as e:
            self.bot.logger.error(f"Backend error fetching user! {e}")
            return None
        if len(res) == 0:
            return None
        else:
            return res['data'][0]['id']

    def _register_all(self):
        """Attempts to register stream_changed callbacks for all configured users."""
        self.bot.logger.info("Registering callbacks for all watched users..")
        users = self.backend.filter(TwitchWatchedUser, {'twitch_name': {"$exists": True}})
        if not users:
            self.bot.logger.info("No users to watch. No callbacks registered.")
        else:
            for u in users:
                self.bot.logger.info(f"Registering: {u['twitch_name']}")
                success, uuid = self.hook.subscribe_stream_changed(u['twitch_id'], self._cb_stream_changed)
                if success and uuid:
                    self.uuids.append(uuid)
                    self.bot.logger.info(f"{success}: registered subscription UUID: {uuid}")
                else:
                    self.bot.logger.error(f"{success}: failed registering subscription: {uuid}")

    def _cb_stream_changed(self, uuid, data):
        """Callback for Twitch webhooks, fires on stream change event"""
        self.bot.logger.debug(f"Callback data for {uuid}: {data}")
        if data["type"] == "offline":
            if uuid in self.online_uuids:
                self.online_uuids.remove(uuid)  # Stupid twitch sending the same damn webhook multiple times...
                return
            else:
                self.bot.logger.debug(f"Ignoring duplicate offline callback for {uuid}")
                return
        elif data["type"] == "live":
            if uuid in self.online_uuids:
                self.bot.logger.debug(f"Ignoring duplicate live callback for {uuid}")
                return
            else:
                self.online_uuids.append(uuid)
        else:
            self.bot.logger.error(f"Got a callback type we can't handle: {data['type']}")
            return

        if uuid not in self.uuids:
            self.bot.logger.error(f"Got a callback for a UUID we're not tracking: {uuid}, my UUIDs: {self.uuids}")
            return

        try:
            item = self.backend.get(TwitchWatchedUser, {"twitch_id": data["user_id"]})
        except TwitchWatchedUser.DoesNotExist:
            self.bot.logger.error(
                f"Got a callback for a USER we're not tracking: {data['user_id']} -> {data['user_name']}")
            return
        channel: discord.TextChannel = self.bot.get_channel(item['notify_channel'])

        width = 640
        height = 360
        url = data['thumbnail_url'].format(width=width, height=height)

        tu = self.twitch.get_users(data['user_id'])['data'][0]
        self.bot.logger.debug(tu)

        embed = discord.Embed(
            title=f"Now streaming {data['game_name']}",
            description=data['title'],
            color=discord.Color.green(),
        )
        embed.set_image(url=url)
        embed.set_thumbnail(url=tu["profile_image_url"])
        embed.set_author(name=item["twitch_name"], url=f"https://twitch.tv/{data['user_name']}")
        embed.add_field(name="Watch live at", value=f"https://twitch.tv/{data['user_name']}")
        self.bot.loop.create_task(channel.send(  # This isn't an async function, so enqueue it manually
            embed=embed
        ))
        self.bot.logger.info(f"Successfully sent online notification for {data['user_id']}")

    @cog_ext.cog_subcommand(base="Twitchwatch", name="add_notification",
                            description="Add a go live notification for Twitch",
                            options=[twitch_name, notify_channel, notify_text],
                            guild_ids=util.guilds)
    async def add_notification(self, ctx: SlashContext, twitch_name: str, notify_channel: discord.TextChannel,
                               notify_text: str):
        twitch_id = self._login_to_id(twitch_name)
        try:
            self.backend.get(TwitchWatchedUser, {'twitch_name': twitch_name})
        except TwitchWatchedUser.DoesNotExist:
            pass
        except TwitchWatchedUser.MultipleDocumentsReturned:
            self.bot.logger.error("Multiple users returned - database inconsistent???")
            return
        if not twitch_id:
            await ctx.send(embed=mkembed('error', f"Unable to get the Twitch ID for the name {twitch_name}"))
            return
        await ctx.defer()  # This bit can take a minute.
        success, uuid = self.hook.subscribe_stream_changed(twitch_id, self._cb_stream_changed)
        if success and uuid:
            self.uuids.append(uuid)
            self.bot.logger.info(f"{success}: registered subscription UUID: {uuid}")
        else:
            self.bot.logger.error(f"{success}: failed registering subscription: {uuid}")
            await ctx.send("Bluh, couldn't register the webhook with twitch :(")
            return
        item = TwitchWatchedUser(
            {'twitch_name': twitch_name, 'twitch_id': twitch_id, 'discord_name': ctx.author.id,
             'notify_channel': notify_channel.id, 'notify_text': notify_text, 'uuid': str(uuid)}
        )
        self.bot.logger.debug(f"DB object dump: {item.__dict__}")
        self.backend.save(item)
        await ctx.send(embed=mkembed("done", f"Notification added for {twitch_name}", channel=notify_channel.name))

    @cog_ext.cog_subcommand(base="Twitchwatch", name="del_notification",
                            description="Remove a go live notification for Twitch",
                            options=[twitch_name],
                            guild_ids=util.guilds)
    async def del_notification(self, ctx: SlashContext, twitch_name: str):
        try:
            item = self.backend.get(TwitchWatchedUser, {'twitch_name': twitch_name})
        except TwitchWatchedUser.DoesNotExist:
            await ctx.send(embed=mkembed("error", f"No notification exists for {twitch_name}"))
            return
        self.hook.unsubscribe(item['uuid'])
        self.bot.logger.info(f"Removing watch {item['uuid']}: {twitch_name}")
        self.backend.delete(item)
        if item['uuid'] in self.uuids:
            self.uuids.remove(item['uuid'])
        await ctx.send(embed=mkembed("done", f"Notification for {twitch_name} removed."))


def setup(bot):
    bot.add_cog(TwitchNotifier(bot))
