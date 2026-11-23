import sys
import time
import io
import re
import pytest
from unittest.mock import Mock, patch, MagicMock, create_autospec
import subprocess
import requests
from gi.repository import Gio, GLib
from nocturne_shift.bin.settings import Settings
from nocturne_shift.bin.get_sunrise_sunset import (
    GetTimeOfSunriseSunset,
    AccuracyLevel,
)

REAL_POPEN = subprocess.Popen
AGENT_CMD = ["/usr/lib/geoclue-2.0/demos/agent"]
WHERE_AM_I_CMD = [
    "/usr/lib/geoclue-2.0/demos/where-am-i",
    f"--accuracy-level={AccuracyLevel.STREET.value}",  # street level
    "--time-threshold=3",
]

# What geoclue's where-am-i actually prints (note the trailing degree signs).
WHERE_AM_I_OUTPUT = """\
Client object: /org/freedesktop/GeoClue2/Client/1
New location:
Latitude:    40.712800°
Longitude:   -74.006000°
Accuracy:    50.000000 meters
Timestamp:   Mon 13 Oct 2026 09:00:00 AM EDT (1791896400 seconds since the Epoch)
"""


def fake_process(output=""):
    """A Popen-shaped fake. Real Popen sets .stdout in __init__, so autospec
    can't see it; give it a real text stream that returns "" at EOF."""
    proc = create_autospec(REAL_POPEN, instance=True)
    proc.stdout = io.StringIO(output)
    return proc


@pytest.fixture
def popen():
    with patch(
        "nocturne_shift.bin.get_sunrise_sunset.subprocess.Popen"
    ) as popen:
        yield popen


@pytest.fixture
def fake_settings():
    """A fake Settings backed by a dict: get() reads it, set() writes to it."""
    store = {
        "times": ("", ""),
        "use-geoclue": False,
        "static-latitude": "40.7128",
        "static-longitude": "-74.0060",
    }
    mock_settings = create_autospec(Settings, instance=True)
    mock_settings.get.side_effect = store.get
    mock_settings.set.side_effect = store.__setitem__
    print("mock_store_defaults: ", store)
    mock_settings.data_store = store  # so tests can check what was saved

    return mock_settings


@pytest.fixture
def fetcher(fake_settings):
    # With no settings, __init__ finds no static location and fetches nothing.
    fetcher = GetTimeOfSunriseSunset()
    fetcher.settings = fake_settings
    return fetcher


def _mock_response(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


SUNRISE_TIME = "2026-09-25T06:52:10-04:00"
SUNSET_TIME = "2026-09-25T18:51:30-04:00"

API_PAYLOAD = {
    "sunrise": SUNRISE_TIME,
    "sunset": SUNSET_TIME,
    "tzid": "America/New_York",
}


@patch(
    "nocturne_shift.bin.get_sunrise_sunset.GetTimeOfSunriseSunset._get_location"
)
@patch("nocturne_shift.bin.get_sunrise_sunset.requests.get")
class TestGetSunriseSunset:
    settings = None

    def test_when_geoclue_is_True_and_settings_is_None(
        self, requests, mock_get_location
    ):
        use_geoclue = True
        override = False
        verbose = 0
        lat = 22.0
        lng = -84.0

        requests.return_value = _mock_response(API_PAYLOAD)
        mock_get_location.return_value = (40.7128, -74.0060)  # NYC coordinates
        object = GetTimeOfSunriseSunset(
            verbose=verbose,
            override=override,
            use_geoclue=use_geoclue,
            settings=self.settings,
        )

        assert object.use_geoclue == True
        assert object.times == (SUNRISE_TIME, SUNSET_TIME)

    def test_when_geoclue_is_False_and_settings_is_None(
        self, requests, mock_get_location
    ):
        use_geoclue = False
        override = False
        verbose = 0
        lat = 40.7128
        lng = -74.0060

        requests.return_value = _mock_response(API_PAYLOAD)
        mock_get_location.return_value = (lat, lng)  # NYC coordinates
        object = GetTimeOfSunriseSunset(
            verbose=verbose,
            override=override,
            use_geoclue=use_geoclue,
            settings=self.settings,
        )

        assert object.use_geoclue == False
        assert object.times == None

    def test_when_geoclue_is_None_and_settings_is_None(
        self, requests, mock_get_location
    ):
        use_geoclue = None
        override = False
        verbose = 0
        lat = 40.7128
        lng = -74.0060

        requests.return_value = _mock_response(API_PAYLOAD)
        mock_get_location.return_value = (lat, lng)  # NYC coordinates
        object = GetTimeOfSunriseSunset(
            verbose=verbose,
            override=override,
            use_geoclue=use_geoclue,
            settings=self.settings,
        )

        assert object.use_geoclue == None
        assert object.times == None

    def test_calling_function(self, requests, mock_get_location):
        use_geoclue = None
        override = False
        verbose = 0
        lat = 40.7128
        lng = -74.0060

        requests.return_value = _mock_response(API_PAYLOAD)
        # mock_get_location.return_value = (lat, lng)  # NYC coordinates
        sunrise_sunset = GetTimeOfSunriseSunset(
            verbose=verbose,
            override=override,
            use_geoclue=use_geoclue,
            settings=self.settings,
        )

        sunrise_sunset([lat, lng])


class TestGetSunriseSunsetGetLocation:
    def _run(self, fetcher, popen, output=WHERE_AM_I_OUTPUT):
        agent, where_am_i = fake_process(), fake_process(output)
        popen.side_effect = [
            agent,
            where_am_i,
        ]  # 1st Popen() = agent, 2nd = where-am-i

        return fetcher._get_location(), agent, where_am_i

    def test_starts_the_agent_then_where_am_i(self, fetcher, popen):
        self._run(fetcher, popen)

        assert [c.args[0] for c in popen.call_args_list] == [
            AGENT_CMD,
            WHERE_AM_I_CMD,
        ]

    def test_where_am_i_that_never_answers_times_out(
        self, fetcher, popen, caplog
    ):
        # a real child process that prints nothing, like geoclue stuck
        # waiting for a location
        silent = REAL_POPEN(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            text=True,
            stdout=subprocess.PIPE,
        )
        popen.side_effect = [fake_process(), silent]

        with patch(
            "nocturne_shift.bin.get_sunrise_sunset.GEOCLUE_TIMEOUT", 0.5
        ):
            started = time.monotonic()
            assert fetcher._get_location() is None
            assert time.monotonic() - started < 5  # not the full 60 s

        assert silent.poll() is not None  # killed and reaped
        assert "no location within 0.5 seconds" in caplog.text

    def test_where_am_i_that_answers_is_not_timed_out(self, fetcher, popen):
        coords, _, where_am_i = self._run(fetcher, popen)

        assert coords == (40.7128, -74.006)
        where_am_i.kill.assert_called()  # stopped once it has answered
        where_am_i.wait.assert_called()


@patch(
    "nocturne_shift.bin.get_sunrise_sunset.GetTimeOfSunriseSunset._get_location"
)
@patch("nocturne_shift.bin.get_sunrise_sunset.requests.get")
class TestSettingsIsSet:

    def test_when_geoclue_is_None_and_settings_is_set(
        self, requests, mock_get_location, fake_settings
    ):
        use_geoclue = None
        override = False
        verbose = 0

        requests.return_value = _mock_response(API_PAYLOAD)

        object = GetTimeOfSunriseSunset(
            verbose=verbose,
            override=override,
            use_geoclue=use_geoclue,
            settings=fake_settings,
        )

        print("myobject", object.times)
        assert object.use_geoclue is False

        # fetched the times and saved them back to settings
        assert fake_settings.data_store["times"] == GLib.Variant(
            "(ss)", (SUNRISE_TIME, SUNSET_TIME)
        )
        assert fake_settings.data_store["tzid"] == "America/New_York"


# The request URL carries the coordinates; error output must not, since
# under systemd it goes to the journal.
URL_WITH_COORDS = (
    "https://api.sunrise-sunset.org/v2?lat=40.712776&lng=-74.005974"
)


@patch("nocturne_shift.bin.get_sunrise_sunset.requests.get")
def test_http_errors_report_the_status_not_the_url(mock_get, fetcher, caplog):
    # what raise_for_status() raises: the message names the URL, and
    # .response is attached
    mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError(
        f"500 Server Error: Internal Server Error for url: {URL_WITH_COORDS}",
        response=Mock(status_code=500),
    )

    assert fetcher._get_sunrise_sunset(40.712776, -74.005974, 0) is None

    (record,) = caplog.records
    assert (
        record.getMessage() == "fetching sunrise/sunset times failed: HTTP 500"
    )
    assert record.exc_info is None  # a traceback would include the URL
    assert "40.712776" not in caplog.text and "74.005974" not in caplog.text


@patch("nocturne_shift.bin.get_sunrise_sunset.requests.get")
def test_http_error_without_a_response_is_still_reported(
    mock_get, fetcher, caplog
):
    mock_get.return_value.raise_for_status.side_effect = (
        requests.exceptions.HTTPError("500 Server Error")
    )

    assert fetcher._get_sunrise_sunset(40.7, -74.0, 0) is None
    assert "HTTP no response" in caplog.text


@patch("nocturne_shift.bin.get_sunrise_sunset.requests.get")
def test_other_errors_log_only_their_type(mock_get, fetcher, caplog):
    # e.g. no network: requests' message includes the URL with lat/lng
    mock_get.side_effect = requests.exceptions.ConnectionError(
        f"Max retries exceeded with url: {URL_WITH_COORDS}"
    )

    assert fetcher._get_sunrise_sunset(40.712776, -74.005974, 0) is None
    (record,) = caplog.records
    assert record.getMessage() == (
        "fetching sunrise/sunset times failed: ConnectionError"
    )
    assert record.exc_info is None
    assert "40.712776" not in caplog.text and "74.005974" not in caplog.text


@patch("nocturne_shift.bin.get_sunrise_sunset.requests.get")
def test_request_has_a_timeout(mock_get, fetcher):
    # no timeout lets a hung connection block the oneshot service forever
    mock_get.return_value = _mock_response(API_PAYLOAD)

    fetcher._get_sunrise_sunset(40.7, -74.0, 0)

    assert mock_get.call_args.kwargs["timeout"] == (5, 15)


@patch("nocturne_shift.bin.get_sunrise_sunset.requests.get")
def test_coordinates_are_rounded_before_the_request(mock_get, fetcher):
    # 2 decimals is about 1 km: plenty for sunrise/sunset times, and the
    # third-party API doesn't get your exact location
    mock_get.return_value = _mock_response(API_PAYLOAD)

    fetcher._get_sunrise_sunset(40.712776, -74.005974, 0)

    call = mock_get.call_args
    params = call.kwargs.get(
        "params", call.args[1] if len(call.args) > 1 else None
    )
    assert params == {"lat": 40.71, "lng": -74.01}


@patch("nocturne_shift.bin.get_sunrise_sunset.requests.get")
def test_unexpected_errors_keep_their_traceback(mock_get, fetcher, caplog):
    # not a network problem: a bug in nocturne-shift, so the traceback helps
    mock_get.side_effect = ValueError("bug")

    assert fetcher._get_sunrise_sunset(40.7, -74.0, 0) is None
    (record,) = caplog.records
    assert record.exc_info is not None
    assert "ValueError: bug" in caplog.text


def test_save_without_settings_says_why(caplog):
    fetcher = GetTimeOfSunriseSunset()  # no settings
    caplog.clear()  # drop anything __init__ logged

    fetcher._save(
        {"tzid": "America/New_York", "times": (SUNRISE_TIME, SUNSET_TIME)}
    )

    (record,) = caplog.records
    assert record.getMessage() == (
        "unable to save tzid, times: settings unavailable"
    )
    assert record.exc_info is None  # not inside an except: no traceback


def test_save_errors_are_logged_with_their_traceback(fetcher, caplog, capsys):
    fetcher.settings.set.side_effect = TypeError("can't save tzid")

    fetcher._save({"tzid": "America/New_York"})

    (record,) = caplog.records
    assert record.getMessage() == "saving tzid failed"
    assert "TypeError: can't save tzid" in caplog.text
    assert capsys.readouterr().out == ""  # stdout stays clean for `| cmd`


@patch("nocturne_shift.bin.get_sunrise_sunset.requests.get")
def test_saved_timestamp_is_whole_seconds_with_an_offset(mock_get, fetcher):
    """The GNOME extension reads `timestamp` with JavaScript's Date.parse(),
    which is only specified for this form: no microseconds."""
    mock_get.return_value = _mock_response(API_PAYLOAD)

    fetcher._get_sunrise_sunset(40.7, -74.0, 0)

    timestamp = fetcher.settings.data_store["timestamp"]
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", timestamp
    ), timestamp


def test_accuracy_levels_match_geoclue_and_cannot_change():
    assert [(level.name, level.value) for level in AccuracyLevel] == [
        ("COUNTRY", 1),
        ("CITY", 4),
        ("NEIGHBORHOOD", 5),
        ("STREET", 6),
        ("EXACT", 8),
    ]
    with pytest.raises(AttributeError):
        AccuracyLevel.CITY = 5
