import datetime
import io
from unittest.mock import Mock, MagicMock

import discord
import discord.iterators
import pytest

from cogs.chatgpt import ChatGPT
from util.chatgpt import GPTUser


class TestChatGPTCommands:
    @pytest.fixture
    def bot(self):
        bot = MagicMock()
        bot.config = {
            "ChatGPT": {
                "api_key": "foo",
                "default": {
                    "system_prompt": "System prompt",
                    "model_name": "gpt-3.5-turbo",
                },
            }
        }
        bot.user = MagicMock()
        bot.user.display_name = "Bot"
        return bot

    @pytest.fixture
    def cog(self, bot):
        cog = ChatGPT(bot)
        cog.users = {123: GPTUser(123, "User", "My prompt", None)}
        return cog

    @pytest.fixture
    def gu_mini_conversation(self, cog):
        gu: GPTUser = cog.users[123]
        gu.push_conversation({"role": "user", "content": "Hello"})
        gu.push_conversation({"role": "assistant", "content": "Hi"})
        return gu

    #  Tests that the bot resets the conversation history
    @pytest.mark.asyncio
    async def test_reset(self, mocker, cog):
        cog.reset.cog = cog
        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.author.id = 123
        ctx.author.display_name = "Nuvie"
        ctx.respond = mocker.AsyncMock()
        ctx.command = MagicMock(spec=discord.ApplicationCommand)
        assert 123 in cog.users
        await cog.reset(ctx, "")
        assert "Nuvie" in cog.users[123].conversation[0]["content"]
        assert len(cog.users[123].conversation) == 1
        ctx.respond.assert_called_once_with(
            "Your conversation history has been reset.", ephemeral=True
        )

    #  Tests that stale conversations can be resumed
    @pytest.mark.asyncio
    async def test_continue(self, mocker, cog):
        cog.continue_conversation.cog = cog
        ctx = mocker.Mock()
        ctx.respond = mocker.AsyncMock()
        ctx.author.id = 123
        cog.users[123].staleseen = True

        await cog.continue_conversation(ctx)

        assert not cog.users[123].staleseen
        assert isinstance(cog.users[123].last, datetime.datetime)
        ctx.respond.assert_called_once_with(
            "Your conversation has been resumed.", ephemeral=True
        )

    #  Tests that the bot shows the conversation history
    @pytest.mark.asyncio
    async def test_show_conversation(self, mocker, cog):
        cog.show_conversation.cog = cog
        ctx = Mock(spec=discord.ApplicationContext)
        ctx.author.id = 123
        ctx.author.send = mocker.AsyncMock()
        ctx.respond = mocker.AsyncMock()
        cog.format_conversation = mocker.Mock(return_value="User: Hello\nBot: Hi")
        await cog.show_conversation(ctx)
        ctx.author.send.assert_called_once_with("Here is your conversation with Bot:")
        ctx.respond.assert_called_once_with(
            "I've sent you a private message with your conversation history.",
            ephemeral=True,
        )

    #  Tests that the bot saves the conversation history to a text file
    @pytest.mark.asyncio
    async def test_save_conversation(self, mocker, cog, gu_mini_conversation):
        cog.save_conversation.cog = cog
        ctx = Mock(spec=discord.ApplicationContext)
        ctx.author.id = 123
        ctx.author.send = mocker.AsyncMock()
        ctx.respond = mocker.AsyncMock()

        data = io.BytesIO()
        data.write(gu_mini_conversation.format_conversation("Bot").encode())
        data.seek(0)
        discord_file = discord.File(data, filename="conversation.txt")

        await cog.save_conversation(ctx)

        ctx.author.send.assert_called_once()
        assert ctx.author.send.call_args[0][0] == "Here is your conversation with Bot:"
        actual_file_sent = ctx.author.send.call_args[1]["file"]
        assert actual_file_sent.fp.read() == discord_file.fp.read()
        ctx.respond.assert_called_once_with(
            "I've sent you a private message with your conversation history as a text file.",
            ephemeral=True,
        )

    #  Tests that the bot summarizes the last n messages in the current channel
    @pytest.mark.asyncio
    async def test_summarize_chat(self, mocker, cog):
        cog.summarize_chat.cog = cog
        cog.send_to_chatgpt = mocker.AsyncMock(return_value="Summary")

        channel = Mock(spec=discord.TextChannel)
        channel.is_nsfw.return_value = False
        channel.history.return_value = mocker.AsyncMock(
            spec=discord.iterators.HistoryIterator
        )
        channel.typing.return_value.__aenter__ = mocker.AsyncMock()
        channel.typing.return_value.__aexit__ = mocker.AsyncMock()
        author = Mock(spec=discord.Member)
        author.name = "User"  # Can't set name in the constructor
        channel.history.return_value.flatten.return_value = [
            Mock(
                spec=discord.Message,
                author=author,
                content="Hello",
            )
        ]
        ctx = Mock(spec=discord.ApplicationContext)
        ctx.channel = channel
        ctx.respond = mocker.AsyncMock()
        ctx.send = mocker.AsyncMock()
        ctx.send.return_value = Mock(spec=discord.Message)
        ctx.send.return_value.edit = mocker.AsyncMock()

        await cog.summarize_chat(ctx, 1, "")

        cog.send_to_chatgpt.assert_called_once()
        assert cog.send_to_chatgpt.call_args[0][1] == [
            {
                "role": "system",
                "content": "The following is a conversation between various people in a Discord chat. It is "
                "formatted such that each line begins with the name of the speaker, a colon, "
                "and then whatever the speaker said. Please provide a summary of the conversation "
                "beginning below: \nUser: Hello\n",
            }
        ]
        ctx.send.assert_called_with("Now generating summary of the last 1 messages…")
        ctx.send.return_value.edit.assert_called_with(
            content="Summary of the last 1 messages:\n\nSummary"
        )
