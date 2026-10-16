"""Pairing phones with this laptop."""

import socket

from fastapi import APIRouter, Depends

from ...core import errors
from ..deps import local_only, services
from ..network import lan_ip
from ..schemas import PairReq
from ..services import Services
from ..services.pairing import CODE_SECONDS

router = APIRouter()


@router.post("/api/pair/start", dependencies=[Depends(local_only)])
def pair_start(svc: Services = Depends(services)):
    code = svc.pairing.start()
    return {"code": code, "expires_in": CODE_SECONDS, "lan": svc.lan, "address": f"{lan_ip()}:{svc.port}"}


@router.post("/api/pair")
def pair(body: PairReq, svc: Services = Depends(services)):
    paired = svc.pairing.pair(body.code, body.name)
    if paired is None:
        raise errors.WrongCode("Wrong or expired code")
    token, device = paired
    return {"token": token, "host": socket.gethostname(), "device_id": device["id"]}


@router.get("/api/devices", dependencies=[Depends(local_only)])
def devices(svc: Services = Depends(services)):
    return [{k: d[k] for k in ("id", "name", "paired")} for d in svc.pairing.devices()]


@router.delete("/api/devices/{device_id}", dependencies=[Depends(local_only)])
def unpair(device_id: str, svc: Services = Depends(services)):
    svc.pairing.unpair(device_id)
    return {"ok": True}


@router.get("/api/hello")
def hello():
    """Unauthenticated: lets a phone check it found Lumen before pairing."""
    return {"app": "lumen", "host": socket.gethostname()}
