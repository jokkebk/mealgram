from __future__ import annotations
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HELSINKI = ZoneInfo("Europe/Helsinki")

_WEEKDAYS = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "weds": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}

_CMD_RE = re.compile(
    r"""^/time\s+
        (?:(?P<dateword>[A-Za-z]+)\s+)?    # optional: today|yesterday|weekday
        (?P<hour>\d{1,2})\s*(?P<ampm>[AaPp][Mm])$
    """,
    re.VERBOSE,
)

class TimeCommandError(ValueError): pass

def handle_time_command(cmd: str, user_tz: str | ZoneInfo = "Europe/Helsinki"):
    """
    Parse '/time [dateword] <hour am/pm>' and return a timezone-aware datetime
    converted to Europe/Helsinki, plus a short confirmation string.

    dateword: optional one word in {'today','yesterday'} or weekday name (Mon..Sun)
              Weekdays resolve to the most recent occurrence (within past 6 days).
    Time is rounded to the hour (e.g., '6 pm').
    """
    m = _CMD_RE.match(cmd.strip())
    if not m:
        raise TimeCommandError("Format: /time [today|yesterday|weekday] <H am/pm> (e.g., '/time yesterday 6 pm').")

    dw = (m.group("dateword") or "today").lower()
    hour = int(m.group("hour"))
    ampm = m.group("ampm").lower()

    if hour < 1 or hour > 12:
        raise TimeCommandError("Hour must be 1–12.")

    # Resolve user's timezone "today"
    utz = ZoneInfo(user_tz) if isinstance(user_tz, str) else user_tz
    now_user = datetime.now(utz)
    today_user = now_user.date()

    # Determine target date
    if dw in ("today",):
        target_date = today_user
    elif dw in ("yesterday",):
        target_date = today_user - timedelta(days=1)
    else:
        if dw not in _WEEKDAYS:
            raise TimeCommandError("Unknown date word. Use today, yesterday, or a weekday (Mon..Sun).")
        target_wd = _WEEKDAYS[dw]
        delta = (now_user.weekday() - target_wd) % 7
        # Prefer the most recent occurrence; if it's 0, that's today.
        if delta > 6:
            raise TimeCommandError("Weekday must refer to the past 6 days.")
        target_date = today_user - timedelta(days=delta)

    # Convert 12h to 24h
    hr24 = (hour % 12) + (12 if ampm == "pm" else 0)

    # Build datetime in user's timezone
    user_dt = datetime(target_date.year, target_date.month, target_date.day, hr24, 0, 0, tzinfo=utz)

    # Convert to Helsinki time
    helsinki_dt = user_dt.astimezone(HELSINKI)

    # Safety: only allow past 6 days (including today)
    if (now_user - user_dt) > timedelta(days=6, hours=23, minutes=59) or user_dt > now_user + timedelta(seconds=59):
        raise TimeCommandError("Time must be within the past 6 days and not in the future.")

    # Compact confirmation
    conf = helsinki_dt.strftime("Set to Helsinki time: %a %Y-%m-%d %I %p (UTC%z)")
    return helsinki_dt, conf

# --- examples ---
if __name__ == "__main__":
    for s in [
        "/time yesterday 6 pm",
        "/time wed 8 am",
        "/time today 10 pm",
        "/time monday 7 am",
    ]:
        try:
            dt, msg = handle_time_command(s, user_tz="Europe/Helsinki")
            print(s, "->", msg, "| ISO:", dt.isoformat())
        except TimeCommandError as e:
            print(s, "-> error:", e)