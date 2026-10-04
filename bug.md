# Tsumiki — Config Schema / Default Config Mismatch Audit

> **Everything below "## Real bugs" is the original audit, kept as a historical
> snapshot.** It is not the current status — several findings were already fixed
> upstream, and some of its key names are since stale (`osd.duration` became
> `osd.timeout`; `dock.preview_apps`/`preview_size` were removed).
> **For what is actually still outstanding, read the "## Not completed" section
> at the end of this file.**

Audit of `tsumiki.schema.json` against `DEFAULT_CONFIG` in `utils/constants.py`
and the actual `config.get()` call sites.

**Scope:** schema (3546 lines), `DEFAULT_CONFIG` (~1900 lines), and every
`config.get()` in `modules/`, `widgets/`, `shared/`, `services/`, `utils/`.
No source files were modified during the audit.

**Method:** leaf paths from `DEFAULT_CONFIG` are matched against leaf nodes of
the schema; values are compared where the schema declares a `default`. Every
claim below was traced to a `config.get()` call site or confirmed as unread by
grepping all consumers.

**Excluded from the tables:** the `styling.*` tree. The schema has no `styling`
section at all, so all ~412 `styling.*` keys are unmatched by construction and
would drown out the real findings. Its absence is intentional — see
[Open item 4](#other) under "Not completed", which is now closed by decision.

---

## Executive summary

| Class                                                            | Count | Status                                   |
| ---------------------------------------------------------------- | ----- | ---------------------------------------- |
| Real bugs (corrupt data, dead config key, wrong format language) | 4     | Done — 1 already fixed upstream, 3 fixed |
| Config keys the schema cannot see but the code reads             | 6     | Done                                     |
| Schema properties nothing reads                                  | 3     | Open                                     |
| Duplicate `id` making a button unreachable                       | 1     | Already fixed upstream                   |
| Divergent default values                                         | 55    | Done — `DEFAULT_CONFIG` is authoritative |
| `DEFAULT_CONFIG` omits a schema default                          | 66    | 25 open (13 of them the cheatsheet gap)  |

The four real bugs are listed first. Everything else is drift that needed a
decision about which file is authoritative; the ruling was that
`DEFAULT_CONFIG` and the TypedDicts win. See "Not completed" at the end for
what is still open.

**Ruling applied:** `DEFAULT_CONFIG` and the TypedDicts are authoritative. The
schema follows them, except where the schema is the only correct source (see
the two deliberate exceptions at the end).

---

## Real bugs

> Bug 1 (corrupt icon) is absent from the current tree — `8a02d95d` ("fix:
> correct icon formatting in world clock configuration") already fixed it.

### 2. `modules.osd` — schema renamed the key, the code did not follow — DONE

| Side                                    | Key        | Value  |
| --------------------------------------- | ---------- | ------ |
| Schema                                  | `duration` | `3000` |
| `DEFAULT_CONFIG` + `modules/osd.py:110` | `timeout`  | `1500` |

`modules/osd.py:110` reads `self.config.get("timeout", 3000)`. The schema's
`duration` property is therefore unreachable, and the schema editor offers a
key that does nothing while the key that works is invisible. The two also
disagree numerically, so even a user who sets both gets `1500`.

Fix: rename the schema property to `timeout`, and reconcile the default with
`DEFAULT_CONFIG` (or drop the `DEFAULT_CONFIG` entry and let the code
fallback stand).

**Resolved as suggested.** The schema property is now `timeout` with default
`1500`, and the code fallback at `modules/osd.py:110` was corrected from `3000`
to `1500` so all three sides agree. `utils/widget_settings.py:259` already
declared `"timeout": int`, which confirmed the name.

### 3. `modules.desktop_clock` — schema advertises moment.js syntax, code runs strftime — DONE

| Side             | `date_format`  | `time_format` |
| ---------------- | -------------- | ------------- |
| Schema (was)     | `YYYY-MM-DD`   | `HH:mm`       |
| Code fallback    | `%Y-%m-%d`     | `%H:%M:%S`    |
| `DEFAULT_CONFIG` | `%A, %d %B %Y` | `%H:%M`       |

`modules/desktop_clock.py:460,469` passes both strings straight to
`ExtendedDateTime`, which formats with strftime. A user who trusted the schema
and wrote `YYYY-MM-DD` got the literal text `YYYY-MM-DD` rendered on the
desktop.

**Resolved as suggested.** Schema defaults are now `%Y-%m-%d` and `%H:%M`, and
both descriptions state "as a strftime template" so the format language is
explicit in the editor.

### 4. `widgets.submap` — schema key name does not match the code — DONE (upstream)

| Side             | Key               |
| ---------------- | ----------------- |
| Schema           | `hide_on_default` |
| Code             | `hide_on_default` |
| `DEFAULT_CONFIG` | `hide_on_default` |

The report was written against the pre-`44f8b820` tree, where the schema said
`hide_when_default`. Commit `44f8b820` already renamed it, so all three sides
now agree. No action needed.

## Config keys the schema cannot see but the code reads — DONE

| Key                                     | Read at                       |
| --------------------------------------- | ----------------------------- |
| `modules.notification.max_actions`      | `modules/notification.py:409` |
| `modules.notification.dismiss_on_hover` | `modules/notification.py:576` |
| `modules.osd.play_sound`                | — (see below)                 |
| `modules.osd.timeout`                   | `modules/osd.py:110`          |
| `widgets.battery.full_battery_level`    | `widgets/battery.py:24`       |
| `widgets.divider.size`                  | — (see below)                 |

`max_actions`, `dismiss_on_hover` and `full_battery_level` are real, working
options that were simply missing from the schema. All three are now declared,
each with the `DEFAULT_CONFIG` value as its default.

`widgets.divider.size` is different: `widgets/utility_widgets.py:11` defines
`DividerWidget` as a bare `Box` that never reads its config, so `size` did
nothing. Dropped rather than implemented.

`modules.osd.play_sound` is a third case the report did not anticipate: it has
**no reader at all**, in `modules/osd.py` or any of the five files in
`modules/osds/`. The only `play_sound` readers are `modules/notification.py:71,159`.
It is now declared in the schema for consistency with `DEFAULT_CONFIG` and the
`OSD` TypedDict, but it is still a declared no-op — setting it to `true` plays
nothing.

**Resolved:**

- `modules.notification.max_actions` — added, integer min 0, default `3`
- `modules.notification.dismiss_on_hover` — added, boolean, default `false`
- `widgets.battery.full_battery_level` — added, integer 0–100, default `100`
- `modules.osd.play_sound` — added, boolean, default `false` (no reader; see above)
- `modules.osd.timeout` — added by the bug 2 fix
- `widgets.divider.size` — removed from `DEFAULT_CONFIG` and `config.toml`

---

## Schema properties nothing reads

Declared in the schema, absent from `DEFAULT_CONFIG`, and with no
`config.get()` call site anywhere.

| Property                       | Note                                                                                                                |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| `modules.osd.style`            | no reader in `modules/osd.py`                                                                                       |
| `modules.osd.poll_interval`    | in `DEFAULT_CONFIG` (200) but unread; the only `poll_interval` reader is `widgets/stats.py:134`, a different widget |
| `modules.notification.enabled` | in `DEFAULT_CONFIG` (True) but never read; the module is gated by `main.py` at load time instead                    |

Also dead in `DEFAULT_CONFIG`, though these are schema-side too:

- `modules.desktop_clock.extended_date` and `widgets.date_time.extended_date`
  are both `False` and read by nothing. The code reads `nepali_date`
  (`datetime_menu.py:766`, `desktop_clock.py:462`), which the schema _does_
  declare. `extended_date` is a leftover rename.

---

---

## Divergent default values (55 keys)

`DEFAULT_CONFIG` and the schema both set a default, and they disagree. The
schema default is what an editor shows and what `example/config.toml` implies;
`DEFAULT_CONFIG` is what a fresh install actually gets.

Before fixing these, a decision is needed: **which file is authoritative?**
The AGENTS.md guidance names the schema as the source of truth for config
shape, which would mean the `DEFAULT_CONFIG` values are the ones to correct.

### Where the schema default looks wrong

| Path                                   | Schema  | `DEFAULT_CONFIG` |
| -------------------------------------- | ------- | ---------------- |
| `modules.dock.show_launcher`           | `false` | `true`           |
| `modules.dock.tooltip`                 | `true`  | `false`          |
| `modules.dock.enabled`                 | `true`  | `false`          |
| `modules.osd.enabled`                  | `true`  | `false`          |
| `modules.osd.icon_size`                | `40`    | `28`             |
| `modules.launcher.icon_size`           | `30`    | `16`             |
| `modules.launcher.tooltip`             | `false` | `true`           |
| `widgets.keyboard.show_icon`           | `false` | `true`           |
| `widgets.language.show_icon`           | `false` | `true`           |
| `widgets.submap.label`                 | `false` | `true`           |
| `widgets.kanban.tooltip`               | `false` | `true`           |
| `widgets.mpris.tooltip`                | `false` | `true`           |
| `widgets.mpris.truncation_size`        | `10`    | `20`             |
| `widgets.screenshot.annotation`        | `false` | `true`           |
| `widgets.date_time.clock_format`       | `'24h'` | `'12h'`          |
| `widgets.window_title.truncation_size` | `50`    | `20`             |

`modules.osd.enabled = true` and `modules.dock.enabled = true` in the schema
mean a user who writes a partial `[modules.osd]` block gets an overlay popping
up on a hotkey they did not ask for.

### Remaining 34 keys

Behavioural toggles that differ in both directions
(`general.debug`/`monitor_styles`/`tooltips`, `modules.notification.play_sound`,
`modules.notification.transition_type`, `modules.osd.transition_type`,
`widgets.*.hover_reveal`, `widgets.updates.flatpak`/`pad_zero`,
`widgets.date_time.hover_reveal`, `widgets.date_time.notification.hide_count_on_zero`),
plus formatting differences (`layout.*_section`,
`modules.activate_linux.layer`, `modules.desktop_clock.anchor`,
`widgets.battery.label_format`, `widgets.battery.hide_percent_when_full`,
`widgets.cpu.mode`, `widgets.memory.mode`, `widgets.storage.mode`,
`widgets.network_usage.kb_digits`, `widgets.network_usage.label_format`,
`widgets.weather.label_format`, `widgets.window_count.label_format`,
`widgets.quick_settings.shortcuts.items`, `widgets.cpu.sensor`,
`widgets.date_time.date_format`).

Note `widgets.cpu.mode` and `widgets.memory.mode` are `'circular'` in
`DEFAULT_CONFIG` but `'label'` in the schema, while `widgets.storage.mode` is
`'circular'` in `DEFAULT_CONFIG` and `'label'` in the schema too — but
`config.toml` sets all three to a third value. The three sibling widgets
should agree with each other before they agree with the schema.

---

## `DEFAULT_CONFIG` omits a schema default (66 keys)

Mostly harmless: the code supplies its own `.get()` fallback. Three are real
gaps where nothing supplies a value.

| Gap                                               | Detail                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `widgets.cheatsheet.*` (7 keys)                   | `DEFAULT_CONFIG["widgets"]["cheatsheet"]` is `{}` — entirely empty, while the schema declares `icon`, `label`, `label_text`, `tooltip`, `title`, `columns`, `groups_per_page`, `max_entries_per_group`. `config.toml` fills them in; a fresh install gets nothing and falls through to per-call `.get()` defaults scattered across `widgets/cheatsheet.py`. |
| `modules.cheatsheet` (5 keys)                     | The whole module is absent from `DEFAULT_CONFIG`.                                                                                                                                                                                                                                                                                                           |
| `modules.desktop_clock.type` + 10 `cookie_*` keys | Absent, so the cookie clock silently falls back to the non-cookie path.                                                                                                                                                                                                                                                                                     |

The other ~50 are `custom_widget[]`, `custom_button_group.buttons[]`,
`power.item_shortcuts`, `launcher.anchor/width/height/grid_columns/...`,
`widget_groups[].hover_reveal/revealer_icon`, `weather.provider`,
`workspaces.icon_map/show_urgent`, `github_tray.local_projects`,
`date_time.nepali_date`, `dock.location/preview_apps/preview_size`,
`notification.max_lines/max_expanded_lines`, `osd.duration` — each has a code
fallback, so none is urgent.

---

## Open item 4

The schema has **no `styling` section**, and the root has no
`additionalProperties: false`. Every one of the ~380 `styling.*` keys in
`config.toml` is therefore unvalidated: a typo like `border_radius` for
`border-radius` fails silently and the styling is just not applied.

`config.toml` also carries `[widgets.divider]`, `[widgets.settings]` and
`[widgets.wallpaper]`, none of which exist in the schema, though all three are
registered widgets (`modules/bar.py:84,105,116`).

This is a large piece of work — the styling tree is deeply nested and
repetitive — and it is out of scope for the bugs above. It is listed here
because it is the single largest source of unvalidated config in the project.

---

## Suggested order

4. Add the six missing `config.toml` keys to the schema.
5. Decide the authoritative side, then reconcile the 55 divergent defaults.
6. Fill the three `DEFAULT_CONFIG` gaps.

Steps 1-4 are mechanical and low risk. Step 5 needs a ruling; do not start it
without one.

---

## Verification

```
uv run ruff check .                                  # clean
uv run python -m unittest discover tests -q          # 1132 tests, OK
prek run --all-files                                 # all hooks pass
```

No styles were modified, so the SCSS compile check was not required.

---

## Not completed

Everything above this line is either fixed, was already fixed upstream, or was
closed by an explicit decision. What remains, re-verified against the current
tree rather than copied from the original audit.

Two items are closed **by decision rather than by code change** — the missing
`styling` schema section, and `widgets.divider` / `widgets.settings` /
`widgets.wallpaper` being absent from the schema. Both are intentional. They
are recorded under "Other" below with the supporting facts, so the next person
to read this does not re-open them as bugs.

### Dead config: declared but never read

Traced by searching every `config.get`/`persist.get` call site in `modules/`,
`widgets/`, `shared/`, `services/` and `utils/`. These are schema and/or
`DEFAULT_CONFIG` keys with no reader. Each needs an implement-or-drop decision.

| Key                                        | In `DEFAULT_CONFIG` | Note                                                                                                  |
| ------------------------------------------ | ------------------- | ----------------------------------------------------------------------------------------------------- |
| `modules.osd.style`                        | no                  | the only `"style"` read is `shortcut_config` in `widgets/quick_settings/shortcuts.py:26`              |
| `widgets.network_usage.upload`             | no                  | the code reads `upload_threshold`/`download_threshold` instead (`widgets/stats.py:308,309`)           |
| `widgets.network_usage.download`           | no                  | same                                                                                                  |
| `modules.osd.poll_interval`                | yes (200)           | the only `poll_interval` read is the GPU poller in `widgets/stats.py:134`                             |
| `modules.notification.enabled`             | yes                 | `modules/notification.py:147` reads `persist`, not `config`; the module is gated by `main.py` instead |
| `modules.dock.preview_apps`                | —                   | **DONE — removed** (was: no match in `modules/dock.py`)                                               |
| `modules.dock.preview_size`                | —                   | **DONE — removed**                                                                                    |
| `modules.dock.always_show_focused`         | —                   | **DONE — removed**                                                                                    |
| `modules.dock.hide_special_workspace_apps` | —                   | **DONE — removed**                                                                                    |
| `modules.notification.auto_dismiss`        | yes                 | no match                                                                                              |
| `widgets.battery.icons`                    | yes                 | `widgets/battery.py:29,44` build hardcoded icon lists                                                 |
| `widgets.usb_manager.auto_refresh`         | yes                 | no match                                                                                              |
| `widgets.usb_manager.refresh_interval`     | yes                 | no match                                                                                              |
| `widgets.cpu.show_unit`                    | yes                 | no match                                                                                              |
| `widgets.cheatsheet.groups_per_page`       | no                  | `columns` is read at `widgets/kanban.py:376`, this one is not                                         |
| `modules.desktop_clock.extended_date`      | yes                 | leftover rename; the code reads `nepali_date`                                                         |
| `widgets.date_time.extended_date`          | yes                 | same                                                                                                  |

Note `modules.osd.play_sound` is now declared in the schema but is still in
this category — it has no reader in `modules/osd.py` or any of the five files
in `modules/osds/`.

### `DEFAULT_CONFIG` omits a schema default

**25 keys remain** (was 47). All have a code `.get()` fallback, so none is
urgent. Grouped by cause:

- **Real gaps — 13 keys.** A fresh install gets an empty dict or nothing, and
  the value is scattered across per-call `.get()` defaults. This is the only
  group left worth acting on:
  - `widgets.cheatsheet.*` (8) — `DEFAULT_CONFIG["widgets"]["cheatsheet"]` is `{}`
  - `modules.cheatsheet.*` (5) — the module is absent entirely
    (`enabled`, `layer`, `anchor`, `transition_type`, `transition_duration`)
- **Layout/sizing defaults with code fallbacks — 9 keys:**
  `modules.launcher.ignored`/`anchor`/`width`/`height`/`layout`/`grid_columns`,
  `modules.dock.location`, `modules.notification.max_lines`/`max_expanded_lines`
- **Dead — 3 keys, do not mirror.** `modules.osd.style`,
  `widgets.network_usage.upload`/`download` have no reader. They are in the
  dead-config table above; adding them to `DEFAULT_CONFIG` would manufacture
  new dead keys.

### Already done in this category

- **Widget boilerplate.** Mirrored into `DEFAULT_CONFIG` from the code
  fallbacks: `widgets.dns_switcher.*` (`tooltip`, `label`, `label_text`,
  `icon`), `widgets.cloudflare_warp.*` (5 keys — `tooltip`, `label`,
  `label_text`, `connected_icon`, `disconnected_icon`), `widgets.ip_monitor.*`
  (`tooltip`, `label`, `label_text`, `icon`), and
  `widgets.power.item_shortcuts`. `item_shortcuts` is `{}` rather than the
  schema's per-item values (`shutdown = "s"` etc.) because the code reads
  `config.get("item_shortcuts", {})` at `widgets/power_button.py:34` — the real
  default is _no_ keyboard shortcuts. Mirroring the schema would have activated
  shortcuts nobody asked for.
- **Single behavioural keys — 6 of 9.** Added to `DEFAULT_CONFIG`, each matching
  its code fallback exactly: `modules.launcher.plugins_dir` (`""`),
  `widgets.weather.reveal_duration` (`500`), `widgets.weather.provider`
  (`"open-meteo"`), `widgets.workspaces.show_urgent` (`false`),
  `widgets.date_time.nepali_date` (`false`), `widgets.clipboard.enable_pinning`
  (`true`). The other three are dead and were deliberately **not** added.
  `widgets.clipboard.enable_pinning`

### Other

- **~~Open item 4 — no `styling` section in the schema.~~ CLOSED BY DECISION.**
  The ~412 `styling.*` keys are intentionally left unvalidated; generating a
  schema section for them is not wanted. Recorded facts, for anyone who
  revisits this: `config.toml`'s styling tree is structurally identical to
  `DEFAULT_CONFIG`'s — 412 leaf keys on both sides, **zero** keys in
  `config.toml` that `DEFAULT_CONFIG` does not have, and only 3 value
  differences, all deliberate user customisation (`bar.widgets.system_tray.spacing`,
  `bar.widgets.github_tray.icon_size`, `bar.widgets.quick_settings.icon_size`).
  The root has no `additionalProperties: false`, so a typo like `border_radius`
  for `border-radius` still fails silently — that is the accepted cost.
- **~~`widgets.divider`, `widgets.settings`, `widgets.wallpaper` are not in the
  schema.~~ CLOSED BY DECISION — intentional.** All three are registered
  widgets (`modules/bar.py:84,105,116`) and their absence from the schema is
  deliberate. For the record: `divider` and `settings` read no config at all
  (`widgets/utility_widgets.py` and `widgets/settings.py` contain no config
  access), so there is nothing to declare. `wallpaper` does read two keys —
  `icon` and `label` at `widgets/wallpaper.py:19,21` — both with code
  fallbacks and both mirrored in `DEFAULT_CONFIG`, so the keys work; they
  simply get no editor completion.
- **~~`validate_config_enums` only checks `enum` and `pattern`.~~ DONE.**
  `minimum`, `maximum`, `minItems` and `maxItems` are now enforced in
  `utils/validation.py`. Type mismatches are still ignored by design — a
  value whose type does not match the declaration is skipped rather than
  rejected, so `timeout = "abc"` still passes. Changing that is a larger
  behavioural decision, since it could reject configs that work today.
- **~~No duplicate-`id` detection.~~ DONE.** `_validate_unique_ids` in
  `utils/validation.py` warns on a reused `id` across all four indexed
  collections, naming both indices. A warning rather than an error, so a
  duplicate id cannot stop the bar from starting.

### Deliberate exceptions

Two places where the schema was left as the better value rather than following
`DEFAULT_CONFIG`:

- `modules.desktop_clock.date_format` — schema `%Y-%m-%d`,
  `DEFAULT_CONFIG` `%A, %d %B %Y`. Both are valid strftime; the schema side was
  the bug 3 fix (it was `YYYY-MM-DD`, which renders as that literal text).

---

## Final status — remaining work

Re-verified against the current tree. Everything else in this file is done;
only the items below are outstanding.

### 1. Dead config: declared in both files, nothing reads them

**Now empty — all three keys were dropped.** Removed from the schema,
`DEFAULT_CONFIG`, `config.toml`, `example/config.toml` and every doc locale:

| Key                     | Note                                                                                                        |
| ----------------------- | ----------------------------------------------------------------------------------------------------------- |
| `widgets.battery.icons` | the widget hardcoded its two icon lists, so the key never did anything                                      |
| `modules.osd.style`     | the only `"style"` read is `widgets/workspaces.py:23`, a different widget                                   |
| `widgets.cpu.show_unit` | no reader, and it was in the schema's `required` array, so it could not be dropped without editing that too |

`widgets.workspaces.style` was **kept** — it is a live key read at
`widgets/workspaces.py:23` and shares a name with the dropped `modules.osd.style`.

### 2. Dead config: `DEFAULT_CONFIG` only, no schema entry

| Key                               | In `DEFAULT_CONFIG` | Note                                                  |
| --------------------------------- | ------------------- | ----------------------------------------------------- |
| `modules.notification.enabled`    | `True`              | the module is gated by `main.py` at load time instead |
| `widgets.date_time.extended_date` | `False`             | same                                                  |

Resolved since this table was written:

- `modules.osd.poll_interval` — **dropped** from `DEFAULT_CONFIG`. It had no
  schema entry, and the only `poll_interval` reader (`widgets/stats.py:134`)
  belongs to the CPU widget's GPU poller, a different widget. The schema and
  `DEFAULT_CONFIG` OSD key sets now match exactly.
- `modules.notification.auto_dismiss` — **implemented**.
  `NotificationWidget.start_timeout` returns before arming the expiry repeater
  unless the flag is set, so the guard sits in one place and covers both call
  sites. The default stays `true`; schema, `DEFAULT_CONFIG`, both TOMLs and the
  docs already declared it, so only the reader was missing.

### 3. `widgets.cheatsheet` is `{}` and `modules.cheatsheet` is absent entirely

8 + 5 keys. The only _real_ gap left: a fresh install gets nothing and falls
through to per-call `.get()` defaults scattered through `widgets/cheatsheet.py`.
Worth doing next.

### 4. Layout/sizing keys — resolved

All seven are now mirrored into `DEFAULT_CONFIG`, each matching both the schema
default and the code fallback:

- `modules.launcher.anchor` `center`, `width` `280`, `height` `320`,
  `layout` `list`, `grid_columns` `3` (`modules/launcher.py:88-113`)
- `modules.notification.max_lines` `4`, `max_expanded_lines` `20`
  (`modules/notification.py:215-216`)

Both `config.toml` and `example/config.toml` already set these; only
`DEFAULT_CONFIG` was behind. The launcher and notification key sets now match
the schema exactly in both directions.

Two keys in this group turned out to be dead rather than merely unmirrored, and
have been removed:

- `modules.dock.location` — a rename leftover. `modules/dock.py:938` reads
  `layer`; `location` carried the same enum under a different name and its own
  description said "Determines the layer of the dock". Existed only in the
  schema. **Dropped.**
- `modules.launcher.ignored` — no reader at all, and unlike `dock.location` no
  replacement key, so the launcher simply has no ignore list. Six other widgets
  do have working `ignored` readers. **Dropped** rather than implemented, since
  filtering the launcher's app list is a feature rather than a config fix.

---

### Not to be re-opened

Decided and closed; listed so the next reader does not treat them as new work:

- No `styling` section in the schema. The ~412 `styling.*` keys are
  intentionally unvalidated. Accepted cost: a typo like `border_radius` for
  `border-radius` still fails silently, because the root has no
  `additionalProperties: false`.
- `widgets.divider`, `widgets.settings`, `widgets.wallpaper` absent from the
  schema. All three are registered widgets; `divider` and `settings` read no
  config at all, and `wallpaper` reads only `icon`/`label`, which work.
- Type mismatches are still skipped rather than rejected in validation, so
  `timeout = "abc"` passes. Changing that would reject configs that work today.
- `modules.osd.play_sound` is declared in the schema but has no reader in
  `modules/osd.py` or `modules/osds/`. Kept for consistency with
  `DEFAULT_CONFIG` and the `OSD` TypedDict; setting it to `true` plays nothing.
