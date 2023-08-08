from collections import namedtuple
from datetime import datetime, timedelta
from hashlib import sha256
from typing import List, Dict, Optional

from util.souls import Soul, SOUL_PROMPT

import tiktoken

Model = namedtuple(
    "Model", "model max_tokens temperature", defaults=("gpt-4", 512, 0.5)
)
class GPTUser:
    __slots__ = [
        "id",
        "name",
        "idhash",
        "_conversation",
        "last",
        "staleseen",
        "_soul",
        "telepathy",
        "model",
        "_encoding",
    ]
    id: int
    name: str
    idhash: str
    _conversation: List[Dict[str, str]]
    last: datetime
    stale: bool
    staleseen: bool
    _soul: Optional[Soul]
    telepathy: bool
    model: Model
    _encoding: tiktoken.Encoding

    # noinspection PyArgumentList
    def __init__(
        self,
        uid: int,
        uname: str,
        sysprompt: str,
        suffix: bool = True,
        model: Model = Model(),
    ):
        self.id = uid
        self.name = uname
        self.idhash = sha256(str(uid).encode("utf-8")).hexdigest()
        self.staleseen = False
        prompt_suffix = (
            f" The user's name is {self.name} and it should be used wherever possible."
        )
        self._conversation = [
            {
                "role": "system",
                "content": sysprompt + prompt_suffix if suffix else sysprompt,
            }
        ]
        self.last = datetime.utcnow()
        self._soul = None
        self.telepathy = False
        self.model = model
        self._encoding = tiktoken.encoding_for_model(model.model)

    @property
    def conversation(self):
        return self._conversation

    @conversation.setter
    def conversation(self, value):
        self._conversation = value
        self.last = datetime.utcnow()

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
    def is_stale(self):
        current_time = datetime.utcnow()
        age = current_time - self.last
        return age > timedelta(hours=6)

    @property
    def oversized(self):
        return self._conversation_len + MAX_TOKENS >= MAX_LENGTH

    @property
    def soul(self):
        return self._soul

    @soul.setter
    def soul(self, new_soul: Soul):
        self._soul = new_soul
        self.conversation = [
            {"role": "system", "content": SOUL_PROMPT.format(**new_soul._asdict())}
        ]

    @property
    def _conversation_len(self):
        if self.conversation:
            return sum(
                len(self._encoding.encode(entry["content"]))
                for entry in self.conversation
            )
        else:
            return 0

    def push_conversation(self, utterance: dict[str, str], copy=False):
        """Append the given line of dialogue to this conversation"""
        if copy:
            self._conversation.insert(-1, utterance)
        else:
            self._conversation.append(utterance)
        self.conversation = self._conversation  # Trigger the setter

    def pop_conversation(self, index: int = -1):
        """Pop lines of dialogue from this conversation"""
        p = self._conversation.pop(index)
        self.conversation = self._conversation  # Trigger the setter
        return p

    def freshen(self):
        """Clear the stale seen flag and set the last message time to now"""
        self.staleseen = False
        self.last = datetime.utcnow()


MAX_LENGTH = 4097
MAX_TOKENS = 512
