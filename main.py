# -*- coding: UTF-8 -*-
import atexit
import sys
import traceback

import discord
import yaml

from util import log
from util.cogs.responder import Responder


class KittyBot(discord.ext.commands.bot.Bot):
    config = None
    ready = False
    sentry = None
    logger = None

    def __init__(self, bot_config: dict = None):
        super().__init__(bot_config['system']['command_prefix'])
        self.config = bot_config
        self.logger = log.init_logger('bot', bot_config['system']['log_level'])
        self.logger.info("Ohai! Initializing..")

        # Sentry.io integration
        if 'sentry' in self.config.keys():
            import sentry_sdk
            self.sentry = sentry_sdk
            self.sentry.init(self.config['sentry']['init_url'], environment="production")
            self.logger.warn('sentry.io integration enabled')

        # Cogs
        self.logger.info("Loading cogs..")
        self.add_cog(Responder(self))

    async def on_error(self, event, *args, **kwargs):
        # Sentry.io integration
        exc = sys.exc_info()
        self.logger.error(f"{exc}: {event} -- {args} -- {kwargs}")
        self.logger.error(f"{traceback.extract_tb(exc[2])}")
        if self.sentry:
            with self.sentry.configure_scope() as scope:
                scope.set_tag("bot_event", event)
                scope.set_extra("event_args", args)
                scope.set_extra("event_kwargs", kwargs)
                self.sentry.capture_exception(sys.exc_info())

    async def on_connect(self):
        self.logger.info("Connected to Discord")

    async def on_ready(self):
        self.logger.info("Logged in and serving!")

    async def on_disconnect(self):
        self.logger.warn("Disconnected!")

    def shutdown(self):
        self.logger.warn("Shutting down")


with open('config.yml', 'r') as file:
    conf = yaml.safe_load(file)

bot = KittyBot(bot_config=conf)
atexit.register(bot.shutdown)
bot.run(conf['system']['bot_token'])
