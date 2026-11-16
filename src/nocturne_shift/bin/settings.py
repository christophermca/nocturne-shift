import os
from pathlib import Path
from gi.repository import Gio
from ..data_store import DataStore

EXTENSION_UUID = "night-shift@christophermca.github.io"

DEFAULT_SCHEMA_PATH = os.path.expanduser(
    Path.home()
    / ".local"
    / "share"
    / "gnome-shell"
    / "extensions"
    / EXTENSION_UUID
    / "schemas"
)


class Settings:
    """Wraps the extension's Gio.Settings.

    `Settings()` returns the Gio.Settings object, or None when the schema
    isn't installed (for example the GNOME extension is missing). Callers
    must handle None; nocturne-shift keeps working, it just can't save.
    """

    def __init__(self, data_store: DataStore | None = None):

        self.data_store = (
            data_store
            if data_store is not None
            else DataStore(DEFAULT_SCHEMA_PATH)
        )

    @property
    def data(self):
        return self.data_store.data

    @property
    def available(self) -> bool:
        return self.data_store.available

    @property
    def get_keys(self) -> list[str]:
        return self.data_store.get_keys()

    def get(self, key: str):
        try:
            return self.data_store.get(key)

        except AttributeError as e:
            print(f"Error: Failed to GET key:`{key}`")

    def set(self, key, value):
        self.data_store.set(key, value)
