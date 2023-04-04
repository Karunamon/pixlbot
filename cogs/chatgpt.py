import os
import tempfile
from typing import List, Optional, Dict
from datetime import datetime, timedelta

import discord
import openai
from openai import ChatCompletion, OpenAIError
from discord.commands import SlashCommandGroup
from discord.ext import commands

import util

MAX_LENGTH = 4097
MAX_TOKENS = 512


class GPTUser:
    id: int
    name: str
    _conversation: List[Dict[str, str]]
    last: datetime
    conchars: int
    stale: bool
    staleseen: bool

    def __init__(self, uid: int, uname: str, sysprompt: str):
        self.id = uid
        self.name = uname
        self.conchars = 0
        self.staleseen = False
        self._conversation = self._suffix_system_prompt(sysprompt)
        self.last = datetime.now()

    @property
    def conversation(self):
        return self._conversation

    @conversation.setter
    def conversation(self, value):
        self._conversation = value
        self._update_conchars()
        self.last = datetime.now()

    @property
    def stale(self):
        age = datetime.now() - self.last
        return age > timedelta(hours=6)

    @property
    def oversized(self):
        return self.conchars + MAX_TOKENS >= MAX_LENGTH

    def _update_conchars(self):
        cl = 0
        for entry in self.conversation:
            cl += len(entry["content"])
        self.conchars = cl

    def _suffix_system_prompt(self, sysprompt: str):
        prompt_suffix = (
            f"The user's name is {self.name} and it should be used wherever possible."
        )
        return [
            {
                "role": "system",
                "content": sysprompt + prompt_suffix,
            }
        ]


class ChatGPT(commands.Cog):
    gpt = SlashCommandGroup("ai", "AI chatbot", guild_ids=util.guilds)

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config["ChatGPT"]
        self.users: Dict[int, GPTUser] = {}
        openai.api_key = self.config["api_key"]
        bot.logger.info("ChatGPT integration initialized")

    async def send_to_chatgpt(self, messages: List[dict]) -> Optional[str]:
        try:
            response = await ChatCompletion.acreate(
                model=self.config["model_name"],
                messages=messages,
                max_tokens=MAX_TOKENS,
                n=1,
                stop=None,
                temperature=0.5,
            )
            return response.choices[0]["message"]["content"]
        except OpenAIError as e:
            self.bot.logger.error(e)
            return None

    def remove_bot_mention(self, message: str) -> str:
        mention = self.bot.user.mention
        return message.replace(mention, "").strip()

    def format_conversation(self, gu: GPTUser) -> str:
        formatted_conversation = ""
        bot_name = self.bot.user.display_name

        for msg in gu.conversation:
            role = msg["role"]
            content = msg["content"]

            if role == "user":
                formatted_conversation += f"{gu.name}: {content}\n"
            elif role == "assistant":
                formatted_conversation += f"{bot_name}: {content}\n"

        return formatted_conversation

    def should_reply(self, message: discord.Message) -> bool:
        if message.is_system():
            return False
        elif message.author.bot:
            return False
        elif message.mention_everyone:
            return False
        elif isinstance(message.channel, discord.DMChannel):
            return any(message.author.mutual_guilds)
        elif isinstance(message.channel, discord.Thread):
            if message.channel.me and message.channel.member_count == 2:
                return True
        elif self.bot.user.mentioned_in(message):
            return True
        else:
            return False

    @staticmethod
    async def reply(message: discord.Message, content: str):
        """Replies to the given Message depending on its type. Do a full reply and
        mention the author if the message was sent in public, or just send to the
        channel if it was a direct message or thread."""
        if isinstance(message.channel, discord.DMChannel):
            await message.channel.send(content)
        elif isinstance(message.channel, discord.Thread):
            await message.channel.send(content)
        else:
            await message.reply(content)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self.should_reply(message):
            return

        user_id = message.author.id
        gu = self.users.get(user_id) or GPTUser(
            user_id, message.author.display_name, self.config["system_prompt"]
        )

        message.content = self.remove_bot_mention(message.content)
        if gu.stale:
            if gu.staleseen:
                del self.users[user_id]
                gu = GPTUser(
                    user_id, message.author.display_name, self.config["system_prompt"]
                )

        gu.conversation.append({"role": "user", "content": message.content})

        overflow = []
        while gu.oversized:
            overflow.append(gu.conversation.pop(0))

        async with message.channel.typing():
            response = await self.send_to_chatgpt(gu.conversation)
            if response:
                gu.conversation.append({"role": "assistant", "content": response})
                if gu.stale:
                    response = (
                        "*This conversation is pretty old so the next time you talk to me, it will be a fresh "
                        "start. Please take this opportunity to save our conversation using the /ai commands "
                        "if you wish.*\n\n" + response
                    )
                    gu.staleseen = True
                if overflow:
                    response = (
                        "*Our conversation is getting too long so I had to forget some of the earlier context. You "
                        "may wish to reset and/or save our conversation using the /ai commands if it is no "
                        "longer useful.*\n\n" + response
                    )
                    gu.conversation = overflow + gu.conversation
                self.users[user_id] = gu
            else:
                response = "Sorry, can't talk to OpenAI right now."

            await self.reply(message, response)

    @gpt.command(
        name="reset",
        description="Reset your conversation history with the bot",
        guild_ids=util.guilds,
    )
    async def reset(self, ctx):
        user_id = ctx.author.id
        if user_id in self.users:
            del self.users[user_id]
            await ctx.respond(
                "Your conversation history has been reset.", ephemeral=True
            )
        else:
            await ctx.respond(
                "You have no conversation history to reset.", ephemeral=True
            )

    @gpt.command(
        name="show_conversation",
        description="Show your current conversation with the bot",
        guild_ids=util.guilds,
    )
    async def show_conversation(self, ctx):
        user_id = ctx.author.id
        if user_id not in self.users:
            await ctx.respond(
                "You have no conversation history to show.", ephemeral=True
            )
            return

        gu = self.users[user_id]
        formatted_conversation = self.format_conversation(gu)
        bot_display_name = self.bot.user.display_name

        try:
            await ctx.author.send(
                f"Here is your conversation with {bot_display_name}:\n\n{formatted_conversation}"
            )
            await ctx.respond(
                "I've sent you a private message with your conversation history.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await ctx.respond(
                "I couldn't send you a private message. Please make sure you allow direct messages from "
                "server members.",
                ephemeral=True,
            )

    @gpt.command(
        name="save_conversation",
        description="Save your current conversation with the bot to a text file",
        guild_ids=util.guilds,
    )
    async def save_conversation(self, ctx):
        user_id = ctx.author.id
        if user_id not in self.users:
            await ctx.respond(
                "You have no conversation history to save.", ephemeral=True
            )
            return

        gu = self.users[user_id]
        formatted_conversation = self.format_conversation(gu)
        bot_display_name = self.bot.user.display_name

        try:
            with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
                temp_file.write(formatted_conversation)
                temp_file_path = temp_file.name
                temp_file.close()
                discord_file = discord.File(temp_file_path, filename="conversation.txt")
                await ctx.author.send(
                    f"Here is your conversation with {bot_display_name}:",
                    file=discord_file,
                )

            os.remove(temp_file_path)
            await ctx.respond(
                "I've sent you a private message with your conversation history as a text file.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await ctx.respond(
                "I couldn't send you a private message. Please make sure you allow direct messages from "
                "server members.",
                ephemeral=True,
            )


def setup(bot):
    bot.add_cog(ChatGPT(bot))
