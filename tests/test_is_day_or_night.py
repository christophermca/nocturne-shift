import datetime
import time
import pytest

from freezegun import freeze_time
from unittest.mock import patch, MagicMock, create_autospec
from nocturne_shift.bin.settings import Settings
from nocturne_shift.bin.is_day_or_night import is_day_or_night

# The API returns ISO date-times in the location's time zone.
# 2026-09-25 is in daylight saving time, so New York is UTC-4.
DATE = "2026-09-25"
OFFSET = "-04:00"
TIMES = (f"{DATE}T07:00:00{OFFSET}", f"{DATE}T20:00:00{OFFSET}")


@pytest.fixture(autouse=True)
def computer_in_new_york(monkeypatch):
    """Put the computer in New York, whatever machine runs the tests.

    is_day_or_night converts the saved times with .astimezone(), which uses
    the system time zone (TZ), not freezegun's tz_offset.
    """
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def at(local_time, date=DATE):
    """Freeze the clock at `local_time` New York time.

    tz_offset makes datetime.now() return New York time as well.
    """
    return freeze_time(f"{date}T{local_time}:00{OFFSET}", tz_offset=-4)


@pytest.fixture(autouse=True)
def settings_class():
    """main() builds one Settings per run; fake it so no test touches GSettings."""
    with patch("nocturne_shift.cli.Settings") as settings_class:
        yield settings_class


def test_is_day_or_night_during_day(settings_class):
    """Test detection of daytime"""
    with at("12:00"):
        assert is_day_or_night(TIMES, settings_class) == "day"


def test_is_day_or_night_before_sunrise(settings_class):
    """Test detection night before sunrise"""
    with at("06:59"):
        assert is_day_or_night(TIMES, settings_class) == "night"


def test_is_day_or_night_at_sunrise(settings_class):
    """Test detection transition at sunrise"""
    with at("07:00"):
        assert is_day_or_night(TIMES, settings_class) == "day"


def test_is_day_or_night_before_sunset(settings_class):
    """Test detection of daytime before sunset"""
    with at("19:48"):
        assert is_day_or_night(TIMES, settings_class) == "day"


def test_is_day_or_night_at_sunset(settings_class):
    """Test detection of transition at sunset"""
    with at("20:00"):
        assert is_day_or_night(TIMES, settings_class) == "night"


def test_is_day_or_night_during_night(settings_class):
    """Test detection of nighttime"""
    with at("20:01"):
        assert is_day_or_night(TIMES, settings_class) == "night"


@pytest.mark.parametrize(
    "now, expected", [("05:59", "night"), ("12:00", "day"), ("18:30", "night")]
)
def test_given_times_are_used_instead_of_saved_ones(now, expected):
    times = (f"{DATE}T07:00:00{OFFSET}", f"{DATE}T18:00:00{OFFSET}")
    with at(now):
        assert datetime.datetime.now().strftime("%H:%M") == now
        assert is_day_or_night(times, None) == expected


def test_given_times_work_without_settings():
    with at("21:00"):
        assert is_day_or_night(TIMES, None) == "night"


def test_uses_the_settings_it_is_given_in_day():
    settings = create_autospec(Settings, instance=True)
    settings.get.return_value = TIMES
    with at("14:00"):
        assert is_day_or_night(None, settings) == "day"


def test_uses_the_settings_it_is_given_at_night():
    settings = create_autospec(Settings, instance=True)
    settings.get.return_value = TIMES
    with at("21:00"):
        assert is_day_or_night(None, settings) == "night"


def test_when_time_and_settings_are_None():
    with pytest.raises(AttributeError):
        is_day_or_night(None, None)


def test_times_from_an_earlier_day_still_work():
    """The times are saved by the last fetch, which may have been yesterday."""
    with at("12:00", date="2026-09-26"):
        assert is_day_or_night(TIMES, None) == "day"


def test_times_in_another_time_zone_are_converted_to_local():
    """11:00/23:59 UTC is 07:00/19:59 New York: day at 12:00, night at 06:30."""
    times_in_utc = (f"{DATE}T11:00:00+00:00", f"{DATE}T23:59:00+00:00")
    with at("12:00"):
        assert is_day_or_night(times_in_utc, None) == "day"
    with at("06:30"):
        assert is_day_or_night(times_in_utc, None) == "night"


def test_times_that_are_not_iso_are_skipped(capsys):
    """The schema default before the first fetch is ("sunrise", "sunset")."""
    help_message = "run nocturne-shift -w"
    settings = create_autospec(Settings, instance=True)
    with at("12:00"):
        assert is_day_or_night(("sunrise", "sunset"), settings) is None
    settings.set.assert_not_called()
    assert help_message in capsys.readouterr().err


@pytest.mark.parametrize(
    "now, expected",
    [
        ("12:00", "night"),
        ("14:00", "day"),
        ("23:00", "day"),
        ("01:00", "day"),
        ("02:00", "night"),
    ],
)
def test_day_that_spans_midnight_in_local_time(now, expected):
    """Los Angeles times on a computer whose clock is set to UTC.

    06:52-18:51 Los Angeles (UTC-7) is 13:52-01:51 UTC, so the day wraps
    past midnight in the computer's time zone.
    """
    times = (f"{DATE}T06:52:00-07:00", f"{DATE}T18:51:00-07:00")
    with patch.dict("os.environ", {"TZ": "UTC"}):
        time.tzset()
        with freeze_time(f"{DATE}T{now}:00+00:00"):
            assert is_day_or_night(times, None) == expected
    time.tzset()
