"""Earned automatic moving, per folder: each folder starts in "suggest" (you approve or correct
every suggestion) and moves mail on its own only once its recent suggestions were right often enough;
it goes back to suggesting when the moves you notice are wrong too often.

Replays the model's real answers from the last mail_bench.py run (data/mail_bench_last.json) as a long
stream of incoming mail (resampled, many random orders), and simulates you:
- suggest mode: you look at every suggestion (approve it, or move the mail where it belongs);
- automatic mode: you notice only some wrong moves (--notice, default half).

    uv run python scripts/mail_bench.py --n 200     # first: the model's answers
    uv run python scripts/mail_earned_bench.py [--mails 1000] [--runs 50] [--notice 0.5]
"""

import argparse
import json
import random
import statistics
from collections import deque
from pathlib import Path

LAST = Path(__file__).resolve().parents[1] / "data" / "mail_bench_last.json"


def simulate(answers: list[dict], mails: int, window: int, bar: float, notice: float, rng: random.Random) -> dict:
    """One stream of mail. Returns what happened: moves, mistakes, when each folder earned automatic."""
    folders = sorted({a["mail"]["folder"] for a in answers})
    record = {f: deque(maxlen=window) for f in folders}  # recent outcomes of this folder's suggestions/moves
    auto = dict.fromkeys(folders, False)
    earned_at: dict[str, int | None] = dict.fromkeys(folders, None)
    demoted = 0
    reviewed = moved_auto = wrong_auto = wrong_unnoticed = 0
    for i in range(mails):
        a = rng.choice(answers)
        want, got = a["mail"]["folder"], a["got"].get("folder")
        if got not in record:
            reviewed += 1  # no usable answer: stays in the Inbox, shown as unsure
            continue
        right = got == want
        if auto[got]:
            moved_auto += 1
            if not right:
                wrong_auto += 1
                if rng.random() < notice:  # you spot it in the wrong folder and move it back
                    record[got].append(False)
                else:
                    wrong_unnoticed += 1
            else:
                record[got].append(True)
            if len(record[got]) == window and sum(record[got]) / window < bar:
                auto[got] = False  # back to suggesting
                demoted += 1
        else:
            reviewed += 1  # a suggestion you approve or correct
            record[got].append(right)
            if len(record[got]) == window and sum(record[got]) / window >= bar:
                auto[got] = True
                if earned_at[got] is None:
                    earned_at[got] = i + 1
    return {
        "auto_share": moved_auto / mails,
        "reviewed_share": reviewed / mails,
        "wrong_auto": wrong_auto,
        "wrong_unnoticed": wrong_unnoticed,
        "auto_precision": 1 - wrong_auto / moved_auto if moved_auto else None,
        "earned_at": earned_at,
        "auto_at_end": [f for f, on in auto.items() if on],
        "demoted": demoted,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mails", type=int, default=1000)
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--notice", type=float, default=0.5, help="share of wrong automatic moves you notice")
    args = ap.parse_args()
    answers = json.loads(LAST.read_text())
    folders = sorted({a["mail"]["folder"] for a in answers})

    # how good each folder's suggestions really are (the model's answers this stream is made of)
    print(f"From {len(answers)} real model answers; {args.mails} mails per run, {args.runs} runs, "
          f"you notice {100 * args.notice:.0f}% of wrong automatic moves.\n")  # fmt: skip
    print("Each folder's suggestions (precision of what the model puts there):")
    for f in folders:
        put = [a for a in answers if a["got"].get("folder") == f]
        ok = sum(a["mail"]["folder"] == f for a in put)
        print(f"  {f:14s} {100 * ok / max(1, len(put)):5.1f}%  ({len(put)} suggestions in the sample)")

    print(
        "\n bar  window | moved on its own | you review | wrong moves (unnoticed) per 1000 mail |"
        " right when moved on its own"
    )
    results = {}
    for bar in (0.90, 0.95, 0.98):
        for window in (20, 30, 50):
            seeds = range(args.runs)
            runs = [simulate(answers, args.mails, window, bar, args.notice, random.Random(s)) for s in seeds]
            results[(bar, window)] = runs
            per = 1000 / args.mails
            share = statistics.mean(r["auto_share"] for r in runs)
            review = statistics.mean(r["reviewed_share"] for r in runs)
            wrong = statistics.mean(r["wrong_auto"] for r in runs) * per
            unnoticed = statistics.mean(r["wrong_unnoticed"] for r in runs) * per
            precisions = [r["auto_precision"] for r in runs if r["auto_precision"] is not None]
            prec = f"{100 * statistics.mean(precisions):5.1f}%" if precisions else "   – "
            print(f" {bar:.2f}  {window:4d}  |      {100 * share:5.1f}%      |   {100 * review:5.1f}%   |"
                  f"        {wrong:5.1f} ({unnoticed:4.1f})                  |   {prec}")  # fmt: skip

    bar, window = 0.95, 30
    runs = results[(bar, window)]
    print(
        f"\nWith a 95% bar over the last {window}: when each folder earned automatic moving"
        " (mail number in the stream, median of runs)"
    )
    for f in folders:
        at = [r["earned_at"][f] for r in runs if r["earned_at"][f] is not None]
        stays = sum(f in r["auto_at_end"] for r in runs)
        when = f"after ~{int(statistics.median(at))} mails" if at else "never"
        print(f"  {f:14s} {when:20s} automatic at the end in {stays}/{len(runs)} runs")
    print(f"  demoted back to suggesting: {statistics.mean(r['demoted'] for r in runs):.1f} times per run")


if __name__ == "__main__":
    main()
