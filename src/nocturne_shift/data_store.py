import sys
import subprocess
from pathlib import Path
from gi.repository import Gio, GLib
from typing import TypedDict, get_type_hints

default_config_file = ".var/night-shift/data.json"


def _compile_schema(schema_path, schema_id) -> Gio.SettingsSchema | None:
    try:
        schema_source = Gio.SettingsSchemaSource.new_from_directory(
            schema_path, Gio.SettingsSchemaSource.get_default(), False
        )
        schema = schema_source.lookup(schema_id, True)
        if schema is None:
            raise LookupError(f"schema {schema_id} not found")

        return schema

    except Exception as e:
        print(
            f"nocturne-shift: settings unavailable, nothing will be saved ({e})",
            file=sys.stderr,
        )


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
            schema_xml = next(
                Path(self.schema_path).glob("*.gschema.xml"), None
            )
            if schema_xml is None:
                raise LookupError(f"no .gschema.xml in {self.schema_path}")
            package_id = schema_xml.name.removesuffix(".gschema.xml")
            self.schema = _compile_schema(
                self.schema_path, schema_id=package_id
            )

            if self.schema is not None:
                self.data = Gio.Settings.new_full(self.schema, None, None)
            else:
                self.data = None

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
