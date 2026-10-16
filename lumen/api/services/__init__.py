"""The long-lived state behind the API, created once per app and handed to routes as a dependency."""

from dataclasses import dataclass, field

from .chats import Chats
from .indexer import Indexer
from .pairing import Pairing


@dataclass
class Services:
    indexer: Indexer = field(default_factory=Indexer)
    chats: Chats = field(default_factory=Chats)
    pairing: Pairing = field(default_factory=Pairing)
    lan: bool = False  # accepting paired phones on the local network
    port: int = 8765
