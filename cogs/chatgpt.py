import os
import tempfile
from typing import List, Optional, Dict

import discord
import openai
from discord.commands import SlashCommandGroup
from discord.ext import commands

import util


class ChatGPT(commands.Cog):
    gpt = SlashCommandGroup("ai", "AI chatbot", guild_ids=util.guilds)

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config['ChatGPT']
        self.user_conversations: Dict[int, List[dict]] = {}
        openai.api_key = self.config['api_key']
        bot.logger.info("ChatGPT integration initialized")

    async def send_request_to_chatgpt(self, messages: List[dict]) -> Optional[str]:
        try:
            response = await openai.ChatCompletion.acreate(
                model=self.config['model_name'],
                messages=messages,
                max_tokens=1024,
                n=1,
                stop=None,
                temperature=0.5,
            )
            return response.choices[0]['message']['content']
        except Exception as e:
            self.bot.logger.error(f"An error occurred while contacting ChatGPT: {e}")
            return None

    def remove_bot_mention(self, message: str) -> str:
        mention = self.bot.user.mention
        return message.replace(mention, "").strip()

    def format_conversation(self, author_display_name: str, conversation: List[dict]) -> str:
        formatted_conversation = ""
        bot_display_name = self.bot.user.display_name

        for msg in conversation:
            role = msg["role"]
            content = msg["content"]

            if role == "user":
                formatted_conversation += f"{author_display_name}: {content}\n"
            elif role == "assistant":
                formatted_conversation += f"{bot_display_name}: {content}\n"

        return formatted_conversation

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        is_private_message = isinstance(message.channel, discord.DMChannel)

        if not is_private_message and not self.bot.user.mentioned_in(message):
            return

        cleaned_message = self.remove_bot_mention(message.content) if not is_private_message else message.content
        user_id = message.author.id
        prompt_suffix = f"The user's name is {message.author.display_name} and it should be used wherever possible."

        if user_id not in self.user_conversations:
            self.user_conversations[user_id] = [
                {"role": "system", "content": self.config['system_prompt'] + prompt_suffix}
            ]
        self.user_conversations[user_id].append({"role": "user", "content": cleaned_message})
        async with message.channel.typing():
            response = await self.send_request_to_chatgpt(self.user_conversations[user_id])
            if response:
                self.user_conversations[user_id].append({"role": "assistant", "content": response})
            else:
                response = "Sorry, can't talk to OpenAI right now."
            if is_private_message:
                await message.channel.send(response)
            else:
                await message.reply(response)

    @gpt.command(name="reset", description="Reset your conversation history with ChatGPT", guild_ids=util.guilds)
    async def reset(self, ctx):
        user_id = ctx.author.id
        if user_id in self.user_conversations:
            del self.user_conversations[user_id]
            await ctx.respond("Your conversation history has been reset.", ephemeral=True)
        else:
            await ctx.respond("You have no conversation history to reset.", ephemeral=True)

    @gpt.command(name="show_conversation", description="Show your current conversation with ChatGPT",
                 guild_ids=util.guilds)
    async def show_conversation(self, ctx):
        user_id = ctx.author.id
        if user_id not in self.user_conversations:
            await ctx.respond("You have no conversation history to show.", ephemeral=True)
            return

        conversation = self.user_conversations[user_id]
        formatted_conversation = self.format_conversation(ctx.author.display_name, conversation)
        bot_display_name = self.bot.user.display_name

        try:
            await ctx.author.send(f"Here is your conversation with {bot_display_name}:\n\n{formatted_conversation}")
            await ctx.respond("I've sent you a private message with your conversation history.", ephemeral=True)
        except discord.Forbidden:
            await ctx.respond("I couldn't send you a private message. Please make sure you allow direct messages from "
                              "server members.", ephemeral=True)

    @gpt.command(name="save_conversation", description="Save your current conversation with ChatGPT to a text file",
                 guild_ids=util.guilds)
    async def save_conversation(self, ctx):
        user_id = ctx.author.id
        if user_id not in self.user_conversations:
            await ctx.respond("You have no conversation history to save.", ephemeral=True)
            return

        conversation = self.user_conversations[user_id]
        formatted_conversation = self.format_conversation(ctx.author.display_name, conversation)
        bot_display_name = self.bot.user.display_name

        try:
            with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
                temp_file.write(formatted_conversation)
                temp_file_path = temp_file.name
                temp_file.close()
                discord_file = discord.File(temp_file_path, filename="conversation.txt")
                await ctx.author.send(f"Here is your conversation with {bot_display_name}:", file=discord_file)

            os.remove(temp_file_path)
            await ctx.respond("I've sent you a private message with your conversation history as a text file.",
                              ephemeral=True)
        except discord.Forbidden:
            await ctx.respond("I couldn't send you a private message. Please make sure you allow direct messages from "
                              "server members.", ephemeral=True)


def setup(bot):
    bot.add_cog(ChatGPT(bot))
