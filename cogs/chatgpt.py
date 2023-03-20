import openai
from typing import List, Optional, Dict

import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup

import util


class ChatGPT(commands.Cog):
    gpt = SlashCommandGroup("chatgpt", "AI chatbot", guild_ids=util.guilds)

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config['ChatGPT']
        self.user_conversations: Dict[int, List[dict]] = {}
        openai.api_key = self.config['api_key']
        bot.logger.info("ChatGPT integration initialized")

    async def send_request_to_chatgpt(self, messages: List[dict]) -> Optional[str]:
        try:
            response = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not self.bot.user.mentioned_in(message):
            return
        cleaned_message = self.remove_bot_mention(message.content)
        user_id = message.author.id

        if user_id not in self.user_conversations:
            self.user_conversations[user_id] = [
                {"role": "system", "content":
                    "You are a helpful assistant named pixlbot.EXE. As a NetNavi who lives in the RGBCast Discord, "
                    "you love video games and the people who play them."}]
        self.user_conversations[user_id].append({"role": "user", "content": cleaned_message})
        async with message.channel.typing():
            response = await self.send_request_to_chatgpt(self.user_conversations[user_id])
            if response:
                self.user_conversations[user_id].append({"role": "assistant", "content": response})
            else:
                response = "Sorry, can't talk to OpenAI right now."

            await message.reply(response)

    @gpt.command(name="reset", description="Reset your conversation history with ChatGPT", guild_ids=util.guilds)
    async def reset(self, ctx):
        user_id = ctx.author.id
        if user_id in self.user_conversations:
            del self.user_conversations[user_id]
            await ctx.respond("Your conversation history has been reset.", ephemeral=True)
        else:
            await ctx.respond("You have no conversation history to reset.", ephemeral=True)


def setup(bot):
    bot.add_cog(ChatGPT(bot))