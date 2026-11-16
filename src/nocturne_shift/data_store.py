import sys
from gi.repository import Gio, GLib
from typing import TypedDict, get_type_hints

default_config_file = ".var/night-shift/data.json"


# The schemas nocturne-shift stores its data in, in order of preference:
# the Night Shift GNOME extension's, then nocturne-shift's own (for use
# without the extension). Looked up by ID, never by which file comes first,
# so a folder holding other apps' schemas too can't be mistaken for one.
SCHEMA_IDS = (
    "org.gnome.shell.extensions.night-shift",
    "com.github.christophermca.night-shift",
)


def _find_schema(schema_path, schema_ids=SCHEMA_IDS) -> Gio.SettingsSchema:
    """The first of `schema_ids` compiled in `schema_path`, else installed
    system-wide (e.g. /usr/share/glib-2.0/schemas). Raises LookupError."""
    try:
        source = Gio.SettingsSchemaSource.new_from_directory(
            str(schema_path), Gio.SettingsSchemaSource.get_default(), False
        )
    except GLib.Error as e:
        raise LookupError(
            f"no compiled schemas in {schema_path} ({e.message})"
        )

    # The folder itself first (recursive=False), then system-wide schemas
    for recursive in (False, True):
        for schema_id in schema_ids:
            schema = source.lookup(schema_id, recursive)
            if schema is not None:
                return schema
    raise LookupError(f"no Night Shift schema in {schema_path}")


class TypedStore(TypedDict):
    day_or_night: str
    last_known_coordinates: tuple[float, float]
    static_latitude: str
    static_longitude: str
    timestamp: str
    times: tuple[str, str]
    tzid: str
    use_geoclue: bool


class DataStore:

    def __init__(self, schema_path: str):
        self.data: GObject | TypedStore | None = None
        self.schema_path = schema_path

        self.schema: Gio.SettingsSchema | None = None

        try:
            self.schema = _find_schema(self.schema_path)
            self.data = Gio.Settings.new_full(self.schema, None, None)

        except Exception as e:
            print(
                f"nocturne-shift: settings unavailable, nothing will be saved ({e})",
                file=sys.stderr,
            )
            self.data = None

    def get_keys(self) -> list[str]:
        if self.schema is None:
            return []
        else:
            return sorted(self.schema.list_keys())

    def get(self, key: str):
        if self.data is None:
            return None

        annotations = get_type_hints(TypedStore)

        norm_key = key.replace("-", "_")
        value = annotations.get(norm_key)()

        match value:
            case bool():
                value = self.data[key]
                return value
            case str():
                value = self.data[key]
                return value
            case int():
                value = self.data[key]
                return value
            case _:
                value = self.data[key]
                return value

    def set(self, key: str, value):
        if self.data is None:
            raise AttributeError("`data` is None")
            return None

        match value:
            case bool():  # bool must go before int: bool is a subclass of int
                self.data.set_boolean(key, value)
            case str():
                self.data.set_string(key, value)
            case int():
                self.data.set_int(key, value)
            case GLib.Variant():  # tuples like "times" (ss) and coords (dd)
                self.data.set_value(key, value)
            case _:
                raise TypeError(
                    f"can't save {key}: unsupported type {type(value).__name__}"
                )

    @property
    def available(self) -> bool:
        return self.data is not None
