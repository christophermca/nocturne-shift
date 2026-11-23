import importlib.metadata
import sys
import types

import pytest

from nocturne_shift import cli


@pytest.fixture
def plugins(monkeypatch):
    """Control which plugins load_commands() sees, whatever this machine has
    installed (e.g. `pip install -e ./gnome-night-shift` registers the real one).
    """
    installed = []

    def entry_points(group):
        assert group == cli.PLUGIN_GROUP
        return installed

    monkeypatch.setattr(importlib.metadata, "entry_points", entry_points)

    def install(name, value):
        installed.append(
            importlib.metadata.EntryPoint(
                name=name, value=value, group=cli.PLUGIN_GROUP
            )
        )

    return install


@pytest.fixture
def fake_services(monkeypatch):
    """A module that registers `services <action>` and records each call."""
    module = types.ModuleType("fake_services")
    module.calls = []

    def register(subparsers):
        subparsers.add_parser("services").add_argument("action")
        return lambda args: module.calls.append(args.action)

    module.register = register
    monkeypatch.setitem(sys.modules, "fake_services", module)
    return module


def test_installed_plugin_handles_its_command(argv, plugins, fake_services):
    plugins("services", "fake_services:register")
    argv("services", "start")

    cli.main()

    assert fake_services.calls == ["start"]


def test_missing_plugin_says_how_to_install(argv, plugins):
    argv("services", "start")

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert "pip install 'gnome-night-shift'" in str(exit_info.value.code)


def test_broken_plugin_does_not_break_the_core_cli(
    argv, plugins, capsys, caplog
):
    plugins("services", "no_such_module:register")
    argv()  # no arguments: prints help

    cli.main()

    captured = caplog.text
    assert (
        "usage: nocturne-shift" in capsys.readouterr().out
    )  # Prints the help message
    assert "skipping plugin 'services'" in caplog.text  # logs the problem
