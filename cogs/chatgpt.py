import io
from contextlib import contextmanager
from typing import List, Optional, Dict

import discord
import openai
import yaml
from openai import ChatCompletion
from discord.commands import SlashCommandGroup, Option
from discord.ext import commands
from blitzdb import Document, FileBackend

import util
from util.chatgpt import GPTUser, UserConfig, ConversationLine, Model, DEFAULT_FLAGS
from util.souls import Soul, REMEMBRANCE_PROMPT


class PersistentUser(Document):
    class Meta(Document.Meta):
        primary_key = "uid"


class ChatGPT(commands.Cog):
    gpt = SlashCommandGroup("ai", "AI chatbot", guild_ids=util.guilds)

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config["ChatGPT"]
        self.users: Dict[int, GPTUser] = {}
        self.backend = FileBackend("db")
        self.backend.autocommit = True
        openai.api_key = self.config["api_key"]
        bot.logger.info("ChatGPT integration initialized")

    @contextmanager
    def get_persistent_userdata(self, userid: int) -> PersistentUser:
        """Searches for a user's persistent data in the DB by id, returning it if found, or a new minimal set if not."""
        try:
            pu = self.backend.get(PersistentUser, {"uid": userid})
        except PersistentUser.DoesNotExist:
            pu = PersistentUser({"uid": userid, "config": DEFAULT_FLAGS.value})
        yield pu
        self.backend.save(pu)

    async def send_to_chatgpt(self, user, conversation=None) -> Optional[str]:
        """Sends a conversation to OpenAI for chat completion and returns what the model said in reply. The model
        details will be read from the provided GPTUser. If a conversation is provided, it will be sent to the model.
        Otherwise, the conversation will be read from the user object.
        :param conversation: A specific conversation to be replied to, rather than the user's conversation
        :type conversation: List[ConversationLine] or None
        :param GPTUser user: The user object associated with this conversation
        :return: The response from the model, or none if there was a problem
        """
        try:
            response = await ChatCompletion.acreate(
                model=user.model.model,
                max_tokens=user.model.max_tokens,
                temperature=user.model.temperature,
                messages=conversation or user.conversation,
                n=1,
                stop=None,
                user=user.idhash,
            )
            return response.choices[0]["message"]["content"]
        except Exception as e:
            self.bot.logger.error(e)
            return None

    def remove_bot_mention(self, content: str) -> str:
        mention = self.bot.user.mention
        return content.replace(mention, "").strip()

    def get_user_from_context(self, context, force_new=False, **kwargs) -> GPTUser:
        """Returns a new or existing GPTUser based on the `author` of the provided context.
        Generally, you should be using this rather than reaching directly into `self.users`

        :param context: Something with an .author.id property that resolves to a Discord user ID
        :type context: discord.Message or discord.ApplicationContext
        :param force_new: If true, force creation of a new user object even if one already exists in `self.users`
        :param kwargs:
             sysprompt str: Overrides the system prompt for a new user.
             promptinfo str: A short description of the provided system prompt
        """
        uid = context.author.id
        if context.guild:
            server_config = self.config.get(context.guild.id, self.config["default"])
        else:
            server_config = self.config["default"]
        sysprompt = kwargs.pop("sysprompt", None)
        promptinfo = kwargs.pop("promptinfo", None)
        gu = self.users.get(uid)
        if (not gu) or force_new or sysprompt:
            with self.get_persistent_userdata(uid) as pu:
                gu = GPTUser(
                    uid=uid,
                    uname=context.author.display_name,
                    sysprompt=sysprompt or server_config["system_prompt"],
                    prompt_info=promptinfo,
                    model=Model(server_config["model_name"]),
                    config=UserConfig(pu.config),
                )
        return gu

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
        """Helper function for dereferencing and copying the content of another user's bot reply. This allows for
        reasonable replies should a user reply to a message directed at another user since conversations are usually
        isolated.
        """
        if message.reference:
            replied_to = message.reference.resolved
            if replied_to and replied_to.author == self.bot.user:
                other_user_id = replied_to.author.id
                if other_user_id in self.users:
                    other_user = self.users[other_user_id]
                    last_bot_msg = other_user.conversation[-1]
                    self.users[message.author.id].push_conversation(last_bot_msg, True)

    @staticmethod
    async def reply(message, content, em):
        """Replies to the given `Message` depending on its type, and automatically break up the replies to stay under
        Discord's maximum message length. Does a full reply and mentions the author if the message was sent in public,
        or just sends to the channel if it was a direct message or thread.
        :param discord.Message message: The message to reply to
        :param str content: Text to send as a reply
        :param em: An embed to send with the content. If `content` had to be split, it gets sent with the first message.
        :type em: discord.Embed or None
        """
        for chunk in util.split_content(content):
            if isinstance(message.channel, (discord.DMChannel, discord.Thread)):
                await message.channel.send(chunk, embed=em)
            else:
                await message.reply(chunk, embed=em)
            em = None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self.should_reply(message):
            return

        self.copy_public_reply(message)

        user_id = message.author.id
        gu = self.get_user_from_context(message)

        message.content = self.remove_bot_mention(message.content)
        if gu.is_stale:
            if gu.staleseen:
                gu = self.get_user_from_context(message, True)

        gu.push_conversation({"role": "user", "content": message.content})
        if gu.soul:
            # noinspection PyProtectedMember
            gu.push_conversation(
                {
                    "role": "system",
                    "content": REMEMBRANCE_PROMPT.format(**gu.soul._asdict()),
                }
            )
        overflow = []
        while gu.oversized:
            overflow.append(gu.pop_conversation(0))

        async with message.channel.typing():
            response = await self.send_to_chatgpt(gu)
            telembed = None
            warnings = ""
            stats = ""
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
                    if gu.config & UserConfig.TELEPATHY
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
                    if gu.config & UserConfig.TERSEWARNINGS:
                        warnings += "⏰❗ "
                    else:
                        warnings += (
                            "*This conversation is pretty old so the next time you talk to me, it will be a fresh "
                            "start. Please take this opportunity to save our conversation using the /ai save command "
                            "if you wish, or use /ai continue to keep this conversation going.*\n"
                        )
                    gu.staleseen = True
                if overflow:
                    if gu.config & UserConfig.TERSEWARNINGS:
                        warnings += "📏❗ "
                    else:
                        warnings += (
                            "*Our conversation is getting too long so I had to forget some of the earlier context. You "
                            "may wish to reset and/or save our conversation using the /ai commands if it is no "
                            "longer useful.*\n"
                        )
                    gu.conversation = overflow + gu.conversation
                if gu.config & UserConfig.SHOWSTATS:
                    stats = (
                        f"\n\n*📏{gu.conversation_len}/{gu.model.max_context}{'(❗)' if gu.oversized else ''}  "
                        f"{'👼' + gu.soul.name + '  ' if gu.soul else ''}"
                        f"🗣️{gu.model.model}  "
                        f"📝{'Default' if not gu.prompt_info else gu.prompt_info}  "
                        f"*"
                    )
            else:
                response = "Sorry, can't talk to OpenAI right now."
                gu.pop_conversation()  # GPT didn't get the last thing the user said, so forget it
            response = f"{warnings}\n{response}\n{stats}"
            self.users[user_id] = gu
            await self.reply(message, response, telembed)

    @gpt.command(guild_ids=util.guilds)
    async def reset(
        self,
        ctx,
        system_prompt: Option(
            str,
            description="The system (initial) prompt for the new conversation",
            default=None,
        ),
    ):
        """Reset your conversation history with the bot"""
        gu = self.get_user_from_context(
            ctx,
            True,
            sysprompt=system_prompt,
            promptinfo="Custom" if system_prompt else None,
        )
        user_id = ctx.author.id
        self.users[user_id] = gu
        response = "Your conversation history has been reset."
        if system_prompt:
            response += f"\nSystem prompt set to: {system_prompt}"
        await ctx.respond(response, ephemeral=True)

    @gpt.command(name="continue", guild_ids=util.guilds)
    async def continue_conversation(self, ctx):
        """Continue a stale conversation rather than resetting"""
        user_id = ctx.author.id
        if not self.users.get(user_id):
            await ctx.respond(
                "You have no active conversation to continue.", ephemeral=True
            )
            return
        self.users[user_id].freshen()
        await ctx.respond("Your conversation has been resumed.", ephemeral=True)

    @gpt.command(guild_ids=util.guilds)
    async def show_conversation(self, ctx):
        """Show your current conversation with the bot"""
        user_id = ctx.author.id
        if user_id not in self.users:
            await ctx.respond(
                "You have no conversation history to show.", ephemeral=True
            )
            return

        gu = self.get_user_from_context(ctx)
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

    @gpt.command(guild_ids=util.guilds)
    async def save_conversation(self, ctx):
        """Save your current conversation with the bot to a text file"""
        user_id = ctx.author.id
        if user_id not in self.users:
            await ctx.respond(
                "You have no conversation history to save.", ephemeral=True
            )
            return

        gu = self.get_user_from_context(ctx)
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

    @gpt.command(guild_ids=util.guilds)
    async def summarize_chat(
        self,
        ctx: discord.ApplicationContext,
        num_messages: Option(
            int, default=50, description="Number of messages to summarize"
        ),
        prompt: Option(
            str,
            description="Custom prompt to use for the summary (Actual chat is inserted after these words)",
            default=None,
        ),
    ):
        """Summarize the last n messages in the current channel"""
        gu = self.get_user_from_context(ctx)
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

        conversation: List[ConversationLine] = [
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
            # noinspection PyTypeChecker
            # This is a lint bug
            summary = await self.send_to_chatgpt(gu, conversation)
            if summary:
                await loading_message.edit(
                    content=f"Summary of the last {num_messages} messages:\n\n{summary}"
                )
            else:
                await loading_message.edit(
                    content="Sorry, can't generate a summary right now."
                )

    @gpt.command(guild_ids=util.guilds)
    async def load_core(
        self,
        ctx: discord.ApplicationContext,
        core: Option(str, autocomplete=util.souls.scan_cores, required=True),
        telepathy: Option(bool, default=True, description="Show thinking"),
    ):
        """Load a soul core (warning: resets conversation)"""
        try:
            with open(f"cores/{core.split(' ')[0]}") as file:
                core_data = yaml.safe_load(file)
            loaded_soul = Soul(**core_data)
            gu = self.get_user_from_context(ctx, True)
            gu.soul = loaded_soul
            gu.config |= UserConfig.TELEPATHY if telepathy else gu.config
            self.users[gu.id] = gu
        except Exception as e:
            await ctx.respond(f"Failed to load {core}: {repr(e)}", ephemeral=True)
            return
        await ctx.respond(f"{core} has been loaded", ephemeral=True)

    @gpt.command(guild_ids=util.guilds)
    async def help(self, ctx: discord.ApplicationContext):
        """Explain how this all works"""
        help_embed = discord.Embed(title="AI Chatbot Help", color=0x3498DB)
        help_embed.description = f"""I can use AI to hold a conversation. Just @mention me! I also accept DMs if you 
        are in a server with me.

        Conversations are specific to each person and are not stored. Additionally, openai has committed to deleting 
        conversations after 30 days and not using them to further train the AI. The bot will only see text that 
        specifically mentions it.
        
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

    # noinspection PyTypeHints
    @gpt.command(guild_ids=util.guilds)
    async def toggle_flags(
        self,
        ctx,
        flag: Option(
            str,
            description="The flag to toggle",
            choices=UserConfig.__members__.keys(),
            required=True,
        ),
    ):
        """Toggles user flags on/off"""
        gu = self.get_user_from_context(ctx)
        flag_to_toggle = UserConfig[flag]

        if gu.config & flag_to_toggle:
            gu.config &= ~flag_to_toggle  # If the flag is set, unset it
        else:
            gu.config |= flag_to_toggle  # If the flag is not set, set it

        self.users[gu.id] = gu
        with self.get_persistent_userdata(gu.id) as pu:
            pu.config = gu.config.value
        await ctx.respond(
            f"{flag} has been {'enabled' if gu.config & flag_to_toggle else 'disaled'}.",
            ephemeral=True,
        )

    @gpt.command(guild_ids=util.guilds)
    async def show_flags(self, ctx):
        """Show your AI settings"""
        gu = self.get_user_from_context(ctx)
        out = f"```md\n# AI settings for {gu.name}:\n"
        for k in UserConfig.__members__.keys():
            f = UserConfig[k]  # FOO rather than UserConfig.FOO
            out += f"{f.name}: {'enabled' if gu.config & f else 'disaled'}\n"
        out += "```"
        await ctx.respond(out, ephemeral=True)

    @gpt.command(guild_ids=util.guilds)
    async def translate(
        self,
        ctx,
        from_language: Option(str, "The language to translate from", required=True),
        to_language: Option(str, "The language to translate to", required=True),
        text: Option(str, "The text to be translated", required=True),
        keep_going: Option(
            bool,
            "Stay in translation mode after translating line (warning: resets conversation)",
            default=False,
        ),
    ):
        """Translate across languages"""
        await ctx.defer()
        prompt = (
            f"You are an expert translator, fluent in both {from_language} and {to_language}. "
            f"The user will say something in {from_language}, you should repeat it back to them, "
            f"and then repeat it again in {to_language}."
        )
        gu = self.get_user_from_context(
            ctx,
            True,
            sysprompt=prompt,
            promptinfo=f"Translator: {from_language} -> {to_language}",
        )
        gu.push_conversation({"role": "user", "content": text})
        async with ctx.channel.typing():
            response = await self.send_to_chatgpt(gu)
            if not response:
                response = "Sorry, could not communicate with OpenAI. Please try again."
                gu.pop_conversation()
            await ctx.respond(response)
            if keep_going:
                self.users[ctx.author.id] = gu


def setup(bot):
    bot.add_cog(ChatGPT(bot))
