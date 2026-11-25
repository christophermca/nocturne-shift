from unittest.mock import create_autospec, patch

import re
import pytest

from nocturne_shift.bin.settings import DEFAULT_SCHEMA_PATH, Settings
from nocturne_shift.data_store import DataStore


@pytest.fixture
def store():
    """A DataStore-shaped fake: calling a method DataStore lacks raises."""
    return create_autospec(DataStore, instance=True)


def test_uses_the_data_store_it_is_given(store):
    assert Settings(store).data_store is store


def test_builds_a_default_data_store_when_none_is_given():
    with patch("nocturne_shift.bin.settings.DataStore") as data_store_class:
        settings = Settings()

    data_store_class.assert_called_once_with(DEFAULT_SCHEMA_PATH)
    assert settings.data_store is data_store_class.return_value


def test_default_schema_path_is_the_extension_schemas_dir():
    assert DEFAULT_SCHEMA_PATH.endswith(
        "gnome-shell/extensions/night-shift@christophermca.github.io/schemas"
    )


def test_get_reads_from_the_data_store(store):
    store.get.return_value = ("06:52", "18:51")

    assert Settings(store).get("times") == ("06:52", "18:51")
    store.get.assert_called_once_with("times")


def test_set_writes_to_the_data_store(store):
    Settings(store).set("tzid", "America/New_York")

    store.set.assert_called_once_with("tzid", "America/New_York")


def test_get_keys_from_data_store(store):
    store.get_keys.return_value = ["times", "tzid"]

    assert Settings(store).get_keys == ["times", "tzid"]

    store.get_keys.assert_called_once()


def test_get_keys_is_empty_without_a_schema(tmp_path, capsys):
    assert DataStore(str(tmp_path)).get_keys() == []


@pytest.mark.parametrize("available", [True, False])
def test_available_reflects_the_data_store(store, available):
    store.available = available

    assert Settings(store).available is available


def test_missing_schema_means_unavailable(tmp_path, caplog):
    # Real DataStore and real Gio: an empty directory has no compiled schema,
    # which is exactly a machine without the GNOME extension installed.
    settings = Settings(DataStore(str(tmp_path)))

    assert settings.available is False
    assert "settings unavailable" in caplog.text
