"""Errors with a message meant for people. Raise these anywhere; the API turns them into a JSON
error the app can show, and the CLI prints the message.

    {"detail": message, "error": {"code", "message", "hint", "id"}}

`detail` is kept for apps from before this format.
"""


class LumenError(Exception):
    status = 500
    code = "error"

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class InvalidInput(LumenError):
    """The request can't be done as asked (wrong value, missing folder…)."""

    status, code = 400, "invalid_input"


class NotPaired(LumenError):
    status, code = 401, "not_paired"


class LocalOnly(LumenError):
    """Settings, keys and pairing can only be changed on the laptop itself."""

    status, code = 403, "local_only"


class OutsideFolders(LumenError):
    """A path outside the indexed folders."""

    status, code = 403, "outside_folders"


class WrongCode(LumenError):
    """A pairing code that is wrong, expired or used up."""

    status, code = 403, "wrong_code"


class NotFound(LumenError):
    status, code = 404, "not_found"


class Conflict(LumenError):
    """Not now: something else is going on (indexing runs, nothing is waiting for approval…)."""

    status, code = 409, "conflict"


class VoiceUnavailable(LumenError):
    """Voice chat can't run here: its speech engine or voice is missing."""

    status, code = 503, "voice_unavailable"


class ProviderUnavailable(LumenError):
    """A model provider can't be reached or refused the request."""

    status, code = 502, "provider_unavailable"


# HTTP status -> code, for errors raised as plain HTTPException (e.g. by FastAPI itself)
CODES = {
    400: "invalid_input",
    401: "not_paired",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "invalid_input",
    502: "provider_unavailable",
}
