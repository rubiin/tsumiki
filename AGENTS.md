# Claude Configuration for Tsumiki

> Precedence: if an explicit user instruction in a session conflicts with this
> file, the user instruction wins for that task. Otherwise, follow this file.

## 1. Project Overview

Tsumiki is a modular status bar / panel for Hyprland, built with
[Fabric](https://github.com/Fabric-Development/fabric) (Python + GTK3 widget
framework). Main code is Python; styles are SCSS; docs are an Astro site.

## 2. Repository Layout

| Path        | Contents                                                          |
| ----------- | ----------------------------------------------------------------- |
| `modules/`  | Core UI modules (dock, overview, notification, settings, etc.)    |
| `services/` | Background services (battery, weather, network, brightness, etc.) |
| `widgets/`  | Individual widget implementations                                 |
| `shared/`   | Reusable UI components and mixins                                 |
| `styles/`   | SCSS stylesheets and theming                                      |
| `utils/`    | Utility functions, config management, helpers                     |
| `docs/`     | Astro-based documentation site                                    |
| `tests/`    | Test suite                                                        |
| `assets/`   | Static assets (icons, images, i18n, emoji, etc.)                  |

## 3. Key Files

- `main.py` — entry point
- `pyproject.toml` — Python project metadata, targets Python 3.12 style checks
- `config.toml` — configuration example / user config
- `tsumiki.schema.json` — configuration schema (source of truth for config shape)
- `Justfile` — task recipes

## 4. Setup, Build & Test Commands

```bash
./tsumiki.sh -setup          # install/setup dependencies (uv sync)
./tsumiki.sh -start           # run the app
just --list                 # list all available task recipes
uv run python -m unittest discover tests -q   # run the test suite
cd docs && pnpm install && pnpm build   # build the docs site
fabric-cli gs GtkLayerShell-0.1 Playerctl-2.0 NM-1.0  # regenerate gi stubs
```

The following are **one-off/maintainer commands** — run only when explicitly
requested, never as a side effect of an unrelated change:

- `./install.sh` (system-level bootstrap install)
- `uv lock` (regenerates the locked dependency set in `uv.lock`)

## 5. Guardrails

- Do not run `./install.sh`, `uv lock`, or any destructive/system-modifying
  command unless the user explicitly asks for it.
- Do not revert user changes unless explicitly asked.
- Do not edit generated files (docs build output, stub files from
  `fabric-cli gs`) directly — regenerate them via their command instead.
- `tsumiki.schema.json` is the source of truth for config shape. Never let
  `config.toml` or `utils/config.py` drift from it silently — update all three
  together.
- Don't commit, push, or open a PR unless asked to.
- When in doubt about scope, prefer the smaller change and ask.

## 6. Before Starting Work

- Confirm whether the task is a **feature, bugfix, or refactor**.
- Check whether it touches the **public config schema** (`tsumiki.schema.json`).
- Decide whether it needs **new tests** (default: yes for any new logic or a
  bugfix with a reproduction case — see §14).
- Decide whether it needs **doc updates** (README, docs site, or schema).
- For unfamiliar areas, skim `README.md`, `CONTRIBUTING.md`, and `doc.md` first.
- Plan to run `ruff` + the test suite before finishing (see §14).

## 7. Editing Conventions

- Prefer small, focused changes over broad rewrites.
- Keep style consistent with the surrounding code.
- Prefer refactors that reduce duplication and nested branching.
- Before touching popup, dock, notification, OSD, or settings UI code, check
  `shared/` for an existing helper first — don't reimplement.
- Settings UI is large and repetitive; prefer generic builders over copy-paste.
- Ruff is enabled — keep imports clean and avoid obvious lint noise.
- Use ASCII in code, comments, and identifiers unless the file already uses
  Unicode. This does **not** apply to intentional UI glyphs (e.g. Nerd Font /
  emoji icons in widget config defaults) — those are a design choice, not a
  style violation.

Architecture notes worth knowing before editing:

- Popup logic is centralized in `shared/popup.py`.
- Lazy widget loading happens in `modules/bar.py`.

## 8. Code Review Checklist

1. **Conventions** — structure, naming, and patterns match the rest of the repo.
2. **Integration** — minimal coupling, proper separation of concerns.
3. **Maintainability** — readable, documented, testable.
4. **Schema alignment** — respects `tsumiki.schema.json`.

## 9. Common Tasks

| Task              | Approach                                             |
| ----------------- | ---------------------------------------------------- |
| Add new widget    | See §10                                              |
| Add new module    | See §11                                              |
| Add new service   | Create in `services/`, register in `main.py`         |
| Add config option | Update schema, add to `utils/config.py`, update docs |
| Style changes     | Edit relevant SCSS, test theme variants              |
| Fix UI bug        | See §13                                              |

## 10. Adding a New Widget (panel-based, toggleable)

Widgets live in `widgets/` and are typically panel buttons that open popovers
or show quick info.

**Step 1 — Widget file** (`widgets/my_widget.py`):

```python
from fabric.widgets.box import Box
from fabric.widgets.label import Label

from shared.mixins import PopoverMixin
from shared.widget_container import ButtonWidget
from utils.widget_utils import nerd_font_icon


class MyWidgetMenu(Box):
    """Popover content."""

    def __init__(self, parent=None, **kwargs):
        super().__init__(
            name="my-widget-menu",
            orientation="v",
            spacing=8,
            **kwargs,
        )
        self._parent = parent
        self.children = [Label(label="Menu content")]

    def close(self, *_):
        if self._parent:
            self._parent.hide_popover()


class MyWidget(ButtonWidget, PopoverMixin):
    """Panel widget."""

    def __init__(self, **kwargs):
        super().__init__(name="my_widget", **kwargs)

        self.container_box.add(
            nerd_font_icon(
                icon=self.config.get("icon", "📦"),
                props={"style_classes": ["panel-font-icon"]},
            )
        )

        if self.config.get("tooltip", True) and self.tooltips_enabled:
            self.set_tooltip_text("My Widget")

        self.setup_popover(lambda: MyWidgetMenu(parent=self))
```

**Step 2 — Bar layout** (`config.toml`):

```toml
[layout]
bar = [
    # ... existing widgets ...
    "my_widget",
]

[widgets.my_widget]
enabled = true
icon = "📦"
tooltip = true
```

**Step 3 — Config schema** (`tsumiki.schema.json`, under `widgets`):

```json
"my_widget": {
  "type": "object",
  "properties": {
    "enabled": {"type": "boolean", "default": true},
    "icon": {"type": "string", "default": "📦"},
    "tooltip": {"type": "boolean", "default": true}
  }
}
```

**Step 4 — Styling** (`styles/_my_widget.scss`, imported via `@use` in
`styles/main.scss`):

```scss
#my-widget-menu {
  padding: 12px;
}

#my-widget-menu-label {
  color: #ffffff;
  font-size: 12px;
}
```

Follow the GTK3 CSS rules in §12 (`text-align`, `margin: auto`, `transition`,
etc. are not supported — use `h_align="center"` in Python instead).

## 11. Adding a New Module (standalone overlay/popup)

Modules are top-level windows (overlays, popups, full panels) — e.g.
notification, overview, dock, desktop_clock.

**Step 1 — Service** (`services/my_module.py`, only if the module manages state):

```python
from fabric.core.service import Signal
from fabric.utils import GLib, logger

from services.base import SingletonService


class MyModuleService(SingletonService):
    @Signal
    def updated(self) -> None:
        """Signal emitted on state change."""

    def __init__(self):
        super().__init__()
        self.state = "idle"

    def do_something(self):
        self.state = "active"
        self.emit("updated")
        logger.info("[MyModule] State updated")


my_module_service = MyModuleService()
```

**Step 2 — Widget** (`widgets/my_module.py`, or `modules/my_module.py` if it's
complex enough to warrant it):

```python
from fabric.widgets.box import Box
from fabric.widgets.label import Label

from shared.mixins import PopoverMixin
from shared.widget_container import ButtonWidget
from services.my_module import my_module_service
from utils.widget_utils import nerd_font_icon


class MyModulePopover(Box):
    """Popover content for module."""

    def __init__(self, parent=None, **kwargs):
        super().__init__(
            name="my-module-popover",
            orientation="v",
            spacing=12,
            **kwargs,
        )
        self._parent = parent
        self.service = my_module_service

        self.title = Label(
            name="my-module-title",
            markup="<span font='14' color='#ffffff'>My Module</span>",
        )

        self.children = [self.title]
        self.service.connect("updated", self._on_update)

    def _on_update(self, *_):
        pass

    def close(self, *_):
        if self._parent:
            self._parent.hide_popover()


class MyModuleWidget(ButtonWidget, PopoverMixin):
    """Panel button for module."""

    def __init__(self, **kwargs):
        super().__init__(name="my_module", **kwargs)

        self.container_box.add(
            nerd_font_icon(
                icon=self.config.get("icon", "🎯"),
                props={"style_classes": ["panel-font-icon"]},
            )
        )

        if self.config.get("tooltip", True) and self.tooltips_enabled:
            self.set_tooltip_text("My Module")

        self.setup_popover(lambda: MyModulePopover(parent=self))
```

**Step 3 — Register in `main.py`:**

```python
# After other modules
if module_options.get("my_module", {}).get("enabled", False):
    from widgets.my_module import MyModuleWidget
    # If it's a panel widget, it's auto-loaded via layout
    # If it's a standalone overlay, add window:
    # app.add_window(MyModuleWindow(widget_config))
```

**Step 4 — Config schema** (`tsumiki.schema.json`, under `modules`):

```json
"my_module": {
  "type": "object",
  "properties": {
    "enabled": {"type": "boolean", "default": false},
    "anchor": {
      "type": "string",
      "enum": ["center", "top-right", "bottom-left", ...],
      "default": "center"
    },
    "layer": {
      "type": "string",
      "enum": ["top", "overlay", "bottom", "background"],
      "default": "overlay"
    }
  }
}
```

**Step 5 — Config entry** (`config.toml`):

```toml
[modules.my_module]
enabled = false
anchor = "center"
layer = "overlay"
```

**Step 6 — Styling** (`styles/_my_module.scss`, always nested to avoid global
selectors, imported via `@use` in `styles/main.scss`):

```scss
#my-module {
  background-color: rgba(40, 40, 50, 0.95);
  border-radius: 16px;
  padding: 16px;
  border: 1px solid rgba(200, 200, 220, 0.2);
}

#my-module-popover {
  padding: 12px;
}

#my-module-title {
  color: #ffffff;
  font-size: 14px;
}
```

Follow the GTK3 CSS rules in §12.

**Step 7 — Sanity check:**

```bash
python3 -c "from services.my_module import my_module_service; print('OK: service')"
python3 -c "from widgets.my_module import MyModuleWidget; print('OK: widget')"
```

## 12. GTK/Fabric Best Practices

**Lifecycle & threading:**

- Keep UI updates on the main thread only; push heavy work to background and
  return via `GLib` idle/timeout callbacks.
- Prefer signal-driven updates over polling; if polling is required, store
  timer IDs and stop them on destroy/unmap.
- Avoid duplicate signal connections; guard repeated setup paths and lifecycle
  re-entry.
- Always clean up on destroy: signal handlers, timers, async callbacks,
  subprocess readers.
- Never block GTK callbacks with synchronous shell/process operations.

**Rendering & performance:**

- Use fallback labels/icons for missing services or unavailable devices.
- Avoid rebuilding full widget trees for small state changes; update existing
  widgets in place.
- Keep widget hierarchy shallow and avoid expensive style churn in hot paths.
- Keep service state logic separate from rendering logic for easier testing
  and safer refactors.
- Debounce noisy event streams to limit redundant relayout/repaint work.

**GTK3 CSS (SCSS) rules:**

- Only use properties [GTK3 CSS supports](https://docs.gtk.org/gtk3/css-properties.html).
- Not supported — do not use: `text-align`, `align-items`, `justify-content`,
  `margin: auto`.
- `transition` and `animation`/`@keyframes` **are** supported by GTK3 (they are
  documented in the official CSS properties table).
- To center a label, use `h_align="center"` in Python, not CSS.
- To center a box, use the `h_align="center"` Python property, not CSS.

## 13. Bug-Fixing Checklist

- Validate the touched file against existing error checks if available.
- If a change affects shared state, check all call sites before editing.
- If a refactor touches UI lifecycle code, watch for stale handlers,
  duplicate timers, and destroy/cleanup paths (see §12).
- If a change touches config schema, update `tsumiki.schema.json`, `utils/config.py`,
  and `config.toml` examples in sync.
- Add a regression test when the bug has a clear reproduction case (see §14).

## 14. Definition of Done — Run After EVERY Feature, Bugfix, or Refactor

A task is **not complete** until the checks below pass. Run them every time
one feature or bugfix is finished — not just at the end of a large batch.

```bash
# 1. Lint Python code — REQUIRED after every change
uv run ruff check .

# 2. Run the test suite
uv run python -m unittest discover tests -q

# 3. Compile SCSS (only if styles were modified)
sass styles/main.scss ~/tmp/style.css --no-source-map

# 4. Run pre-commit hooks
prek run --all-files
```

- **Ruff**: Must pass before finishing — no exceptions. Fix any lint errors
  and re-run until clean.
- **Tests**:
  - All existing tests must pass.
  - **Add tests whenever possible.** Default to writing a unit/regression test
    for any new functionality or a bugfix with a clear reproduction case; a
    fix without a test is incomplete. UI-only changes with no testable logic
    may skip adding tests, but state that explicitly.
  - Follow `tests/` conventions: plain `unittest`, mock services/DBus/GTK
    rather than requiring a display (see `tests/test_functions.py`,
    `tests/test_notification_service.py`, `tests/test_mpris.py`).
- **SCSS compilation**: Verify styles compile without errors; this catches
  syntax issues, undefined variables, and import problems.
- **Pre-commit**: All hooks must pass; fix any issues flagged by hooks
  before finishing.

If any check fails, fix the issue and re-run until all pass. Do not mark the
task done while checks are failing.

## 15. Architecture Notes

- Configuration is hot-reloadable via `utils/config_watcher.py`.
- Themes are generated dynamically (see `services/matugen.py`).
- DBus is used for system integration (`utils/dbus_helper.py`).
- Internationalization is via JSON files in `assets/i18n/`.

### 15.1. Indexed Widget References with `id` Support

Four special widget types support `@type:id` references in the layout:

| Layout reference  | Config key                                | Collection path                                     |
| ----------------- | ----------------------------------------- | --------------------------------------------------- |
| `@collapsible:`   | `[[collapsible_groups]]`                  | `parsed_data.collapsible_groups[]`                  |
| `@group:`         | `[[widget_groups]]`                       | `parsed_data.widget_groups[]`                       |
| `@custom_button:` | `[[widgets.custom_button_group.buttons]]` | `parsed_data.widgets.custom_button_group.buttons[]` |
| `@custom_widget:` | `[[widgets.custom_widget]]`               | `parsed_data.widgets.custom_widget[]`               |

**Referencing syntax:**

- Numeric index (backward compatible): `@collapsible:0`, `@group:1`, `@custom_button:0`, `@custom_widget:0`
- String id: `@collapsible:utility-tools`, `@group:workspaces-group`, `@custom_button:firefox`, `@custom_widget:volume`

**Config example:**

```toml
[[collapsible_groups]]
id = "utility-tools"
widgets = ["ocr", "screenshot"]

[[widget_groups]]
id = "workspaces-group"
widgets = ["workspaces", "window_title"]

[[widgets.custom_widget]]
id = "volume"
exec = "pamixer --get-volume"

[[widgets.custom_button_group.buttons]]
id = "firefox"
command = "firefox"
```

**Implementation layers (all must be kept in sync):**

1. **Schema** (`tsumiki.schema.json`): Patterns use `^@type:[\\w-]+$` to accept both numeric and string ids. Each collection item has an optional `"id"` string property.
2. **Python validation** (`utils/functions.py` and `utils/validation.py`): `_validate_indexed_reference()` checks `identifier.isdigit()` first for backward compat, then falls back to id lookup for supported collection names.
3. **Runtime resolution** (`utils/widget_factory.py`): `IndexedWidgetHelper.validate_and_get_index()` does generic id lookup for all types without collection-name restriction.
4. **TypedDict** (`utils/widget_settings.py`): Each indexed type's TypedDict includes an optional `"id": str` field.
5. **Config examples** (`config.toml`, `example/config.toml`): Should include `id` fields in collection items and use string references in layout sections.

**When adding `id` support to a new type, you must update all 5 layers.**

## 16. gi.repository Type Stubs

`gi.repository` imports lack type checking by default. Stubs are generated
via `gengir` (see the `fabric-cli gs ...` command in §4). More detail:
https://fabric-development.github.io/fabric-wiki/installing-stubs.html

## 17. Assistant Behavior

**Communication:**

- Be concise — respect token budgets; prioritize clarity over elaboration.
- Ground answers in code inspection, not assumptions.
- Show concrete code snippets rather than descriptions.
- Use progressive disclosure — start simple, add detail only if needed.
- Challenge assumptions — point out issues in plans or designs plainly.
- Be direct and professional. Do not add pleasantries, filler, or sign-offs to the end of responses.

**Tools:**

- Use `pylance` for Python analysis.
- Use branch/commit tools for git workflows (but don't commit/push unasked —
  see §5).
- Use the `review` skill for PR reviews.
- Use the `diagnose` skill for bug investigations.
- Use the `tdd` skill for feature development.
- Use the `brainstorm` skill for design discussions.


**Testing**

- Write tests after adding new production behavior, and always when adding or changing Sheldon-compatibility behavior (command names, TOML shape, lock format, rendered output).
- Prefer table-driven tests and golden-file comparisons for renderer and lock output, consistent with existing tests in each package.
- Add a regression test for every bug fix before considering the fix done.

## Best practices

**Code review**

- Re-read your own diff before finishing. Remove debug output, dead code, and speculative abstractions.
- Keep diffs small and single-purpose. If a change mixes concerns, split it.
- Prefer boring, explicit code over cleverness. Optimize only when a benchmark or profile shows a problem.

**Maintenance**

- Review and refactor code regularly to maintain clarity, simplicity, and adherence to established patterns.
- Keep comments concise and valuable: state why, not what. Run the `unslop` skill when writing or rewriting comments.
- Run the `brainstorming` skill to generate and evaluate ideas before implementing them in code.
- Use sub-agent-driven development whenever working on multiple independent tasks.


## Commit standards

- Use [Conventional Commits](https://www.conventionalcommits.org/): `<type>(<scope>): <summary>`. Use `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, or `revert`.
- Write the subject in the imperative, under 72 characters, with no trailing period. Explain body details as what and why, not how.
- Do not commit unless explicitly requested.
- Keep each commit and PR scoped to a single logical change; call out any Sheldon-compatibility implication explicitly in the description.
- Never append a footer to a commit message:
  - No `Co-Authored-By`, no `Signed-off-by` unless requested, no "Generated with", no AI tool or model names, no attribution lines of any kind.
- The same rule applies to all generated text: PR descriptions, issue reports, docs, and replies must not carry footers, signatures, or AI attribution.

## Workflow

- Run the checks in Definition of done and confirm their output before claiming any change is complete.
- Do not commit changes unless explicitly requested.
