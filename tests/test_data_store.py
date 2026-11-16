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
SUNRISE_TIME = "2026-09-25T06:52:10-04:00"
SUNSET_TIME = "2026-09-25T18:51:30-04:00"


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
            GLib.Variant("(ss)", (SUNRISE_TIME, SUNSET_TIME)),
            (SUNRISE_TIME, SUNSET_TIME),
        ),
        (
            "last-known-coordinates",
            GLib.Variant("(dd)", (40.7, -74.0)),
            (40.7, -74.0),
        ),
        ("tzid", "America/New_York", "America/New_York"),
        ("use-geoclue", False, False),  # default is true, so save False
    ],
    # `ids` name the type of each value above
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
        store.set("times", [SUNRISE_TIME, SUNSET_TIME])


@patch("nocturne_shift.bin.get_sunrise_sunset.requests.get")
def test_fetched_times_are_saved_through_settings(mock_get, store, capsys):
    """The -w path end to end: fetch -> _save -> Settings -> DataStore."""
    response = MagicMock()
    response.json.return_value = {
        "sunrise": SUNRISE_TIME,
        "sunset": SUNSET_TIME,
        "tzid": "America/New_York",
    }
    mock_get.return_value = response
    fetcher = GetTimeOfSunriseSunset(settings=Settings(store))

    fetcher._get_sunrise_sunset(40.7, -74.0, False)

    assert "ERROR SAVING" not in capsys.readouterr().err
    assert store.data["times"] == (SUNRISE_TIME, SUNSET_TIME)
    assert store.data["tzid"] == "America/New_York"


def test_schema_id_picks_which_schema_to_load(tmp_path):
    shutil.copy(SCHEMA_XML, tmp_path)
    subprocess.run(["glib-compile-schemas", str(tmp_path)], check=True)
    package_id = SCHEMA_XML.name.removesuffix(".gschema.xml")

    store = DataStore(str(tmp_path))

    assert store.schema.get_id() == package_id


def test_folder_without_schemas_says_why(tmp_path, capsys):
    store = DataStore(str(tmp_path))

    assert store.available is False
    assert f"no compiled schemas in {tmp_path}" in capsys.readouterr().err


# DataStore finds the schema by ID, not by which .gschema.xml comes first, so a
# folder that also holds other apps' schemas can't be mistaken for it.
EXTENSION_XML = """<schemalist>
  <schema id="org.gnome.shell.extensions.night-shift"
          path="/org/gnome/shell/extensions/night-shift/">
    <key name="timestamp" type="s"><default>""</default></key>
  </schema>
</schemalist>"""

# Sorts before both Night Shift schemas, so "the first file" would pick it
OTHER_APP_XML = """<schemalist>
  <schema id="com.example.aaa" path="/com/example/aaa/">
    <key name="timestamp" type="s"><default>""</default></key>
  </schema>
</schemalist>"""


def compiled_folder(folder, **schemas):
    """Write {file stem: XML} into `folder` and compile them."""
    if shutil.which("glib-compile-schemas") is None:
        pytest.skip("glib-compile-schemas is not installed")
    folder.mkdir(parents=True, exist_ok=True)
    for stem, xml in schemas.items():
        (folder / f"{stem}.gschema.xml").write_text(xml)
    subprocess.run(["glib-compile-schemas", str(folder)], check=True)
    return str(folder)


def test_a_shared_folder_uses_the_night_shift_schema(tmp_path):
    folder = compiled_folder(
        tmp_path / "shared",
        **{"com.example.aaa": OTHER_APP_XML},
        **{"org.gnome.shell.extensions.night-shift": EXTENSION_XML},
    )

    store = DataStore(folder)

    assert store.schema.get_id() == "org.gnome.shell.extensions.night-shift"


def test_a_folder_with_only_another_apps_schema_is_unavailable(
    tmp_path, capsys
):
    folder = compiled_folder(
        tmp_path / "other", **{"com.example.aaa": OTHER_APP_XML}
    )

    store = DataStore(folder)

    assert store.available is False
    assert f"no Night Shift schema in {folder}" in capsys.readouterr().err


def test_the_extension_schema_is_preferred_over_nocturne_shifts_own(tmp_path):
    folder = compiled_folder(
        tmp_path / "both",
        **{"com.github.christophermca.night-shift": SCHEMA_XML.read_text()},
        **{"org.gnome.shell.extensions.night-shift": EXTENSION_XML},
    )

    store = DataStore(folder)

    assert store.schema.get_id() == "org.gnome.shell.extensions.night-shift"
