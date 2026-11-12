#!/usr/bin/python

import sys

from .settings import Settings
from datetime import datetime


def is_day_or_night(
    times: tuple[str, str] | None = None,
    settings: Settings | None = None,
    verbose=0,
):
    """Work out "day" or "night" and save it.

    `times` is a (sunrise, sunset) pair of "HH:MM" strings. When it's not
    given, the times saved in settings are used.

    `settings` is a `Settings`. When it's not given, raise an Error to the caller;
    """

    settings = settings

    if times is None:
        if settings is None:
            raise AttributeError(
                "nocturne-shift: unable to check `day or night`. settings is None"
            )
            return

        times = settings.get("times")

    if not times:
        return
    # Compare times of day in this computer's time zone: the saved ISO times
    # are in the location's time zone, and can be from an earlier day.
    try:
        sunrise, sunset = (
            datetime.fromisoformat(t).astimezone().time() for t in times
        )
    except ValueError:
        # the schema default ("sunrise", "sunset"), or "HH:MM" saved before this change
        print(
            f"nocturne-shift: no usable sunrise/sunset saved ({times}); run nocturne-shift -w",
            file=sys.stderr,
        )
        return None

    current_time = datetime.now().time()

    # Checks if currrent time is after sunrise or sunset
    DAY_NIGHT: str

    if verbose >= 1:
        print(sunrise, current_time, sunset)

    if sunrise <= sunset:
        is_day = sunrise <= current_time < sunset
    else:
        # In this computer's time zone the location's day spans midnight
        # (e.g. Los Angeles on a UTC clock: sunrise 13:52, sunset 01:51)
        is_day = current_time >= sunrise or current_time < sunset

    DAY_NIGHT = "day" if is_day else "night"

    # set day-or-night
    try:
        settings.set("day-or-night", DAY_NIGHT)
    except Exception as e:
        print(
            "nocturne-shift: unable to save day-or-night: settings unavailable",
            file=sys.stderr,
        )

    print(f"{DAY_NIGHT}")
    return DAY_NIGHT
