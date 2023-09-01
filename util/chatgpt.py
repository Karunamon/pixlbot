from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import List, Optional, TypedDict, Literal
from enum import Flag, auto

from util.souls import Soul, SOUL_PROMPT

import tiktoken


class ConversationLine(TypedDict):
    role: Literal["user", "system", "assistant"]
    content: str


class UserConfig(Flag):
    SHOWSTATS = auto()
    TELEPATHY = auto()
    NAMESUFFIX = auto()
    TERSEWARNINGS = auto()


DEFAULT_FLAGS = UserConfig.SHOWSTATS | UserConfig.NAMESUFFIX


@dataclass
class Model:
    model: str = "gpt-3.5-turbo"
    max_tokens: int = 768
    temperature: float = 0.5
    max_context: int = 4097


class GPTUser:
    __slots__ = [
        "id",
        "name",
        "idhash",
        "_conversation",
        "last",
        "staleseen",
        "_soul",
        "_model",
        "config",
        "_encoding",
        "_conversation_len",
        "prompt_info",
    ]
    id: int
    name: str
    idhash: str
    _conversation: List[ConversationLine]
    last: datetime
    staleseen: bool
    _soul: Optional[Soul]
    _model: Model
    config: UserConfig
    _encoding: tiktoken.Encoding
    _conversation_len: int
    prompt_info: Optional[str]

    def __init__(
        self,
        uid: int,
        uname: str,
        sysprompt: str,
        prompt_info: Optional[str],
        model: Model = Model(),
        config: UserConfig = DEFAULT_FLAGS,
    ):
        """
        :param config: A UserConfig bitfield.
        :param uid: The unique ID of the user (Usually a Discord snowflake).
        :param uname: The username of the user.
        :param sysprompt: The system prompt to be used for conversation generation.
        :param prompt_info: A very short description of the system prompt.
        :param model: The model object to be used for conversation generation.
        """
        self.id = uid
        self.name = uname
        self.idhash = sha256(str(uid).encode("utf-8")).hexdigest()
        self.staleseen = False
        self.config = config
        self._conversation = [{"role": "system", "content": sysprompt}]
        self.last = datetime.utcnow()
        self._soul = None
        self.prompt_info = prompt_info
        self._model = model
        self._encoding = tiktoken.encoding_for_model(model.model)
        self._conversation_len = self._calculate_conversation_len()
        if UserConfig.NAMESUFFIX in config:
            self._add_namesuffix()

    @property
    def conversation(self):
        return self._conversation

    @conversation.setter
    def conversation(self, value):
        self._conversation = value
        self.last = datetime.utcnow()
        # It would be more efficient to increment/decrement the length as needed, but we have too many use cases where
        # we need to directly modify the conversation, so recalculating on every update is an intentional choice here.
        self._conversation_len = self._calculate_conversation_len()

    def format_conversation(self, bot_name: str) -> str:
        """Returns a pretty-printed version of user's conversation history with system prompts removed"""
        formatted_conversation = [
            f"{self.name}: {msg['content']}"
            if msg["role"] == "user"
            else f"{bot_name}: {msg['content']}"
            for msg in self.conversation
            if msg["role"] != "system"
        ]
        formatted_conversation = "\n".join(formatted_conversation)
        return formatted_conversation

    @property
    def is_stale(self) -> bool:
        """Check if the user conversation is stale (More than six hours old)"""
        current_time = datetime.utcnow()
        age = current_time - self.last
        return age > timedelta(hours=6)

    @property
    def oversized(self):
        """
        Returns if the current conversation is or is about to be too large to fit into the current model's context
        """
        return self.conversation_len + self.model.max_tokens >= self.model.max_context

    @property
    def soul(self):
        return self._soul

    @soul.setter
    def soul(self, new_soul: Soul):
        self._soul = new_soul
        self.conversation = [
            {"role": "system", "content": SOUL_PROMPT.format(**new_soul._asdict())}
        ]
        self.prompt_info = "Soul"

    def _calculate_conversation_len(self) -> int:
        if self._conversation:
            return sum(
                len(self._encoding.encode(entry["content"]))
                for entry in self._conversation
            )
        else:
            return 0

    def push_conversation(self, utterance: ConversationLine, copy=False):
        """Append the given line of dialogue to this user's conversation"""
        if copy:
            self._conversation.insert(-1, utterance)
        else:
            self._conversation.append(utterance)
        self._conversation_len += len(self._encoding.encode(utterance["content"]))

    def pop_conversation(self, index: int = -1) -> ConversationLine:
        """Pop lines of dialogue from this user's conversation"""
        popped_item = self._conversation.pop(index)
        self._conversation_len -= len(self._encoding.encode(popped_item["content"]))
        return popped_item

    @property
    def conversation_len(self):
        """Return the length of this user's conversation in tokens"""
        return self._conversation_len

    def freshen(self):
        """Clear the stale seen flag and set the last message time to now"""
        self.staleseen = False
        self.last = datetime.utcnow()

    @property
    def model(self):
        return self._model

    @model.setter
    def model(self, new_model: Model):
        self._encoding = tiktoken.encoding_for_model(new_model.model)
        self._model = new_model
        self._conversation_len = self._calculate_conversation_len()

    def _add_namesuffix(self):
        """Apply the user's name to the end of the first system prompt."""
        self.conversation[0][
            "content"
        ] += (
            f"\nThe user's name is {self.name} and it should be used wherever possible."
        )
        # This didn't trigger the setter for conversation, manually update length
        self._conversation_len = self._calculate_conversation_len()
