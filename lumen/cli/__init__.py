"""The `lumen` command.

python -m lumen index            build / refresh the file index
python -m lumen stats            show index size
python -m lumen search WORDS     search directly (no AI)
python -m lumen ask "QUESTION"   one question to the agent
python -m lumen chat             interactive terminal chat
"""

import argparse
import logging
import sys

from . import chat, index, search, serve


def main(argv=None):
    p = argparse.ArgumentParser(prog="lumen")
    sub = p.add_subparsers(dest="cmd", required=True)
    ip = sub.add_parser("index")
    ip.add_argument("--no-captions", action="store_true", help="skip describing images/scans")
    ip.add_argument("--no-media", action="store_true", help="skip video/audio")
    ip.add_argument("--power", choices=["auto", "saver", "performance"], help="override LUMEN_POWER")
    ip.add_argument("--no-transcripts", action="store_true", help="video/audio: skip speech-to-text")
    ip.set_defaults(fn=index.run)
    sub.add_parser("stats").set_defaults(fn=search.stats)
    sp = sub.add_parser("search")
    sp.add_argument("words", nargs="*")
    sp.add_argument("--ext", default="")
    sp.add_argument("--after", default="")
    sp.add_argument("--before", default="")
    sp.add_argument("--folder", default="")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(fn=search.search)
    ap = sub.add_parser("ask")
    ap.add_argument("question", nargs="+")
    ap.set_defaults(fn=chat.ask)
    sub.add_parser("chat").set_defaults(fn=chat.chat)
    sv = sub.add_parser("serve", help="API server for the desktop/mobile app")
    sv.add_argument("--lan", action="store_true", help="also accept paired phones on the local network")
    sv.add_argument("--port", type=int, default=8765)
    sv.set_defaults(fn=serve.run)
    a = p.parse_args(argv)
    from ..core import errors
    from ..core import logging as lumen_logging
    from ..core.bootstrap import load_saved_state

    # `serve` sets up its own log; an index run started by the app writes indexer.log
    if a.cmd != "serve":
        lumen_logging.setup("indexer" if a.cmd == "index" else "cli")
    log = logging.getLogger("lumen.cli")
    try:
        load_saved_state()
        a.fn(a)
    except errors.LumenError as e:
        log.warning("%s: %s", a.cmd, e.message)
        sys.exit(f"{e.message}{chr(10) + e.hint if e.hint else ''}")
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        log.exception("lumen %s failed", a.cmd)
        log_file = lumen_logging.log_file("indexer" if a.cmd == "index" else "cli")
        print(f"lumen {a.cmd} failed. The details are in {log_file}", file=sys.stderr)
        raise
