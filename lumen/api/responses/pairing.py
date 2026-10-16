"""Answers about pairing."""

from .common import Out


class PairStarted(Out):
    code: str
    expires_in: int
    lan: bool
    address: str


class Paired(Out):
    token: str
    host: str
    device_id: str


class DeviceOut(Out):
    id: str
    name: str
    paired: float


class Hello(Out):
    app: str
    host: str
