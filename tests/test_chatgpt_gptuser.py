from datetime import datetime, timedelta
from hashlib import sha256

from util.souls import Soul
from util.chatgpt import GPTUser, UserConfig


class TestGPTUser:
    #  Tests that a GPTUser object is created with the correct attributes
    def test_create_GPTUser_object(self):
        user = GPTUser(1, "John", "Hello.", None)
        assert user.id == 1
        assert user.name == "John"
        assert user.idhash == sha256(str(1).encode("utf-8")).hexdigest()
        assert user._conversation == [
            {
                "role": "system",
                "content": "Hello.\nThe user's name is John and it should be used wherever possible.",
            }
        ]
        assert isinstance(user.last, datetime)
        assert user.staleseen is False
        assert user._soul is None
        assert not UserConfig.TELEPATHY & user.config

    #  Tests that the conversation history is properly formatted
    def test_format_conversation(self):
        user = GPTUser(1, "John", "Hello", None)
        user.push_conversation({"role": "user", "content": "Hi there"})
        user.push_conversation({"role": "assistant", "content": "How can I help you?"})
        formatted_conversation = user.format_conversation("Bot")
        expected_output = "John: Hi there\nBot: How can I help you?"
        assert formatted_conversation == expected_output

    #  Tests that a new soul can be assigned to a GPTUser object
    def test_assign_new_soul(self):
        user = GPTUser(1, "John", "Hello", None)
        soul = Soul("John", "short", "long", "plan")
        user.soul = soul
        assert user._soul == soul
        assert len(user._conversation) == 1

    #  Tests that the is_stale property returns True when the last message was sent more than 6 hours ago
    def test_is_stale_property(self):
        user = GPTUser(1, "John", "Hello", None)
        assert user.is_stale is False
        user.last = datetime.utcnow() - timedelta(hours=7)
        assert user.is_stale is True

    #  Tests that the oversized property returns True when the conversation history exceeds the maximum length
    def test_oversized_property(self):
        user = GPTUser(1, "John", "Hello", None)
        message = {
            "role": "user",
            "content": "Lorem ipsum dolor sit amet, consectetur adipiscing elit " * 50,
        }
        for i in range(100):
            user.push_conversation(message)
        assert user.oversized is True
        for i in range(100):
            user.pop_conversation()
        assert user.oversized is False
