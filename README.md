# Nocturne Shift

Nocturne Shift will lookup the time of the sunrise and sunset for the provided location.

- `nocturne-shift` can also check if the current state of the 24hr period is day or night
- `nocturne-shift services`: systemd timers (with `gnome-night-shift`)


## Features

* Use geoclue to determine location. Requires Location services to be enabled. **(Settings > Privacy & Security > Location > Enable "Automatic Device Location"**
* Run `nocturne-shift` as a systemd service.

## How It Works

**Night Shift** can use the provided `latitude` and `longitude` OR will use `geoclue` to determine your systems geolocation.
Next **Night shift** will determine the time for sunrise and sunset.

Then **Night Shift** will attempt to create a Gsettings Object to store the data.

## Requirements
- Python 3.10+
- GLib / GSettings and PyGObject (usually installed with your desktop; on Debian/Ubuntu: `python3-gi`)
- `glib-compile-schemas` to compile the schema (Debian/Ubuntu: `libglib2.0-bin`)
- Optional: systemd (Linux) for `nocturne-shift services`
- Optional: GeoClue for `-g`


## Installation

Two packages; this repo is the core:

| Package | What it is |
|---|---|
| `nocturne-shift` | The core and the `nocturne-shift` command |
| [`gnome-night-shift`](https://github.com/christophermca/gnome-night-shift) | `nocturne-shift` plus the systemd timers (`nocturne-shift services ...`, Linux); what the GNOME extension uses. Lives in its own repo |

### GNOME

```bash
pipx install --system-site-packages gnome-night-shift
```

### Just the command

```bash
pipx install --system-site-packages nocturne-shift
```

`--system-site-packages` uses your distro's PyGObject instead of building it.

## Usage

```sh
usage: nocturne-shift [-h] [--lat [LATITUDE]] [--lng [LONGITUDE]]
                      [-c [SCHEMA_PATH]] [-f] [-g] [-w [SCHEMA_PATH]] [-v]
                      [--version]
                      {services} ...

Get the times for the sunrise/sunset

positional arguments:
  {services}
    services            Handle Night-Shift Service

options:
  -h, --help            show this help message and exit
  --lat [LATITUDE]      compares current time with sunrise/sunset time
  --lng [LONGITUDE]     compares current time with sunrise/sunset time
  -c [SCHEMA_PATH], --check-now [SCHEMA_PATH]
                        compares current time with sunrise/sunset time
  -f, --force           ignores cached data
  -g, --geoclue         use geoclue to determine location
  -w [SCHEMA_PATH], --watch [SCHEMA_PATH]
                        watch for changes in data_store
  -v, --verbose         Prints more information
  --version             Prints more information
```


[![Publish to PyPI](https://github.com/christophermca/nocturne-shift/actions/workflows/publish-pypi.yml/badge.svg)](https://github.com/christophermca/nocturne-shift/actions/workflows/publish-pypi.yml)

[![Publish to TestPyPI](https://github.com/christophermca/nocturne-shift/actions/workflows/publish-testpypi.yml/badge.svg?branch=dev&event=workflow_dispatch)](https://github.com/christophermca/nocturne-shift/actions/workflows/publish-testpypi.yml)
