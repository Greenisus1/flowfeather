# Flowfeather

Tiny self-hosted automations for your Pi. A flow is one trigger plus one
action: on a schedule, when a file changes, or when an RSS feed posts
something new - run a shell command, append to a log file, or fetch a
URL. Fullscreen terminal UI, pure Python standard library, one JSON
state file. No daemon and no heavy runtime: it runs what is due when you
press `r`, or from cron with `--tick`.

## What it does

- **Triggers**: every N minutes; a file appearing, changing or
  disappearing (content-checked); a new item in an RSS feed.
- **Actions**: run a shell command (60s cap), append a templated line to
  a file (`{name}` and `{time}` placeholders), fetch a URL.
- **Per-flow log** (`l`) of the last 20 runs, run counters, enable/disable
  (`e`) without deleting.
- **Cron-friendly**: `python3 flowfeather.py --tick` runs every due flow
  once and exits - no resident process burning your Pi's RAM.

## Install (Pi App Store)

Install through the Pi App Store, or:

```sh
sudo bash app-store.sh install   # checks Python/curses, compiles sources
sudo python3 flowfeather.py      # or: bash app-store.sh run
sudo bash app-store.sh tick      # run due flows once (for cron)
```

State lives in `/root/flowfeather/flows.json` (override with the
`FLOWFEATHER_HOME` environment variable).

## Tests

```sh
python3 test_flowfeather.py   # unit tests (triggers, actions, runner)
python3 test_pty.py           # fullscreen walkthrough in a pty
```

MIT license, copyright Greenisus1. Built with AI assistance from my design.
