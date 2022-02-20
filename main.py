# -*- coding: UTF-8 -*-
import atexit
import sys
import traceback
from abc import ABC

import discord
import yaml
from discord.ext.commands.bot import Bot

from util import log
from util import update_guilds


# noinspection PyDunderSlots
class PixlBot(Bot, ABC):
    config = None
    ready = False
    sentry = None
    logger = None

    # noinspection PyUnresolvedReferences
    def __init__(self, bot_config: dict = None):
        i = discord.Intents()
        i.guilds = True
        i.members = True
        i.messages = True
        super().__init__(bot_config['system']['command_prefix'], intents=i)
        self.config = bot_config
        self.logger = log.init_logger('bot', bot_config['system']['log_level'])
        self.logger.info("Ohai! Initializing..")
        self.atshutdown = []
        update_guilds(bot_config['system']['guilds'])

        # Sentry.io integration
        if 'sentry' in self.config.keys():
            import sentry_sdk
            self.sentry = sentry_sdk
            self.sentry.init(self.config['sentry']['init_url'], environment="production")
            self.logger.warning('sentry.io integration enabled')

    async def on_error(self, event, *args, **kwargs):
        exc = sys.exc_info()
        self.logger.error(f"{exc}: {event} -- {args} -- {kwargs}")
        self.logger.error(f"{traceback.extract_tb(exc[2])}")
        # Sentry.io integration
        if self.sentry:
            with self.sentry.configure_scope() as scope:
                scope.set_tag("bot_event", event)
                scope.set_extra("event_args", args)
                scope.set_extra("event_kwargs", kwargs)
                self.sentry.capture_exception(sys.exc_info())

    async def on_connect(self):
        self.logger.info("Connected to Discord")
        self.logger.info("Loading cogs..")
        for ext in self.config['system']['plugins']:
            try:
                self.logger.info(f"Attempting to load {ext}")
                self.load_extension(ext)
            except Exception as e:
                self.logger.error(e)
                continue

    async def on_ready(self):
        self.logger.info("Ready!")
        self.logger.info(self.guilds)
        await self.sync_commands()

    async def on_join_guild(self, guild):
        self.logger.info(f"Invited to a guild: {guild}")
        update_guilds(self.guilds)

    async def on_guild_remove(self, guild):
        self.logger.info(f"Removed from a guild: {guild}")
        update_guilds(self.guilds)

    # Seems to randomly trigger despite not actually being disconnected.
    # async def on_disconnect(self):
    #     self.logger.warning("Disconnected!")

    def shutdown(self):
        self.logger.warning("Shutting down")
        for f in self.atshutdown:
            self.logger.debug("Executing shutdown triggers: ")
            f()


with open('config.yml', 'r') as file:
    conf = yaml.safe_load(file)

bot = PixlBot(bot_config=conf)
atexit.register(bot.shutdown)
bot.run(conf['system']['bot_token'])
