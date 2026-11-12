import re
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from gi.repository import Gio, GLib

import nocturne_shift
from nocturne_shift import data_store
from nocturne_shift.data_store import DataStore
from nocturne_shift.bin.get_sunrise_sunset import GetTimeOfSunriseSunset
from nocturne_shift.bin.settings import Settings

SCHEMA_XML = next(
    (Path(nocturne_shift.__file__).parent / "schemas").glob("*.gschema.xml")
)


@pytest.fixture
def store(tmp_path):
    """A DataStore backed by a real Gio.Settings built from the package schema.

    The schema is compiled into tmp_path as is (DataStore finds its id), and
    the settings live in GLib's in-memory backend, so nothing touches dconf.
    """
    if shutil.which("glib-compile-schemas") is None:
        pytest.skip("glib-compile-schemas is not installed")

    shutil.copy(SCHEMA_XML, tmp_path)
    subprocess.run(["glib-compile-schemas", str(tmp_path)], check=True)

    store = DataStore(str(tmp_path))
    store.data = Gio.Settings.new_full(
        store.schema, Gio.memory_settings_backend_new(), None
    )
    return store


@pytest.mark.parametrize(
    "key, value, expected",
    [
        (
            "times",
            GLib.Variant("(ss)", ("06:52", "18:51")),
            ("06:52", "18:51"),
        ),
        (
            "last-known-coordinates",
            GLib.Variant("(dd)", (40.7, -74.0)),
            (40.7, -74.0),
        ),
        ("tzid", "America/New_York", "America/New_York"),
        ("use-geoclue", False, False),  # default is true, so save False
    ],
    # ids follows the aboves return types
    ids=["variant-ss", "variant-dd", "string", "bool"],
)
def test_set_saves_each_type(store, key, value, expected):
    store.set(key, value)

    assert store.data[key] == expected


def test_get_keys_lists_every_key_in_the_schema(store):
    xml_keys = re.findall(r'<key name="([^"]+)"', SCHEMA_XML.read_text())

    assert store.get_keys() == sorted(xml_keys)


def test_set_rejects_unsupported_types(store):
    with pytest.raises(TypeError, match="can't save times: unsupported type"):
        store.set("times", ["06:52", "18:51"])


@patch("nocturne_shift.bin.get_sunrise_sunset.requests.get")
def test_fetched_times_are_saved_through_settings(mock_get, store, capsys):
    """The -w path end to end: fetch -> _save -> Settings -> DataStore."""
    response = MagicMock()
    response.json.return_value = {
        "sunrise": "2026-09-25T06:52:10-04:00",
        "sunset": "2026-09-25T18:51:30-04:00",
        "tzid": "America/New_York",
    }
    mock_get.return_value = response
    fetcher = GetTimeOfSunriseSunset(settings=Settings(store))

    fetcher._get_sunrise_sunset(40.7, -74.0, False)

    assert "ERROR SAVING" not in capsys.readouterr().err
    assert store.data["times"] == ("06:52", "18:51")
    assert store.data["tzid"] == "America/New_York"


def test_schema_id_picks_which_schema_to_load(tmp_path):
    shutil.copy(SCHEMA_XML, tmp_path)
    subprocess.run(["glib-compile-schemas", str(tmp_path)], check=True)
    package_id = SCHEMA_XML.name.removesuffix(".gschema.xml")

    store = DataStore(str(tmp_path))

    assert store.schema.get_id() == package_id


def test_folder_without_schema_xml_says_why(tmp_path, capsys):
    store = DataStore(str(tmp_path))

    assert store.available is False
    assert f"no .gschema.xml in {tmp_path}" in capsys.readouterr().err
