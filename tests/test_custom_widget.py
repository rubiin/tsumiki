"""Tests for ``widgets/custom_widget.py`` output formatting.

Command output is untrusted text: a percentage icon table arrives in whatever
order the user wrote it, and a tooltip may hold anything the command printed.
"""

import json
import unittest
from unittest import mock

from widgets.custom_widget import (
    CustomWidgetExecutor,
    CustomWidgetPresenter,
    _resolve_icon,
)


def make_presenter(
    *,
    format_icons: dict | None = None,
    tooltip: bool = True,
    tooltip_format: str | None = None,
) -> CustomWidgetPresenter:
    label, icon, host = mock.Mock(), mock.Mock(), mock.Mock()
    module_config: dict = {"label_format": "{value}", "tooltip": tooltip}
    if format_icons is not None:
        module_config["format_icons"] = format_icons
    if tooltip_format is not None:
        module_config["tooltip_format"] = tooltip_format
    return CustomWidgetPresenter(module_config, label, icon, host), host


class LabelFormatTest(unittest.TestCase):
    """``{value}`` is the command output; nothing else is a placeholder."""

    def _label_for(self, config: dict, output: str = "50") -> str:
        label, icon, host = mock.Mock(), mock.Mock(), mock.Mock()
        presenter = CustomWidgetPresenter(config, label, icon, host)
        presenter._handle_text_output(output)
        return label.set_label.call_args[0][0]

    def test_value_is_replaced_with_the_output(self):
        self.assertEqual("50%", self._label_for({"label_format": "{value}%"}))

    def test_value_keeps_the_literal_text_around_it(self):
        self.assertEqual("vol 50 ", self._label_for({"label_format": "vol {value} "}))

    def test_value_repeats_for_each_occurrence(self):
        self.assertEqual("50/50", self._label_for({"label_format": "{value}/{value}"}))

    def test_no_label_format_shows_the_output(self):
        self.assertEqual("50", self._label_for({}))

    def test_an_unknown_placeholder_shows_the_raw_output(self):
        self.assertEqual("50", self._label_for({"label_format": "{volume}"}))

    def test_the_positional_placeholder_is_not_one(self):
        self.assertEqual("50", self._label_for({"label_format": "{}%"}))

    def test_the_removed_format_key_no_longer_configures_the_label(self):
        self.assertEqual("50", self._label_for({"format": "50%"}))

    def test_the_value_placeholder_reaches_json_output(self):
        label, icon, host = mock.Mock(), mock.Mock(), mock.Mock()
        presenter = CustomWidgetPresenter(
            {"label_format": "vol {value}"}, label, icon, host
        )

        presenter._handle_json_output(json.dumps({"text": "80"}))

        label.set_label.assert_called_once_with("vol 80")

    def test_max_length_still_applies_after_formatting(self):
        config = {"label_format": "vol {value}", "max_length": 5}
        self.assertEqual("vol 5…", self._label_for(config))

    def test_min_length_still_pads_after_formatting(self):
        config = {"label_format": "{value}", "min_length": 4}
        self.assertEqual("50  ", self._label_for(config))


class TooltipFormatTest(unittest.TestCase):
    """``tooltip_format`` takes the same ``{value}`` as the label."""

    def _tooltip_for(self, tooltip_format: str, output: str = "50") -> str:
        presenter, host = make_presenter(tooltip_format=tooltip_format)

        presenter._handle_text_output(output)

        return host.set_tooltip_text.call_args[0][0]

    def test_value_is_replaced_with_the_output(self):
        self.assertEqual("vol: 50", self._tooltip_for("vol: {value}"))

    def test_a_format_with_no_placeholder_leaves_the_output_alone(self):
        self.assertEqual("50", self._tooltip_for("vol"))

    def test_no_tooltip_format_leaves_the_output_alone(self):
        presenter, host = make_presenter()

        presenter._handle_text_output("50")

        host.set_tooltip_text.assert_called_once_with("50")


class StaticIconTest(unittest.TestCase):
    """The widget's glyph is ``format_icons.default``; the ``icon`` key is gone."""

    def test_the_default_format_icon_is_the_static_glyph(self):
        self.assertEqual("X", _resolve_icon({"format_icons": {"default": "X"}}))

    def test_no_format_icons_means_no_glyph(self):
        self.assertIsNone(_resolve_icon({}))

    def test_the_removed_icon_key_is_not_a_glyph(self):
        self.assertIsNone(_resolve_icon({"icon": "X"}))

    def test_a_widget_without_a_default_gets_no_glyph(self):
        self.assertIsNone(_resolve_icon({"format_icons": {"75": "A"}}))


class FormatIconThresholdTest(unittest.TestCase):
    """The highest matching threshold wins, not the first one in dict order."""

    def _icon_for(self, format_icons, percentage, alt=None):
        presenter, _ = make_presenter(format_icons=format_icons)
        presenter._update_icon(alt, percentage)
        return (
            presenter._icon.set_label.call_args[0][0]
            if (presenter._icon.set_label.called)
            else None
        )

    def test_the_highest_matching_threshold_wins(self):
        icons = {"75": "A", "50": "B"}
        self.assertEqual("A", self._icon_for(icons, 80))

    def test_the_matching_threshold_wins_regardless_of_write_order(self):
        icons = {"50": "B", "75": "A"}
        self.assertEqual("A", self._icon_for(icons, 80))

    def test_a_lower_percentage_falls_to_the_lower_threshold(self):
        self.assertEqual("B", self._icon_for({"75": "A", "50": "B"}, 60))

    def test_a_percentage_below_every_threshold_sets_no_icon(self):
        self.assertIsNone(self._icon_for({"75": "A", "50": "B"}, 10))

    def test_an_exact_threshold_matches(self):
        self.assertEqual("A", self._icon_for({"75": "A", "50": "B"}, 75))

    def test_a_named_alt_beats_the_thresholds(self):
        icons = {"75": "A", "50": "B", "muted": "M"}
        self.assertEqual("M", self._icon_for(icons, 80, alt="muted"))

    def test_non_numeric_keys_are_not_thresholds(self):
        icons = {"default": "D", "50": "B"}
        self.assertEqual("B", self._icon_for(icons, 80))

    def test_no_icon_without_a_format_icons_table(self):
        self.assertIsNone(self._icon_for({}, 80))


class TooltipOutputTest(unittest.TestCase):
    """Raw command output is not Pango markup; '&' or '<' empties the tooltip."""

    def test_a_tooltip_is_applied_as_plain_text(self):
        presenter, host = make_presenter()

        presenter._handle_json_output(json.dumps({"text": "80%", "tooltip": "A & B"}))

        host.set_tooltip_text.assert_called_once_with("A & B")
        host.set_tooltip_markup.assert_not_called()

    def test_markup_characters_survive_intact(self):
        presenter, host = make_presenter()

        presenter._handle_json_output(
            json.dumps({"text": "x", "tooltip": "<b>bold</b> & <i>it</i>"})
        )

        host.set_tooltip_text.assert_called_once_with("<b>bold</b> & <i>it</i>")

    def test_the_tooltip_format_still_applies(self):
        presenter, host = make_presenter(tooltip_format="vol: {value}")

        presenter._handle_json_output(json.dumps({"text": "x", "tooltip": "50"}))

        host.set_tooltip_text.assert_called_once_with("vol: 50")

    def test_a_disabled_tooltip_sets_nothing(self):
        presenter, host = make_presenter(tooltip=False)

        presenter._handle_json_output(json.dumps({"text": "x", "tooltip": "50"}))

        host.set_tooltip_text.assert_not_called()

    def test_an_absent_tooltip_clears_the_previous_one(self):
        presenter, host = make_presenter()

        presenter._handle_json_output(json.dumps({"text": "x", "tooltip": "50"}))
        presenter._handle_json_output(json.dumps({"text": "y"}))

        host.set_tooltip_text.assert_called_with("")

    def test_plain_output_also_uses_plain_text(self):
        presenter, host = make_presenter()

        presenter._handle_text_output("1 < 2 & 3")

        host.set_tooltip_text.assert_called_once_with("1 < 2 & 3")


class IntervalUnitsTest(unittest.TestCase):
    """``interval`` is milliseconds, so the repeater gets the value unchanged."""

    def test_the_interval_reaches_the_repeater_as_milliseconds(self):
        executor = CustomWidgetExecutor(
            {"exec": "echo hi", "interval": 2500}, mock.Mock()
        )
        with (
            mock.patch("widgets.custom_widget.exec_shell_command_async"),
            mock.patch("widgets.custom_widget.invoke_repeater") as repeater,
        ):
            executor.start()

        repeater.assert_called_once_with(2500, executor._periodic_execute)


class ClickOnlyButtonTest(unittest.TestCase):
    """A widget with no ``exec`` is a button, not a misconfigured widget.

    This is what replaced ``[[widgets.custom_buttons]]``: an icon plus the
    command to run on click.
    """

    def _warned(self, config: dict) -> bool:
        logger = mock.Mock()
        with mock.patch("widgets.custom_widget.logger", logger):
            CustomWidgetExecutor(config, mock.Mock()).start()
        return logger.warning.called

    def test_a_click_handler_alone_does_not_warn(self):
        self.assertFalse(self._warned({"on_click": "spotify"}))

    def test_a_click_only_button_takes_its_glyph_from_format_icons(self):
        config = {"on_click": "spotify", "format_icons": {"default": ""}}

        self.assertEqual("", _resolve_icon(config))

    def test_no_exec_and_no_handler_still_warns(self):
        self.assertTrue(self._warned({}))

    def test_nothing_runs_without_an_exec(self):
        with mock.patch("widgets.custom_widget.exec_shell_command_async") as run:
            CustomWidgetExecutor({"on_click": "spotify"}, mock.Mock()).start()

        run.assert_not_called()


class StaticTooltipTest(unittest.TestCase):
    """``tooltip_text`` shows without any command output to carry one."""

    def _tooltip(self, config: dict) -> str | None:
        label, icon, host = mock.Mock(), mock.Mock(), mock.Mock()
        CustomWidgetPresenter(config, label, icon, host)
        if not host.set_tooltip_text.called:
            return None
        return host.set_tooltip_text.call_args[0][0]

    def test_tooltip_text_is_applied(self):
        config = {"tooltip_text": "Open Spotify"}

        self.assertEqual("Open Spotify", self._tooltip(config))

    def test_no_tooltip_text_leaves_the_tooltip_alone(self):
        self.assertIsNone(self._tooltip({}))

    def test_tooltip_false_suppresses_it(self):
        config = {"tooltip_text": "Open Spotify", "tooltip": False}

        self.assertIsNone(self._tooltip(config))


class HideEmptyTextTest(unittest.TestCase):
    """``hide_empty_text`` hides the button until there is output again."""

    def _presenter(self, config: dict):
        label, icon, host = mock.Mock(), mock.Mock(), mock.Mock()
        return CustomWidgetPresenter(config, label, icon, host), host

    def test_empty_output_hides_the_widget(self):
        presenter, host = self._presenter({"hide_empty_text": True})

        presenter.handle_output("")

        host.set_visible.assert_called_once_with(False)

    def test_whitespace_output_hides_the_widget(self):
        presenter, host = self._presenter({"hide_empty_text": True})

        presenter.handle_output("   \n")

        host.set_visible.assert_called_once_with(False)

    def test_output_shows_the_widget_again(self):
        presenter, host = self._presenter({"hide_empty_text": True})

        presenter.handle_output("")
        presenter.handle_output("50")

        self.assertEqual(
            [mock.call(False), mock.call(True)], host.set_visible.call_args_list
        )

    def test_default_leaves_visibility_alone(self):
        presenter, host = self._presenter({})

        presenter.handle_output("")

        host.set_visible.assert_not_called()

    def test_the_hyphenated_alias_is_accepted(self):
        presenter, host = self._presenter({"hide-empty-text": True})

        presenter.handle_output("")

        host.set_visible.assert_called_once_with(False)


class ExecIfTest(unittest.TestCase):
    """``exec_if`` gates every run of ``exec`` on its exit status."""

    def _run_condition(self, exit_ok: bool, config: dict | None = None):
        config = config or {"exec": "echo hi", "exec_if": "which pamixer"}
        on_ok = mock.Mock()
        executor = CustomWidgetExecutor(config, mock.Mock())
        proc = mock.Mock()

        def fake_wait_check_async(_cancellable, callback):
            callback(proc, mock.Mock())

        proc.wait_check_async.side_effect = fake_wait_check_async
        if not exit_ok:
            proc.wait_check_finish.side_effect = Exception("exit 1")
        with mock.patch("widgets.custom_widget.Gio") as gio:
            gio.Subprocess.new.return_value = proc
            executor._run_condition(on_ok)
        return on_ok

    def test_a_zero_exit_runs_the_command(self):
        self.assertTrue(self._run_condition(exit_ok=True).called)

    def test_a_non_zero_exit_skips_the_command(self):
        self.assertFalse(self._run_condition(exit_ok=False).called)

    def test_a_failing_exec_if_itself_skips_the_command(self):
        on_ok = mock.Mock()
        executor = CustomWidgetExecutor(
            {"exec": "echo hi", "exec_if": "not-a-real-command-xyz"}, mock.Mock()
        )
        with mock.patch("widgets.custom_widget.Gio") as gio:
            gio.Subprocess.new.side_effect = Exception("spawn failed")
            executor._run_condition(on_ok)

        on_ok.assert_not_called()

    def test_exec_if_gates_execute_once(self):
        config = {"exec": "echo hi", "exec_if": "which pamixer"}
        proc = mock.Mock()

        def fake_wait_check_async(_cancellable, callback):
            callback(proc, mock.Mock())

        proc.wait_check_async.side_effect = fake_wait_check_async
        proc.wait_check_finish.side_effect = Exception("exit 1")
        with (
            mock.patch("widgets.custom_widget.Gio") as gio,
            mock.patch("widgets.custom_widget.exec_shell_command_async") as run,
        ):
            gio.Subprocess.new.return_value = proc
            CustomWidgetExecutor(config, mock.Mock()).execute_once()

        run.assert_not_called()

    def test_the_hyphenated_alias_is_accepted(self):
        config = {"exec": "echo hi", "exec-if": "which pamixer"}
        executor = CustomWidgetExecutor(config, mock.Mock())

        self.assertEqual("which pamixer", executor._exec_if)


if __name__ == "__main__":
    unittest.main()
