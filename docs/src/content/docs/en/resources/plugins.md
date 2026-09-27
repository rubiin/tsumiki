---
title: Plugin Development
description: Write your own slash-command plugins for the launcher
sidebar:
  order: 6
---

Plugins add slash commands to the launcher (e.g. `/calc`, `/translate`). Each
plugin is a Python class that subclasses `LauncherPlugin`; the launcher
discovers plugins in the plugins directory and calls into them as the user
types.

This guide covers everything you need to write, debug, and ship your own
plugin. The bundled plugins in `plugins/` are a good reference — they show
patterns for network requests, subprocesses, and local file access.

## How a plugin runs

1. The user types `/` in the launcher search box and starts typing a command.
2. The launcher matches the text against each plugin's `name` and `aliases`.
3. `handle(args)` runs on a **worker thread** and returns the rows shown live
   while typing.
4. The user highlights a row and presses `Enter` (or clicks it).
5. `execute(result)` runs on the **main thread** and performs the action.

`handle()` is re-invoked on every keystroke (after a debounce), so it must be
fast and safe to run many times.

## Configuration

Plugins live under `[modules.launcher]`:

```toml
[modules.launcher]
enabled = true
plugins_enabled = true
plugins_dir = ""          # default: the bundled plugins/ directory
plugins = ["calc", "emoji"]  # strict allowlist; an empty list loads none
```

- **`plugins_enabled`**: Turns the slash-command system on or off.
- **`plugins_dir`**: Directory to load plugins from. Defaults to the bundled
  `plugins/` directory shipped with Tsumiki; set it to your own directory
  (e.g. `~/.config/tsumiki/plugins`) for personal plugins.
- **`plugins`**: Strict allowlist. Only plugins whose `name` is listed are
  loaded — an empty list loads **no** plugins. Names are matched
  case-insensitively against the plugin's `name`, **not** its aliases.

Any `.py` file (unless it starts with `_`) and any subdirectory with an
`__init__.py` in the plugins directory is imported. Every `LauncherPlugin`
subclass in the module is registered. A plugin with an empty `name` is
skipped; a plugin that fails to import is skipped with a warning — a broken
plugin never crashes the bar.

## A minimal plugin

```python
# ~/.config/tsumiki/plugins/hello.py
from utils.plugin_manager import LauncherPlugin, PluginResult, copy_to_clipboard


class HelloPlugin(LauncherPlugin):
    name = "hello"  # slash command: /hello
    description = "Say hello to someone"
    icon = "face-smile-symbolic"
    aliases = ["hi"]

    def handle(self, args: str) -> list[PluginResult]:
        who = args.strip() or "world"
        return [PluginResult(f"Hello, {who}!", subtitle="Press Enter to copy")]

    def execute(self, result: PluginResult | None = None) -> bool:
        if result:
            copy_to_clipboard(result.title)
        return False  # False closes the launcher
```

Drop the file into the plugins directory, add `"hello"` to `plugins`, and
restart the bar. `/hello` (or `/hi`) now greets you.

## The LauncherPlugin API

### Class attributes

| Attribute     | Type          | Purpose                                                                                                                                                                                                     |
| ------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`        | `str`         | The slash command (`/name`). Required — a plugin without a name is skipped.                                                                                                                                 |
| `description` | `str`         | Short description shown when browsing commands with `/`.                                                                                                                                                    |
| `icon`        | `str \| None` | GTK icon name (e.g. `"face-smile-symbolic"`) or a Nerd Font glyph. Falls back to the launcher default when unset.                                                                                           |
| `aliases`     | `list[str]`   | Extra slash commands that trigger this plugin.                                                                                                                                                              |
| `debounce_ms` | `int \| None` | Per-plugin debounce before `handle()` fires while typing. `None`/`0` uses the launcher default (150 ms). Set a larger value for expensive plugins (network or subprocess) to avoid one query per keystroke. |
| `keep_open`   | `bool`        | When `True`, the launcher stays open after `execute()`.                                                                                                                                                     |

### Methods

| Method                | Thread | Purpose                                                                                           |
| --------------------- | ------ | ------------------------------------------------------------------------------------------------- |
| `handle(args)`        | worker | Return the result rows for the argument string.                                                   |
| `execute(result)`     | main   | Run when the user activates a row (or the bare command). Return `True` to keep the launcher open. |
| `is_cancelled()`      | any    | `True` when the query was superseded since the last dispatch.                                     |
| `run_subprocess(...)` | any    | Like `run_subprocess` but tracks the spawned process so `cancel()` can kill it.                   |

## `handle()`: producing results

`handle()` receives the text after the command, e.g. `/translate bonjour`
calls `handle("bonjour")`. Return a list of `PluginResult` rows:

```python
PluginResult(
    title,  # main line shown in the launcher
    subtitle="",  # secondary line (hint, source, etc.)
    icon=None,  # per-row icon override; falls back to the plugin icon
    data=None,  # arbitrary payload handed to execute() on activation
)
```

- Runs on a worker thread — **no GTK calls allowed**. Network requests,
  subprocesses, and file reads are fine.
- Return an empty list to show the "No results" hint.
- Returning a bare `PluginResult` or a non-list value is coerced, so a plugin
  that misbehaves degrades gracefully instead of crashing.
- If `handle()` raises, the launcher renders an error row with the exception
  message — the bar stays up.

## `execute()`: acting on a result

`execute()` runs on the main thread when the user activates a row. It receives
the row's `PluginResult` (or `None` for a bare command activation). Return
`True` to keep the launcher open, `False` to close it. The plugin's
`keep_open` attribute is honored too.

If `execute()` raises, the error is logged and the launcher stays open.

## Helpers

| Helper                                                            | Purpose                                                                                                                                                                                                                                                                                          |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `copy_to_clipboard(text)`                                         | Copy text to the system clipboard (`wl-copy`, falling back to `xclip`).                                                                                                                                                                                                                          |
| `run_subprocess(args, timeout=..., input=..., env=..., text=...)` | Replacement for `subprocess.run` — returns a `SubprocessResult` (`args`, `returncode`, `stdout`, `stderr`). Raises `SubprocessTimeoutError` on timeout, killing the whole process group. `text=False` returns bytes; `capture_output` is accepted for compatibility. No other keyword arguments. |
| `self.run_subprocess(...)`                                        | Same, but registers the process with the plugin so `cancel()` kills it mid-flight.                                                                                                                                                                                                               |
| `get_http_client()`                                               | Shared `httpx` client from `utils.functions` — use it for network requests (connection pooling, timeouts).                                                                                                                                                                                       |
| `find_executable(name)`                                           | Locate a binary on `PATH`, returning `None` if missing.                                                                                                                                                                                                                                          |

## Cancellation and debouncing

The launcher re-dispatches `handle()` as the user types. When a newer query
supersedes an in-flight one, the launcher calls the plugin's `cancel()` — this
sets a flag and kills any process started via `self.run_subprocess()`.

For long-running work:

- Check `self.is_cancelled()` at safe points and bail out early.
- Run subprocesses through `self.run_subprocess()` so they get killed instead
  of running to completion and being discarded.
- Set a `debounce_ms` (e.g. 400–500) on network/subprocess plugins so queries
  fire only after the user pauses typing.

```python
def handle(self, args: str) -> list[PluginResult]:
    if self.is_cancelled():
        return []  # superseded before the request went out
    result = self.run_subprocess(["some-command"], timeout=5)
    if self.is_cancelled():
        return []  # superseded while in flight
    ...
```

## Multi-file plugins (packages)

For plugins with helper modules, use a package: a directory with an
`__init__.py`. Re-export the plugin class from `__init__.py` and use relative
imports inside the package:

```
plugins/my_tool/
├── __init__.py      # from .plugin import MyToolPlugin
└── plugin.py        # class MyToolPlugin(LauncherPlugin): ...
```

## A subprocess example

```python
from utils.plugin_manager import LauncherPlugin, PluginResult, run_subprocess


class UptimePlugin(LauncherPlugin):
    name = "uptime"
    description = "Show system uptime"
    icon = "utilities-system-monitor-symbolic"

    def handle(self, args: str) -> list[PluginResult]:
        proc = run_subprocess(["uptime", "-p"], timeout=5)
        if proc.returncode != 0:
            return [PluginResult("uptime failed", icon="dialog-error-symbolic")]
        return [PluginResult(proc.stdout.strip(), subtitle="Press Enter to copy")]
```

## Shipping a plugin

1. Place the `.py` file (or package directory) in your plugins directory.
2. Add its `name` to `plugins` in `[modules.launcher]`.
3. Restart the bar (`./tsumiki.sh -start` or your own restart binding).

Plugins load at launcher startup — there is no hot reload. If a plugin doesn't
appear, check the log output: load failures and allowlist mismatches are
logged with a `[LauncherPlugin]` prefix.

## Bundled plugins

Tsumiki ships the following plugins in `plugins/` — they double as reference
implementations of the full API (local work, network requests, subprocesses,
cancellation). Enable the ones you want by listing their `name` in the
`plugins` allowlist.

| Command              | Aliases                   | What it does                                     | Requires              |
| -------------------- | ------------------------- | ------------------------------------------------ | --------------------- |
| `/calc`              | `calculator`, `math`      | Evaluate math, units and currency                | `qalc` (libqalculate) |
| `/translate`         | `tr`, `t`                 | Translate text (auto-detected source)            | network               |
| `/emoji`             | `emo`                     | Search and copy an emoji                         | — (offline)           |
| `/clipboard-history` | `clip`, `cb`              | Search and re-copy clipboard history             | `cliphist`            |
| `/currency`          | `fx`, `money`, `exchange` | Convert currencies (daily cached rates)          | network               |
| `/kill`              | `k`, `pkill`              | Search and kill a process (or a port's listener) | —                     |
| `/search`            | `s`, `web`                | Web search; Enter opens a result                 | network               |
| `/history`           | `h`, `hist`               | Search shell command history                     | —                     |
| `/define`            | `def`, `dict`             | Word definitions (dict.org WordNet)              | network               |
| `/shorten`           | `short`, `tiny`           | Shorten a URL (is.gd / TinyURL)                  | network               |
| `/unicode`           | `uni`, `char`             | Search and copy a Unicode character              | — (offline)           |

### `/calc` — math, units & currency

Evaluates expressions with libqalculate and copies the result on Enter.
Requires `qalc` (e.g. `sudo pacman -S libqalculate`). Runs as a cancellable
subprocess with a generous debounce.

```
/calc 100 cm to inches
/calc sqrt(2)
/calc 2 + 2
```

### `/translate` — text translation

Translates text with auto-detected source language; copies the translation
on Enter. The target language can be given with `in <language>` or
`to <language>`, otherwise the plugin default (English) is used.

```
/translate bonjour
/translate こんにちは
/translate hello in nepali
```

### `/emoji` — emoji search

Searches the bundled emoji database (offline) and copies the selected emoji
on Enter.

```
/emoji heart
/emoji rocket
/emoji smileys
```

### `/clipboard-history` — clipboard search

Searches `cliphist` history and copies the selected item back on Enter.
Requires `cliphist` (e.g. `sudo pacman -S cliphist`).

```
/clipboard-history https://
```

### `/currency` — currency conversion

Converts between world currencies with rates from Frankfurter (keyless,
no API key), cached locally and refreshed at most once per day. The amount
defaults to 1; common names and symbols work too. Enter copies the converted
amount.

```
/currency 100 usd to eur
/currency usd eur
/currency 10 dollars euros
```

### `/kill` — process killer

Searches running processes (by name or command line) and terminates the
selected one with SIGTERM — or SIGKILL with `-9` / `--force`. A numeric
query is treated as a port: `/kill 3000` kills whatever is listening on
port 3000.

```
/kill firefox
/kill -9 spotify
/kill 3000
```

### `/search` — web search

Searches DuckDuckGo (keyless) and shows the top results in the launcher.
Enter opens the selected result in your default browser and copies its URL.

```
/search fabric hyprland
/search python httpx timeout
```

### `/history` — shell history search

Searches your bash, zsh and fish history files (plus `$HISTFILE` when set),
de-duplicated most-recent-first. Enter copies the command back to the
clipboard — nothing is ever executed.

```
/history git
/history docker compose
```

### `/define` — word definitions

Queries dict.org's WordNet over the DICT protocol (RFC 2229) — no API key.
Each numbered sense is its own row; Enter copies the full definition. Pick
a different database with `-d <database>`.

```
/define serendipity
/define -d foldoc monad
```

### `/shorten` — URL shortener

Shortens a URL via is.gd (TinyURL as fallback) — both free and keyless.
`https://` is added automatically when missing. Enter copies the short link.

```
/shorten https://github.com/rubiin/tsumiki
/shorten example.com
```

### `/unicode` -- Unicode character search

Searches a bundled database of ~2000 common Unicode characters by name,
alias, codepoint, or category. Enter copies the character to the clipboard.

```
/unicode arrow
/unicode copyright
/unicode EUR
```
