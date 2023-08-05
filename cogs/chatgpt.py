import io
from typing import List, Optional, Dict
from datetime import datetime

import discord
import openai
import yaml
from openai import ChatCompletion
from discord.commands import SlashCommandGroup, Option
from discord.ext import commands

import util
from util.chatgpt import GPTUser, MAX_TOKENS
from util.souls import Soul, REMEMBRANCE_PROMPT

MAX_MESSAGE_LENGTH = 2000


class ChatGPT(commands.Cog):
    gpt = SlashCommandGroup("ai", "AI chatbot", guild_ids=util.guilds)

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config["ChatGPT"]
        self.users: Dict[int, GPTUser] = {}
        openai.api_key = self.config["api_key"]
        bot.logger.info("ChatGPT integration initialized")

    async def send_to_chatgpt(self, messages: List[dict], user: str) -> Optional[str]:
        try:
            response = await ChatCompletion.acreate(
                model=self.config["model_name"],
                messages=messages,
                max_tokens=MAX_TOKENS,
                n=1,
                stop=None,
                temperature=0.5,
                user=user,
            )
            return response.choices[0]["message"]["content"]
        except Exception as e:
            self.bot.logger.error(e)
            return None

    def remove_bot_mention(self, content: str) -> str:
        mention = self.bot.user.mention
        return content.replace(mention, "").strip()

    def should_reply(self, message: discord.Message) -> bool:
        """Determine whether the given message should be replied to. TL;DR: DON'T reply to system messages,
        bot messages, @everyone pings, or anything in a NSFW channel. DO reply to direct messages where we
        share a guild with the sender, in threads containing only the bot and one other person, and otherwise to
        messages where we were mentioned."""
        if message.is_system():
            return False
        elif message.author.bot:
            return False
        elif message.mention_everyone:
            return False
        elif isinstance(message.channel, discord.DMChannel):
            return any(message.author.mutual_guilds)
        elif message.channel.is_nsfw():
            return False
        elif isinstance(message.channel, discord.Thread):
            if message.channel.me and message.channel.member_count == 2:
                return True
        elif self.bot.user.mentioned_in(message):
            return True
        else:
            return False

    def copy_public_reply(self, message: discord.Message):
        if message.reference:
            replied_to = message.reference.resolved
            if replied_to and replied_to.author == self.bot.user:
                other_user_id = replied_to.author.id
                if other_user_id in self.users:
                    other_user = self.users[other_user_id]
                    last_bot_msg = other_user.conversation[-1]
                    self.users[message.author.id].push_conversation(last_bot_msg, True)

    @staticmethod
    async def reply(
        message: discord.Message, content: str, em: Optional[discord.Embed]
    ):
        """Replies to the given Message depending on its type. Do a full reply and
        mention the author if the message was sent in public, or just send to the
        channel if it was a direct message or thread."""
        while len(content) > 0:
            # If message is too large, find the last newline before the limit
            if len(content) > MAX_MESSAGE_LENGTH:
                split_index = content[:MAX_MESSAGE_LENGTH].rfind("\n")
                # If no newline is found, just split at the max length
                if split_index == -1:
                    split_index = MAX_MESSAGE_LENGTH
            else:
                split_index = len(content)

            chunk = content[:split_index]
            # Remove the chunk from the original content
            content = content[split_index:].lstrip()

            # Send chunk
            if isinstance(message.channel, (discord.DMChannel, discord.Thread)):
                await message.channel.send(chunk, embed=em)
            else:
                await message.reply(chunk, embed=em)
            em = None  # Only send the embed with the first chunk

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self.should_reply(message):
            return

        self.copy_public_reply(message)

        user_id = message.author.id
        gu = self.users.get(user_id) or GPTUser(
            user_id, message.author.display_name, self.config["system_prompt"]
        )

        message.content = self.remove_bot_mention(message.content)
        if gu.is_stale:
            if gu.staleseen:
                del self.users[user_id]
                gu = GPTUser(
                    user_id, message.author.display_name, self.config["system_prompt"]
                )
        gu.push_conversation({"role": "user", "content": message.content})
        if gu.soul:
            gu.push_conversation(
                {
                    "role": "system",
                    "content": REMEMBRANCE_PROMPT.format(**dict(gu.soul)),
                }
            )
        overflow = []
        while gu.oversized:
            overflow.append(gu.pop_conversation(0))

        async with message.channel.typing():
            response = await self.send_to_chatgpt(gu.conversation, gu.namehash)
            telembed = None
            if gu.soul:
                response, telepathy = util.souls.format_from_soul(response)
                telembed = (
                    util.mkembed(
                        "info",
                        "",
                        title=f"{gu.soul.name}'s mind",
                        feeling=telepathy[0],
                        thought=telepathy[1],
                        analysis=telepathy[2],
                    )
                    if gu.telepathy
                    else None
                )

            if response:
                gu.conversation = [
                    y
                    for x, y in enumerate(gu.conversation)
                    if (y["role"] == "system" and x == 0)
                    or (y["role"] != "system" and x > 0)
                ]  # Throw out any system prompts but the first one
                gu.push_conversation({"role": "assistant", "content": response})
                if gu.is_stale:
                    response = (
                        "*This conversation is pretty old so the next time you talk to me, it will be a fresh "
                        "start. Please take this opportunity to save our conversation using the /ai save commands "
                        "if you wish, or use /ai continue to keep this conversation going.*\n\n"
                        + response
                    )
                    gu.staleseen = True
                if overflow:
                    response = (
                        "*Our conversation is getting too long so I had to forget some of the earlier context. You "
                        "may wish to reset and/or save our conversation using the /ai commands if it is no "
                        "longer useful.*\n\n" + response
                    )
                    gu.conversation = overflow + gu.conversation
            else:
                response = "Sorry, can't talk to OpenAI right now."
                gu.pop_conversation()  # GPT didn't get the last thing the user said, so forget it
                if gu.soul:
                    gu.pop_conversation()  # We have to clear the remembrance prompt as well
            self.users[user_id] = gu

            await self.reply(message, response, telembed)

    @gpt.command(
        name="reset",
        description="Reset your conversation history with the bot",
        guild_ids=util.guilds,
    )
    async def reset(
        self,
        ctx,
        system_prompt: str = Option(
            description="The system (initial) prompt for the new conversation",
            default=None,
        ),
    ):
        user_id = ctx.author.id
        self.users[user_id] = GPTUser(
            user_id,
            ctx.author.display_name,
            f"{system_prompt}" if system_prompt else self.config["system_prompt"],
        )
        await ctx.respond("Your conversation history has been reset.", ephemeral=True)

    @gpt.command(
        name="continue",
        description="Continue a stale conversation rather than resetting",
        guild_ids=util.guilds,
    )
    async def continue_conversation(self, ctx):
        user_id = ctx.author.id
        if user_id not in self.users:
            await ctx.respond(
                "You have no active conversation to continue.", ephemeral=True
            )
            return

        gu = self.users[user_id]
        gu.staleseen = False
        gu.last = datetime.utcnow()
        self.users[user_id] = gu

        await ctx.respond("Your conversation has been resumed.", ephemeral=True)

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
        bot_display_name = self.bot.user.display_name
        formatted_conversation = gu.format_conversation(bot_display_name)

        try:
            msg = await ctx.author.send(
                f"Here is your conversation with {bot_display_name}:"
            )
            await self.reply(msg, formatted_conversation, None)
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
        bot_display_name = self.bot.user.display_name
        formatted_conversation = gu.format_conversation(bot_display_name)

        try:
            with io.BytesIO() as temp_file:
                temp_file.write(formatted_conversation.encode())
                temp_file.seek(0)
                discord_file = discord.File(temp_file, filename="conversation.txt")
                await ctx.author.send(
                    f"Here is your conversation with {bot_display_name}:",
                    file=discord_file,
                )

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

    @gpt.command(
        name="summarize_chat",
        description="Summarize the last n messages in the current channel",
        guild_ids=util.guilds,
    )
    async def summarize_chat(
        self,
        ctx: discord.ApplicationContext,
        num_messages: int = Option(
            default=50, description="Number of messages to summarize"
        ),
        prompt: str = Option(
            description="Custom prompt to use for the summary (Actual chat is inserted after these words)",
            default=None,
        ),
    ):
        if ctx.channel.is_nsfw():
            await ctx.respond(
                "Sorry, can't operate in NSFW channels (OpenAI TOS)", ephemeral=True
            )
            return
        if num_messages <= 0:
            await ctx.respond(
                "Number of messages to summarize must be greater than 0.",
                ephemeral=True,
            )
            return

        channel = ctx.channel
        messages = await channel.history(limit=num_messages).flatten()
        messages.reverse()  # Reverse the messages to get them in chronological order.

        text = "\n".join(
            [f"{message.author.name}: {message.content}" for message in messages]
        )
        sysprompt = (
            f"{prompt}\n{text}"
            if prompt
            else (
                f"The following is a conversation between various people in a Discord chat. It is formatted such "
                f"that each line begins with the name of the speaker, a colon, and then whatever the speaker "
                f"said. Please provide a summary of the conversation beginning below: \n{text}\n"
            )
        )

        conversation = [
            {
                "role": "system",
                "content": sysprompt,
            }
        ]
        async with ctx.channel.typing():
            await ctx.respond("Working on the summary now", ephemeral=True)
            loading_message = await ctx.send(
                f"Now generating summary of the last {num_messages} messages…"
            )
            summary = await self.send_to_chatgpt(conversation, "0")
            if summary:
                await loading_message.edit(
                    content=f"Summary of the last {num_messages} messages:\n\n{summary}"
                )
            else:
                await loading_message.edit(
                    content="Sorry, can't generate a summary right now."
                )

    @gpt.command(
        name="load_core",
        description="Load a soul core (warning: resets conversation)",
        guild_ids=util.guilds,
    )
    async def load_core(
        self,
        ctx: discord.ApplicationContext,
        core: discord.Option(str, autocomplete=util.souls.scan_cores, required=True),
        telepathy: discord.Option(bool, default=True, description="Show thinking"),
    ):
        try:
            y = yaml.safe_load(open(f"cores/{core.split(' ')[0]}"))
            s = Soul(**y)
            # noinspection PyTypeChecker
            ca: discord.Member = (
                ctx.author
            )  # We know this is a Member since this is a slash command
            gu = self.users.get(ca.id) or GPTUser(ca.id, ca.nick, "")
            gu.soul = s
            gu.telepathy = telepathy
            self.users[ca.id] = gu
        except Exception as e:
            await ctx.respond(f"Failed to load {core}: {repr(e)}", ephemeral=True)
            return
        await ctx.respond(f"{core} has been loaded", ephemeral=True)

    @gpt.command(name="help", description="Explain how this all works")
    async def display_help(self, ctx: discord.ApplicationContext):
        help_embed = discord.Embed(title="AI Chatbot Help", color=0x3498DB)
        help_embed.description = f"""I can use AI to hold a conversation. Just @mention me! I also accept DMs if you 
        are in a server with me.

Conversations are specific to each person and are not stored. Additionally, openai has committed to deleting 
conversations after 30 days and not using them to further train the AI. The bot will only see text that specifically 
mentions it.

Conversations timeout after six hours and will be reset after that time unless the continue command is used.

Important commands (Others are in the / pop-up, these require additional explanation):
"""
        help_embed.add_field(
            name="load_core",
            value="EXPERIMENTAL: load a soul core to have a conversation with a specific personality. Resets your "
            "current conversation. Use the reset command to return to normal.",
        )
        help_embed.add_field(
            name="continue",
            value="Once a conversation is six hours old, the bot will say the next message is a fresh start. If you "
            "want to continue your conversation rather than starting over, use this command when you see that "
            "warning.",
        )
        await ctx.respond(embed=help_embed, ephemeral=True)


def setup(bot):
    bot.add_cog(ChatGPT(bot))
