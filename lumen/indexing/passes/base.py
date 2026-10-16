"""The AI passes that run after the scan (Strategy): each one says whether it should run and
then runs, reporting each file to the run's Progress. The pipeline doesn't know their details."""

from ...core.settings import settings
from ..progress import Progress


class IndexPass:
    name = ""  # the phase the app shows, and the key of its stats in the run summary

    def wanted(self) -> bool:
        raise NotImplementedError

    def run(self, conn, progress: Progress) -> dict:
        raise NotImplementedError


def _unreachable(what: str, e: Exception) -> dict:
    return {"error": f"Vision model ({settings.vision_provider}) not reachable: {e or 'no connection'}; {what} skipped"}


class Captions(IndexPass):
    """Describe images and scanned PDFs with the vision model."""

    name = "captions"

    def __init__(self, enabled: bool | None = None):
        self.enabled = enabled

    def wanted(self) -> bool:
        return settings.captions if self.enabled is None else self.enabled

    def run(self, conn, progress):
        from .captions import caption_pending

        try:
            return caption_pending(conn, progress.item)
        except ConnectionError as e:
            return _unreachable("captions", e)


class Visual(IndexPass):
    """Image signatures for search by look and similar images."""

    name = "visual"

    def wanted(self) -> bool:
        return settings.visual

    def run(self, conn, progress):
        from .visual import process_pending

        return process_pending(conn, progress.item)


class Media(IndexPass):
    """Video and audio: what it shows (frames) and what is said (speech)."""

    name = "media"

    def __init__(self, enabled: bool | None = None, transcripts: bool | None = None):
        self.enabled = enabled
        self.transcripts = transcripts

    def wanted(self) -> bool:
        return settings.media if self.enabled is None else self.enabled

    def run(self, conn, progress):
        from .media import process_pending

        transcripts = settings.transcripts if self.transcripts is None else self.transcripts
        try:
            return process_pending(conn, progress.item, transcripts=transcripts)
        except ConnectionError as e:
            return _unreachable("video/audio", e)
