"""What the API answers, route by route (FastAPI documents and checks these).

Each model names the fields the app relies on, with their types. Extra fields are allowed and
passed on as they are, so adding one in the code never silently drops it from an answer.
"""

from .chats import ChatEventOut, ChatOut, Pending
from .common import Deleted, Message, Ok, Out
from .files import FileInfoOut, HitOut, ImageHitOut, SegmentOut
from .indexing import (
    Excluded,
    ExcludedAndRemoved,
    FolderPaused,
    IndexPausing,
    IndexProgressOut,
    IndexStarted,
    IndexStopped,
    RecentFile,
    Removed,
)
from .pairing import DeviceOut, Hello, Paired, PairStarted
from .planner import ListOut, NoteOut, NoteSummary, ReminderOut, TodoOut
from .providers import CheckStep, ModelCheck, ModelOut, ProviderOut, ProvidersOut, ProviderTest, PullOut, Role
from .status import Diagnostics, FolderOut, IndexStats, ModelsOut, PowerOut, SettingsOut, StatusOut

__all__ = [
    "NoteSummary",
    "NoteOut",
    "ListOut",
    "TodoOut",
    "ReminderOut",
    "Out",
    "Ok",
    "Message",
    "Deleted",
    "HitOut",
    "ImageHitOut",
    "SegmentOut",
    "FileInfoOut",
    "ChatOut",
    "ChatEventOut",
    "Pending",
    "IndexStarted",
    "IndexStopped",
    "IndexPausing",
    "RecentFile",
    "IndexProgressOut",
    "Excluded",
    "ExcludedAndRemoved",
    "Removed",
    "FolderPaused",
    "IndexStats",
    "FolderOut",
    "PowerOut",
    "ModelsOut",
    "StatusOut",
    "SettingsOut",
    "Diagnostics",
    "ProviderOut",
    "Role",
    "PullOut",
    "ProvidersOut",
    "ModelOut",
    "ProviderTest",
    "CheckStep",
    "ModelCheck",
    "PairStarted",
    "Paired",
    "DeviceOut",
    "Hello",
]
