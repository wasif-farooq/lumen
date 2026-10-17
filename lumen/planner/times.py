"""Plain-words times for reminders and due dates: "tomorrow at 5", "in 2 hours", "every Monday 9am".

Only phrases this module knows are understood; anything else gives None, so the caller asks the
user instead of guessing (a reminder at the wrong time is worse than a question). Times are the
laptop's local time. The model never works out dates: it passes the user's own words here.

Choices for words that leave something open:
- an hour without am/pm: 1-7 means afternoon/evening ("at 5" is 17:00), 8-12 as said
- a day without a time: 9:00; "morning" 9:00, "afternoon" 15:00, "evening" 18:00, "tonight" 20:00
- a time without a day: today if it is still ahead, otherwise tomorrow
- "next Monday" and "Monday": the coming Monday (a week ahead when today is Monday)
- "midnight": 23:59 of that day
"""

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

REPEATS = ("none", "daily", "weekdays", "weekly", "monthly")

DAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}  # fmt: skip
MONTHS = {
    name: n
    for n, names in enumerate(
        [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",),
         ("jun", "june"), ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"),
         ("oct", "october"), ("nov", "november"), ("dec", "december")],
        start=1,
    )
    for name in names
}  # fmt: skip
PARTS = {"morning": 9, "afternoon": 15, "evening": 18, "tonight": 20, "night": 20}
NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "a few": 3, "a couple of": 2, "a couple": 2, "couple of": 2,
}  # fmt: skip
DEFAULT_HOUR = 9

_DAY = r"(?:" + "|".join(sorted(DAYS, key=len, reverse=True)) + r")"
_MONTH = r"(?:" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")"
_ORD = r"(\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?: (\d{4}))?"


@dataclass
class When:
    at: datetime  # local time, no timezone
    repeat: str = "none"


def parse_when(text: str, now: datetime) -> When | None:
    """When the words mean, from `now` (local time); None when it isn't clear."""
    t = " " + re.sub(r"[,!?;]", " ", text.lower()).replace("’", "'") + " "
    t = re.sub(r"\s+", " ", t)
    repeat, weekday, monthday, t = _repeat(t)

    if (rel := _relative(t)) is not None:
        delta, by_days, t = rel
        hm, part, _ = _time(t)
        if not by_days or (hm is None and part is None):
            return When(now + delta, repeat)  # "in 2 hours", "in a week" (same time of day)
        day = (now + delta).date()  # "in 3 days at 9": that day, at that time
        hm = hm or (PARTS[part], 0)  # type: ignore[index]
        return When(datetime(day.year, day.month, day.day, hm[0], hm[1]), repeat)

    day, t = _day(t, now)
    hm, part, t = _time(t)
    if day is None and weekday is not None:
        day = _coming(now.date(), weekday, include_today=True)  # passed today: moved on a week below
    if day is None and monthday is not None:
        day = _month_day(now.date(), monthday)
    if day is None and hm is None and part is None and repeat == "none":
        return None
    if hm is None:
        hm = (PARTS[part], 0) if part else (DEFAULT_HOUR, 0)
    elif part in ("afternoon", "evening", "tonight", "night") and hm[0] < 12:
        hm = (hm[0] + 12, hm[1])  # "at 7 in the evening"
    elif part == "morning" and hm[0] == 12:
        hm = (0, hm[1])
    if day is None:
        day = now.date()
        if datetime.combine(day, datetime.min.time()).replace(hour=hm[0], minute=hm[1]) <= now:
            day += timedelta(days=1)  # a time that has passed today: tomorrow
        if repeat == "weekdays":
            while day.weekday() >= 5:
                day += timedelta(days=1)
    at = datetime(day.year, day.month, day.day, hm[0], hm[1])
    if repeat != "none" and at <= now:
        at = next_after(at, repeat, now)
    return When(at, repeat)


def next_after(anchor: datetime, repeat: str, now: datetime) -> datetime:
    """The first time after `now` that a reminder set for `anchor` repeats ("monthly" keeps the
    anchor's day of the month, or the month's last day when it is shorter)."""
    if repeat not in REPEATS or repeat == "none":
        raise ValueError(f"not a repeat: {repeat}")
    at = anchor
    if repeat == "monthly":
        n = 0
        while at <= now:
            n += 1
            y, m = divmod(anchor.month - 1 + n, 12)
            year, month = anchor.year + y, m + 1
            at = anchor.replace(year=year, month=month, day=min(anchor.day, calendar.monthrange(year, month)[1]))
        return at
    step = timedelta(weeks=1) if repeat == "weekly" else timedelta(days=1)
    if at <= now:  # jump close to now, then step (a reminder missed for months)
        at += step * max(0, (now - at) // step)
    while at <= now or (repeat == "weekdays" and at.weekday() >= 5):
        at += step
    return at


def describe(at: datetime, repeat: str, now: datetime) -> str:
    """For people: "tomorrow at 17:00", "Mon 19 Oct at 09:00, every week"."""
    if at.date() == now.date():
        day = "today"
    elif at.date() == now.date() + timedelta(days=1):
        day = "tomorrow"
    elif 0 < (at.date() - now.date()).days < 7:
        day = at.strftime("%A")
    else:
        day = at.strftime("%a %-d %b") + (f" {at.year}" if at.year != now.year else "")
    every = {"daily": "every day", "weekdays": "every weekday", "weekly": "every week", "monthly": "every month"}
    return f"{day} at {at:%H:%M}" + (f", {every[repeat]}" if repeat in every else "")


# ---------- the parts of a phrase ----------


def _repeat(t: str) -> tuple[str, int | None, int | None, str]:
    """ "every Monday", "daily", "every month on the 1st"… -> (repeat, weekday, day of month, rest)."""
    rules = [
        (r" (?:every|each) ?(?:single )?day | daily | everyday ", "daily"),
        (r" (?:every|each|on) weekdays? | weekdays | every working day ", "weekdays"),
        (rf" (?:every|each) ({_DAY})s? | on ({_DAY})s ", "weekly"),
        (r" (?:every|each) week | weekly ", "weekly"),
        (rf" (?:every|each) month(?: on)?(?: the)? {_ORD} | (?:every|each) {_ORD} of the month ", "monthly"),
        (r" (?:every|each) month | monthly ", "monthly"),
    ]
    for pattern, repeat in rules:
        if m := re.search(pattern, t):
            groups = [g for g in m.groups() if g]
            weekday = DAYS.get(groups[0]) if groups and repeat == "weekly" else None
            monthday = int(groups[0]) if groups and repeat == "monthly" else None
            return repeat, weekday, monthday, t[: m.start()] + " " + t[m.end() :]
    return "none", None, None, t


def _relative(t: str) -> tuple[timedelta, bool, str] | None:
    """ "in 2 hours", "in half an hour", "in a week" -> (how long from now, counted in days or
    more, the rest of the words)."""
    if m := re.search(r" in (?:half an|a half) hour ", t):
        return timedelta(minutes=30), False, t[: m.start()] + " " + t[m.end() :]
    words = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))  # "a few" before "a"
    m = re.search(r" in (\d+|" + words + r") ?(minute|min|hour|hr|day|week|month)s? ", t)
    if not m:
        return None
    n = int(m.group(1)) if m.group(1).isdigit() else NUMBER_WORDS[m.group(1)]
    rest = t[: m.start()] + " " + t[m.end() :]
    delta = {
        "minute": timedelta(minutes=n),
        "min": timedelta(minutes=n),
        "hour": timedelta(hours=n),
        "hr": timedelta(hours=n),
        "day": timedelta(days=n),
        "week": timedelta(weeks=n),
        "month": timedelta(days=30 * n),
    }[m.group(2)]
    return delta, m.group(2) in ("day", "week", "month"), rest


def _day(t: str, now: datetime) -> tuple[date | None, str]:
    today = now.date()
    rules: list[tuple[str, object]] = [
        (r" (?:the )?day after tomorrow ", lambda m: today + timedelta(days=2)),
        (r" tomorrow | tmrw | tomorow ", lambda m: today + timedelta(days=1)),
        (r" today | this (?=morning|afternoon|evening)", lambda m: today),
        (r" (?=tonight )", lambda m: today),
        (r" next week ", lambda m: _coming(today, 0)),
        (r" (?:this |the )?weekend ", lambda m: _coming(today, 5, include_today=True)),
        (r" (\d{4})-(\d{2})-(\d{2}) ", lambda m: _date(int(m[1]), int(m[2]), int(m[3]))),
        (rf" (?:on )?(?:the )?{_ORD} (?:of )?({_MONTH}){_YEAR} ", lambda m: _dated(today, int(m[1]), m[2], m[3])),
        (rf" (?:on )?({_MONTH}) (?:the )?{_ORD}{_YEAR} ", lambda m: _dated(today, int(m[2]), m[1], m[3])),
        (rf" (?:on )?(?:next |this |coming )?({_DAY}) ", lambda m: _coming(today, DAYS[m[1]])),
        (r" (?:on )?the (\d{1,2})(?:st|nd|rd|th) ", lambda m: _month_day(today, int(m[1]))),
    ]
    for pattern, pick in rules:
        if m := re.search(pattern, t):
            day = pick(m)  # type: ignore[operator]
            if day is not None:
                return day, t[: m.start()] + " " + t[m.end() :]
    return None, t


def _time(t: str) -> tuple[tuple[int, int] | None, str | None, str]:
    """-> ((hour, minute) or None, part of day or None, rest)."""
    part = next((p for p in PARTS if re.search(rf"\b{p}\b", t)), None)
    if re.search(r"\b(?:noon|midday)\b", t):
        return (12, 0), part, t
    if re.search(r"\bmidnight\b", t):
        return (23, 59), part, t
    if m := re.search(r"\b(\d{1,2})(?:[:.](\d{2}))? ?(a\.?m\.?|p\.?m\.?)(?=\s)", t):
        hour, minute, pm = int(m[1]) % 12, int(m[2] or 0), m[3].startswith("p")
        return _ok(hour + 12 * pm, minute), part, t
    if m := re.search(r"\b(\d{1,2})[:.](\d{2})\b", t):
        return _ok(_guess_hour(int(m[1]), part), int(m[2])), part, t
    if m := re.search(r"\bat (\d{1,2})(?: o'?clock)?\b|\b(\d{1,2}) o'?clock\b", t):
        return _ok(_guess_hour(int(m[1] or m[2]), part), 0), part, t
    return None, part, t


def _guess_hour(hour: int, part: str | None) -> int:
    """An hour said without am/pm: 1-7 is afternoon or evening, unless it is "in the morning"."""
    if part == "morning" or hour == 0 or hour >= 13:
        return hour
    return hour + 12 if 1 <= hour <= 7 else hour


def _ok(hour: int, minute: int) -> tuple[int, int] | None:
    return (hour, minute) if 0 <= hour <= 23 and 0 <= minute <= 59 else None


def _coming(today: date, weekday: int, include_today: bool = False) -> date:
    ahead = (weekday - today.weekday()) % 7
    return today + timedelta(days=ahead or (0 if include_today else 7))


def _month_day(today: date, day: int) -> date | None:
    """The coming "15th": this month if it is still ahead (or today), otherwise next month."""
    if not 1 <= day <= 31:
        return None
    year, month = today.year, today.month
    for _ in range(13):
        if day <= calendar.monthrange(year, month)[1] and date(year, month, day) >= today:
            return date(year, month, day)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return None


def _dated(today: date, day: int, month_name: str, year: str | None) -> date | None:
    month = MONTHS[month_name]
    if year:
        return _date(int(year), month, day)
    d = _date(today.year, month, day)
    if d is not None and d < today:
        d = _date(today.year + 1, month, day)
    return d


def _date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None
