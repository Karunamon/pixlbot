from unittest.mock import MagicMock

import discord
from cogs import chatgpt

# Dependencies:
# pip install pytest-mock
import pytest

from cogs.chatgpt import ChatGPT
from util.chatgpt import GPTUser


class TestOnMessage:
    #  Test that the method correctly handles the case when a user sends a message that should be replied to.
    @pytest.fixture
    def bot(self):
        bot = MagicMock()
        bot.config = {"ChatGPT": {"api_key": "foo", "system_prompt": "System prompt"}}
        bot.user = MagicMock()
        bot.user.display_name = "Bot"
        return bot

    @pytest.fixture
    def cog(self, bot):
        cog = ChatGPT(bot)
        cog.users = {123: GPTUser(123, "User", "My prompt")}
        return cog

    @pytest.mark.asyncio
    async def test_happy_path(self, mocker, cog):
        message = MagicMock(spec=discord.Message)
        message.author.id = 123
        message.content = "Hello"
        message.channel.typing.return_value.__aenter__ = mocker.AsyncMock()
        message.channel.typing.return_value.__aexit__ = mocker.AsyncMock()
        gu = GPTUser(123, "TestUser", "System Prompt")
        gu.push_conversation({"role": "user", "content": "Hello"})
        cog.should_reply = mocker.MagicMock(return_value=True)
        cog.copy_public_reply = mocker.MagicMock()
        cog.get_user_from_context = mocker.MagicMock(return_value=gu)
        cog.remove_bot_mention = mocker.MagicMock(return_value="Hello")
        cog.send_to_chatgpt = mocker.AsyncMock(return_value="Hi")
        cog.reply = mocker.AsyncMock()

        await cog.on_message(message)

        cog.should_reply.assert_called_once_with(message)
        cog.copy_public_reply.assert_called_once_with(message)
        cog.get_user_from_context.assert_called_once_with(message)
        cog.remove_bot_mention.assert_called_once_with("Hello")
        cog.send_to_chatgpt.assert_called_once_with(gu)
        cog.reply.assert_called_once_with(
            message, "\nHi\n\n\n*📏20/4097    🗣️gpt-3.5-turbo  *", None
        )
