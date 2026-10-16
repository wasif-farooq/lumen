"""`lumen serve`: the API for the app."""

import argparse


def run(a: argparse.Namespace) -> None:
    from ..api.serve import run as serve

    serve(lan=a.lan, port=a.port)
