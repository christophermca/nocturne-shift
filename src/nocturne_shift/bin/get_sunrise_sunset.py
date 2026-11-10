#!/usr/bin/python

import re
import gi
import sys
import pprint
import json
import argparse
import subprocess
import requests

from collections import namedtuple
from typing import Any
from .settings import Settings
from datetime import datetime

gi.require_version("Gio", "2.0")
from gi.repository import GLib

NOAA = "https://api.sunrise-sunset.org/v2"
ACCURACY_LEVEL_CITY = 4
TIME_THRESHOLD = 3


class GetTimeOfSunriseSunset:
    def __init__(
        self,
        verbose: int = 0,
        override: bool = False,
        use_geoclue: bool | None = False,
        settings: Settings | None = None,
    ):
        self.override = override
        self.verbose = verbose
        self.use_geoclue = use_geoclue
        self.settings = settings
        self.agent = None
        self.times: tuple[str, str] | None = None

        # Determine Time of sunrise/sunset
        coords: tuple[float, float] | None = self.determine_location()

        if coords:
            self.times = self._get_sunrise_sunset(*coords, self.verbose)

    # pass coords from cli to module
    def __call__(self, coords, verbose=0):
        return self._get_sunrise_sunset(*coords, verbose)

    def determine_location(self) -> tuple[float, float] | None:
        if self.use_geoclue is None and self.settings is not None:
            self.use_geoclue = self.settings.get("use-geoclue")

        # Determine Location
        if self.use_geoclue is True:
            coords = self._get_location()
        else:
            coords = self._get_static_location_from_settings()

        return coords

    def _get_location(self) -> tuple[float, float]:
        try:

            # Get location data from Geoclue
            if self.agent is None:
                self.agent = subprocess.Popen(
                    ["/usr/lib/geoclue-2.0/demos/agent"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            geoclue_data = subprocess.Popen(
                [
                    "/usr/lib/geoclue-2.0/demos/where-am-i",
                    # Popen takes strings only: an int raises TypeError
                    f"--accuracy-level={ACCURACY_LEVEL_CITY}",
                    f"--time-threshold={TIME_THRESHOLD}",
                ],  # `run /usr/lib/geoclue-2.0/demo/where-am-i -h` for more information about options
                text=True,
                stdout=subprocess.PIPE,
            )

            lat_regex = r"^(Lat.*:).*([\.\-\d+]+)"
            lng_regex = r"^(Long.*:).*([\.\-\d+]+)"

            # READS response for LAT and LNG
            Coordinates = namedtuple("Coordinates", ["latitude", "longitude"])
            found_coords: dict[str, float | None] = {
                "lat": None,
                "lng": None,
            }

            for line in iter(geoclue_data.stdout.readline, ""):
                found_lat = re.match(lat_regex, line)
                found_lng = re.match(lng_regex, line)

                if found_lat:
                    matched_string = found_lat.group().split()[1]
                    found_coords["lat"] = float(matched_string)

                if found_lng:
                    matched_string = found_lng.group().split()[1]
                    found_coords["lng"] = float(matched_string)

                # attempt to exit early
                if found_coords["lat"] and found_coords["lng"]:
                    break

            geoclue_data.terminate()
            # raise exception if unable to determine coords
            if found_coords["lat"] is None and found_coords["lng"] is None:
                raise TypeError(
                    "Could not determine location. Please check your geoclue configuration"
                )

            coords = Coordinates(found_coords["lat"], found_coords["lng"])

            previous_coordinates = None
            if self.settings is not None:
                previous_coordinates = self.settings.get(
                    "last-known-coordinates"
                )
                try:
                    previous_coordinates
                except Exception as e:
                    print(f"{e}")

            # CHECK if should save?
            if self.override or (list(coords) != previous_coordinates):
                last_known_coordinates = GLib.Variant("(dd)", coords)
                data: dict = {
                    "last-known-coordinates": last_known_coordinates,
                }
                self._save(data)
            return coords

        except subprocess.TimeoutExpired as e:
            print(f"TimeoutExpired: {e.timeout} seconds\n\n {e.stdout}")
            return None

        except subprocess.CalledProcessError as e:
            print(f"Error: {e.returncode} \n\n {e.stderr}")
            return None

        finally:
            try:
                if self.agent is not None:
                    self.agent.kill()  # Gracefully exits
                    self.agent.wait()  # Prevents zombie processes
                    self.agent = None

            except Exception as e:
                print(f"Error: ___{e}")

    def _get_sunrise_sunset(
        self, lat: float, lng: float, verbose: int
    ) -> tuple[float, float]:
        try:
            params = {"lat": round(lat, 2), "lng": round(lng, 2)}

            # Handle response
            response = requests.get(NOAA, params, timeout=(5, 15))
            response.raise_for_status()

            response_data = response.json()

            if self.verbose > 1:
                json_string = json.dumps(
                    response_data, indent=4, sort_keys=True
                )
                print(f"[nocturne-shift] {json_string}")

            tzid = response_data["tzid"]
            utc_offset = response_data["utc-offset"]
            sunrise = datetime.fromisoformat(
                response_data["sunrise"]
            ).strftime("%H:%M")
            sunset = datetime.fromisoformat(response_data["sunset"]).strftime(
                "%H:%M"
            )

            times = (sunrise, sunset)

            saved: dict[str, Any] = {}

            times_tuple = GLib.Variant("(ss)", times)
            saved = {
                "timestamp": f"{datetime.now().astimezone().isoformat()}",
                "tzid": tzid,
                "times": times_tuple,
                "utc-offset": utc_offset,
            }

            self._save(saved)

            return times

        except requests.exceptions.HTTPError as http_err:
            # Only the status: str(http_err) includes the URL, with lat/lng.
            # getattr: an HTTPError raised without a response has .response None
            status = getattr(http_err.response, "status_code", "no response")
            print(f"HTTP error occurred (e.g., 404, 500): {status}")
        except (
            Exception
        ) as e:  # Generic Exception must go last becuase it will catch any exception
            print(type(e).__name__)

    def _save(self, data) -> None:
        if self.settings is None:
            print(
                f"nocturne-shift: unable to save {', '.join(data)}: settings unavailable",
                file=sys.stderr,
            )
            return

        try:
            # DataStore.set picks the right Gio setter for each type
            for key, value in data.items():
                self.settings.set(key, value)

            if self.verbose > 0:
                pprint.pprint(data)

        except Exception as e:
            print(f"ERROR SAVING: {e}", file=sys.stderr)

    def _get_static_location_from_settings(self) -> tuple[float, float]:

        if self.settings is None:
            print(
                "nocturne-shift: no static location: self.settings unavailable",
                file=sys.stderr,
            )
            return None

        lat = self.settings.get("static-latitude")
        lng = self.settings.get("static-longitude")

        if lat and lng:
            static_location = (float(lat), float(lng))

            last_known_coordinates = GLib.Variant("(dd)", static_location)
            self._save({"last-known-coordinates": last_known_coordinates})

            return static_location

        else:
            print("Missing required keys")
