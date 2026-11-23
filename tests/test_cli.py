import pytest
from unittest.mock import ANY, patch

from nocturne_shift import cli

TIMES = ("06:52", "18:51")


@pytest.fixture
def mock_fetcher():
    with patch(
        "nocturne_shift.cli.GetTimeOfSunriseSunset", autospec=True
    ) as fetcher:
        yield fetcher


@pytest.fixture
def mock_check():
    with patch("nocturne_shift.cli.check") as check:
        yield check


@pytest.fixture(autouse=True)
def settings_class():
    """main() builds one Settings per run; fake it so no test touches GSettings."""
    with patch("nocturne_shift.cli.Settings") as settings_class:
        yield settings_class


@pytest.fixture(autouse=True)
def data_store_class():
    """-w / -c SCHEMA_PATH build a DataStore; fake it so no schema is compiled."""
    with patch("nocturne_shift.cli.DataStore") as data_store_class:
        yield data_store_class


# --- latitude / longitude ---------------------------------------------------


def test_lat_lng_fetches_and_exits_cleanly(
    argv, mock_fetcher, mock_check, settings_class
):
    argv("--lat=40.7", "--lng=-74.0")

    result = cli.main()

    mock_fetcher.assert_called_once_with(
        0, False, settings=settings_class.return_value
    )
    mock_fetcher.return_value.assert_called_with((40.7, -74.0), 0)
    mock_check.assert_not_called()
    assert result is None


def test_lat_lng_with_check_now_flag_checks_the_fetched_times(
    argv, mock_fetcher, mock_check, settings_class
):
    argv("--lat=40.7", "--lng=-74.0", "--check-now")
    mock_fetcher.return_value.return_value = TIMES

    cli.main()

    mock_fetcher.assert_called_once_with(
        0, False, settings=settings_class.return_value
    )
    mock_fetcher.return_value.assert_called_with((40.7, -74.0), 0)

    settings = settings_class.return_value

    settings_class.assert_called_once_with()  # one Settings for the whole run
    mock_check.assert_called_once_with(TIMES, settings, 0)


def test_non_numeric_coordinate_is_a_usage_error(argv, mock_fetcher, capsys):
    argv("--lat=abc", "--lng=-74.0")

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert "invalid float value" in capsys.readouterr().err
    mock_fetcher.assert_not_called()


# --- -c / --check-now [SCHEMA_PATH] -------------------------------------------
def test_given_check_now_fails_throws_error(argv, settings_class, caplog):
    argv("--check-now")
    with patch(
        "nocturne_shift.cli.is_day_or_night",
    ) as fn:

        fn.side_effect = AttributeError()
        result = cli.main()

        assert result is None
        assert "check() failed" in caplog.text


def test_check_now_uses_default_settings(argv, mock_check, settings_class):
    argv("--check-now")

    result = cli.main()

    mock_check.assert_called_once_with(
        settings=settings_class.return_value, verbose=0
    )
    assert result is None


def test_check_now_with_schema_path_uses_that_data_store(
    argv, mock_check, settings_class, data_store_class
):
    argv("--check-now", "/path/to/schemas")

    cli.main()

    data_store_class.assert_called_once_with("/path/to/schemas")
    settings_class.assert_called_once_with(data_store_class.return_value)
    mock_check.assert_called_once_with(
        settings=settings_class.return_value, verbose=0
    )


# --- -g / --geoclue -----------------------------------------------------------


def test_geoclue_fetches_with_one_shared_settings(
    argv, mock_fetcher, mock_check, settings_class
):
    argv("-g", "-v", "-f")

    cli.main()

    settings_class.assert_called_once_with()
    verbose = 1  # verbose is a count now
    mock_fetcher.assert_called_once_with(
        verbose,
        True,
        True,
        settings_class.return_value,
    )


def test_geoclue_without_check_now_does_not_check(
    argv, mock_fetcher, mock_check
):
    argv("-g")

    cli.main()

    mock_check.assert_not_called()


def test_geoclue_with_check_now_FLAG_checks_the_fetched_times(
    argv, mock_fetcher, mock_check, settings_class
):
    argv("-g", "--check-now")
    mock_fetcher.return_value.times = TIMES

    cli.main()

    mock_check.assert_called_once_with(TIMES, settings_class.return_value, 0)


# --- -w / --watch [SCHEMA_PATH] -----------------------------------------------


def test_watch_with_schema_path_fetches_with_that_data_store(
    argv, mock_fetcher, mock_check, settings_class, data_store_class
):
    argv("--watch", "/path/to/schemas")

    cli.main()

    data_store_class.assert_called_once_with("/path/to/schemas")
    settings_class.assert_called_once_with(data_store_class.return_value)
    mock_fetcher.assert_called_once_with(
        0, False, None, settings_class.return_value
    )


def test_no_args_prints_help(argv, mock_fetcher, capsys):
    argv()

    cli.main()

    assert "usage:" in capsys.readouterr().out
    mock_fetcher.assert_not_called()


# --- check() and run_once() ------------------------------------------------------


def test_check_passes_times_and_settings_through_and_returns_none():
    settings = object()

    with patch("nocturne_shift.cli.is_day_or_night", autospec=True) as fn:
        result = cli.check(TIMES, settings)

    fn.assert_called_once_with(TIMES, settings, 0)
    assert result is None  # a string here would become exit status 1


def test_check_without_times_uses_saved_times():
    with patch("nocturne_shift.cli.is_day_or_night", autospec=True) as fn:
        cli.check()

    fn.assert_called_once_with(None, None, 0)


def test_run_once_shares_settings_with_fetch_and_check(
    mock_fetcher, mock_check
):
    settings = object()
    mock_fetcher.return_value.times = TIMES

    cli.run_once(check_now=None, settings=settings)  # None: -c given, no path

    mock_fetcher.assert_called_once_with(False, False, False, settings)
    mock_check.assert_called_once_with(TIMES, settings, 0)


def test_run_once_without_check_now_does_not_check(mock_fetcher, mock_check):
    cli.run_once(check_now=False)

    mock_check.assert_not_called()


def test_run_once_catches_fetch_errors(mock_fetcher, caplog):
    mock_fetcher.side_effect = RuntimeError("offline")

    cli.run_once()

    (record,) = caplog.records
    assert record.getMessage() == "run_once() failed"
    assert "RuntimeError: offline" in caplog.text


def test_run_once_catches_check_errors(mock_fetcher, caplog):
    mock_fetcher.return_value.times = ("06:52", "18:51")

    with patch(
        "nocturne_shift.cli.check", side_effect=AttributeError("no schema")
    ) as check:
        cli.run_once(check_now=None)

    check.assert_called_once()

    (record,) = caplog.records
    assert record.getMessage() == "check() failed"
    assert "AttributeError: no schema" in caplog.text


# --- -v / --verbose and -w / --watch ---------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ["--check-now"],
        ["--check-now", "/path/to/schemas"],
        ["--lat=40.7", "--lng=-74.0", "--check-now"],
        ["-g", "--check-now"],
    ],
    ids=["-c", "-c PATH", "--lat --lng -c", "-g -c"],
)
def test_verbose_reaches_is_day_or_night(argv, mock_fetcher, args):
    argv(*args, "-vv")
    mock_fetcher.return_value.return_value = TIMES  # sunrise_sunset(coords)
    mock_fetcher.return_value.times = TIMES  # run_once reads .times

    with patch("nocturne_shift.cli.is_day_or_night", autospec=True) as fn:
        cli.main()

    # autospec matches by signature, so this passes however check() spells the call
    fn.assert_called_once_with(ANY, ANY, verbose=2)


@pytest.mark.parametrize(
    "args, checks",
    [
        (["--watch", "/path/to/schemas"], False),
        (["--watch", "/path/to/schemas", "--check-now"], False),
    ],
    ids=["-w", "-w -c"],
)
def test_watch_DOESNOT_check_with_check_now(
    argv, mock_fetcher, mock_check, args, checks
):
    argv(*args)
    mock_fetcher.return_value.times = TIMES  # what a real fetch sets

    cli.main()

    assert mock_check.called is checks


def test_watch_without_path_uses_the_default_settings(
    argv, mock_fetcher, settings_class, data_store_class
):
    argv("--watch")

    cli.main()

    settings_class.assert_called_once_with()
    data_store_class.assert_not_called()
