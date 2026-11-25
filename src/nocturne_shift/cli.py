#!/usr/bin/python
# PYTHON_ARG_COMPLETE_OK
from .bin.get_sunrise_sunset import GetTimeOfSunriseSunset
from .bin.is_day_or_night import is_day_or_night
from .bin.settings import Settings
from .data_store import DataStore

import logging
import sys
import argparse
import argcomplete
import importlib.metadata

PLUGIN_GROUP = "night_shift.commands"
OPTIONAL_COMMANDS = {"services": "gnome-night-shift"}
log = logging.getLogger(__name__)

try:
    __version__ = importlib.metadata.version("nocturne-shift")
except importlib.metadata.PackageNotFoundError:
    __version__ = "unknown"


def load_commands(subparsers) -> dict:
    """Let installed plugins add subcommands; returns {command: handler}.

    A plugin registers in its own pyproject.toml:
        [project.entry-points."night_shift.commands"]
        services = "night_shift_services.cli:register"
    `register(subparsers)` adds its parser and returns `handler(args)`.
    """
    handlers = {}
    for entry_point in importlib.metadata.entry_points(group=PLUGIN_GROUP):
        try:
            handlers[entry_point.name] = entry_point.load()(subparsers)
        except (
            Exception
        ) as e:  # a broken plugin must not take the core CLI down
            log.warning("skipping plugin %r (%s)", entry_point.name, e)

    # Commands whose plugin isn't installed still parse, and say how to get them
    for name, extra in OPTIONAL_COMMANDS.items():
        if name not in handlers:
            stub = subparsers.add_parser(
                name, help=f"(not installed: pip install '{extra}')"
            )
            stub.add_argument(
                "rest", nargs=argparse.REMAINDER
            )  # accept anything
            handlers[name] = _not_installed(name, extra)
    return handlers


def _not_installed(name, extra):
    def handler(args):
        sys.exit(f"nocturne-shift {name} requires: pip install '{extra}'")

    return handler


def check(times=None, settings=None, verbose=0):
    try:
        is_day_or_night(times, settings, verbose)
    except AttributeError:
        log.exception("check() failed")


def run_once(
    verbose: int = 0,
    override: bool = False,
    check_now: bool | str | None = False,
    use_geoclue: bool | None = False,
    settings: Settings | None = None,
):
    try:
        sunrise_sunset = GetTimeOfSunriseSunset(
            verbose, override, use_geoclue, settings
        )
        if check_now != False:
            try:
                check(sunrise_sunset.times, settings, verbose)
            except Exception:
                log.exception("check() failed")
    except Exception:
        log.exception("run_once() failed")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="nocturne-shift: %(levelname)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Get the times for the sunrise/sunset",
        prog="nocturne-shift",
    )

    sub_parsers = parser.add_subparsers(dest="command")
    commands = load_commands(sub_parsers)

    parser.add_argument(
        "--lat",
        dest="latitude",
        type=float,
        nargs="?",
        help="compares current time with sunrise/sunset time",
    )

    parser.add_argument(
        "--lng",
        dest="longitude",
        type=float,
        nargs="?",
        help="compares current time with sunrise/sunset time",
    )

    parser.add_argument(
        "-c",
        "--check-now",
        metavar="SCHEMA_PATH",
        nargs="?",
        default=False,
        help="compares current time with sunrise/sunset time",
    )
    parser.add_argument(
        "-f",
        "--force",
        dest="override",
        action="store_true",
        help="ignores cached data",
    )

    parser.add_argument(
        "-g",
        "--geoclue",
        dest="use_geoclue",
        action="store_true",
        help="use geoclue to determine location",
    )

    parser.add_argument(
        "-w",
        "--watch",
        nargs="?",
        default=False,
        metavar="SCHEMA_PATH",
        help="watch for changes in data_store",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Prints more information",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Prints more information",
    )

    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    # ------------ Plugin Commands
    if args.command in commands:
        return commands[args.command](args)

    # ------------ Watch
    if args.watch != False:
        settings = (
            Settings(DataStore(args.watch)) if args.watch else Settings()
        )

        # TODO validate using run_once will work here.
        return run_once(
            verbose=args.verbose,
            override=args.override,
            check_now=False,  # the watch option only gets the current location if location has changed for an OVERRIDE flag was passed
            use_geoclue=None,  # watch will handle use settings
            settings=settings,
        )

    # ------------ Static coordinates
    elif args.latitude != None and args.longitude != None:
        # One Settings per run, shared by everything below, so a missing schema is reported once. Only created on paths that need it.
        settings = Settings()
        coords = tuple([args.latitude, args.longitude])
        sunrise_sunset = GetTimeOfSunriseSunset(
            args.verbose, args.override, settings=settings
        )
        times = sunrise_sunset(coords, args.verbose)
        if args.check_now != False:
            return check(times, settings, args.verbose)

    # ------------ Using Geoclue
    elif args.use_geoclue:
        settings = Settings()
        return run_once(
            args.verbose,
            args.override,
            args.check_now,
            args.use_geoclue,
            settings,
        )

    elif args.check_now != False:
        settings = (
            Settings(DataStore(args.check_now))
            if type(args.check_now) is str
            else Settings()
        )

        check(settings=settings, verbose=args.verbose)
        return None
    else:
        parser.print_help()
