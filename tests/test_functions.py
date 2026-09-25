import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from utils import functions
from utils.functions import (
    celsius_to_fahrenheit,
    check_if_day,
    convert_bytes,
    convert_seconds_to_milliseconds,
    convert_to_12hr_format,
    convert_to_percent,
    copy_to_clipboard,
    deep_merge,
    exclude_keys,
    extract_body_image,
    extract_one_time_code,
    find_executable,
    flatten_dict,
    format_relative_timestamp,
    format_seconds_to_hours_minutes,
    get_relative_time,
    is_valid_gjs_color,
    mix_colors,
    parse_markup,
    read_json_file,
    rgb_to_css,
    rgb_to_hex,
    tint_color,
    unique_list,
    write_json_file,
)
from utils.validation import (
    validate_config_enums,
)


class FunctionsTest(unittest.TestCase):
    """Test suite for utility functions in the utils module."""

    def test_celsius_to_fahrenheit(self):
        self.assertAlmostEqual(celsius_to_fahrenheit(0), 32)
        self.assertAlmostEqual(celsius_to_fahrenheit(100), 212)
        self.assertAlmostEqual(celsius_to_fahrenheit(-40), -40)

    def test_deep_merge(self):
        target = {"a": 1, "b": {"x": 10, "y": 20}}
        data = {"b": {"y": 30, "z": 40}, "c": 3}
        merged = deep_merge(data, target)
        expected = {"a": 1, "b": {"x": 10, "y": 30, "z": 40}, "c": 3}
        self.assertEqual(merged, expected)

    def test_flatten_dict(self):
        d = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
        flat = flatten_dict(d)
        expected = {"a": 1, "b-c": 2, "b-d-e": 3}
        self.assertEqual(flat, expected)

    def test_exclude_keys(self):
        d = {"a": 1, "b": 2, "c": 3}
        filtered = exclude_keys(d, ["b"])
        self.assertEqual(filtered, {"a": 1, "c": 3})

    def test_format_seconds_to_hours_minutes(self):
        self.assertEqual(format_seconds_to_hours_minutes(0), "0 h 00 min")
        self.assertEqual(
            format_seconds_to_hours_minutes(59), "0 h 00 min"
        )  # less than 1 min
        self.assertEqual(
            format_seconds_to_hours_minutes(60), "0 h 01 min"
        )  # exactly 1 min
        self.assertEqual(
            format_seconds_to_hours_minutes(90), "0 h 01 min"
        )  # 1 min 30 sec rounds down to 1 min
        self.assertEqual(
            format_seconds_to_hours_minutes(3600), "1 h 00 min"
        )  # exactly 1 hour
        self.assertEqual(
            format_seconds_to_hours_minutes(3661), "1 h 01 min"
        )  # 1 hour 1 min 1 sec rounds down to 1 h 01 min

    def test_convert_bytes(self):
        # 1024 bytes = 1 KB
        self.assertEqual(convert_bytes(1024, "kb"), "1.0KB")
        # 1048576 bytes = 1 MB
        self.assertEqual(convert_bytes(1024**2, "mb"), "1.0MB")
        # 1073741824 bytes = 1 GB
        self.assertEqual(convert_bytes(1024**3, "gb"), "1.0GB")

        # Test formatting with 2 decimal places
        self.assertEqual(convert_bytes(123456789, "mb", ".2f"), "117.74MB")

    def test_check_if_day(self):
        # Format: "%I:%M %p" e.g. "06:00 AM"
        sunrise = "06:00 AM"
        sunset = "06:00 PM"

        self.assertTrue(check_if_day(sunrise, sunset, "07:00 AM"))
        self.assertFalse(check_if_day(sunrise, sunset, "05:00 AM"))
        self.assertFalse(check_if_day(sunrise, sunset, "07:00 PM"))

        # Case when sunset < sunrise (e.g. polar regions)
        self.assertTrue(check_if_day("10:00 PM", "06:00 AM", "11:00 PM"))
        self.assertFalse(check_if_day("10:00 PM", "06:00 AM", "07:00 AM"))

    def test_convert_to_12hr_format(self):
        self.assertEqual(convert_to_12hr_format("0"), "12:00 AM")
        self.assertEqual(convert_to_12hr_format("300"), "3:00 AM")
        self.assertEqual(convert_to_12hr_format("1200"), "12:00 PM")
        self.assertEqual(convert_to_12hr_format("2100"), "9:00 PM")

    def test_unique_list(self):
        lst = [1, 2, 2, 3, 4, 4, 5]
        result = unique_list(lst)
        self.assertEqual(sorted(result), [1, 2, 3, 4, 5])

    def test_get_relative_time(self):
        self.assertEqual(get_relative_time(0), "now")
        self.assertEqual(get_relative_time(1), "1 minute ago")
        self.assertEqual(get_relative_time(59), "59 minutes ago")
        self.assertEqual(get_relative_time(60), "1 hour ago")
        self.assertEqual(get_relative_time(120), "2 hours ago")
        self.assertEqual(get_relative_time(1440), "1 day ago")
        self.assertEqual(get_relative_time(2880), "2 days ago")

    def test_convert_to_percent(self):
        self.assertEqual(convert_to_percent(50, 100), 50)
        self.assertEqual(convert_to_percent(1, 3, is_int=False), (1 / 3) * 100)
        self.assertEqual(convert_to_percent(0, 0), 0)

    def test_is_valid_gjs_color(self):
        # Assuming NAMED_COLORS is a set or list of color names
        for name in ["red", "blue"]:
            self.assertTrue(is_valid_gjs_color(name))
        self.assertTrue(is_valid_gjs_color("#fff"))
        self.assertTrue(is_valid_gjs_color("#ffffff"))
        self.assertTrue(is_valid_gjs_color("rgb(255, 0, 0)"))
        self.assertTrue(is_valid_gjs_color("rgba(255, 0, 0, 0.5)"))
        self.assertTrue(is_valid_gjs_color("rgb(256, 0, 0)"))
        self.assertFalse(is_valid_gjs_color("invalidcolor"))

    def test_uptime(self):
        # uptime() lives in utils/widget_utils (needs psutil/fabric widgets),
        # so import it lazily and skip when those deps aren't available.
        try:
            from utils.widget_utils import uptime
        except ImportError:
            self.skipTest("widget_utils dependencies unavailable")
        # Just test format, it should be HH:MM
        result = uptime()
        self.assertRegex(result, r"^\d{2}:\d{2}$")

    def test_convert_seconds_to_milliseconds(self):
        self.assertEqual(convert_seconds_to_milliseconds(1), 1000)
        self.assertEqual(convert_seconds_to_milliseconds(0), 0)
        self.assertEqual(convert_seconds_to_milliseconds(2), 2000)

    def test_rgb_to_hex(self):
        self.assertEqual(rgb_to_hex((255, 0, 0)), "#ff0000")
        self.assertEqual(rgb_to_hex((0, 255, 0)), "#00ff00")
        self.assertEqual(rgb_to_hex((0, 0, 255)), "#0000ff")
        self.assertEqual(rgb_to_hex((255, 255, 255)), "#ffffff")
        self.assertEqual(rgb_to_hex((0, 0, 0)), "#000000")

    def test_rgb_to_css(self):
        self.assertEqual(rgb_to_css((255, 0, 0)), "rgb(255, 0, 0)")
        self.assertEqual(rgb_to_css((0, 255, 0)), "rgb(0, 255, 0)")
        self.assertEqual(rgb_to_css((0, 0, 255)), "rgb(0, 0, 255)")

    def test_mix_colors_default_ratio(self):
        # 50% red and 50% blue should give purple-ish
        self.assertEqual(mix_colors((255, 0, 0), (0, 0, 255)), (127, 0, 127))

    def test_mix_colors_custom_ratio(self):
        # 25% red and 75% blue
        self.assertEqual(mix_colors((255, 0, 0), (0, 0, 255), ratio=0.75), (63, 0, 191))

    def test_tint_color_full_white(self):
        # Tint factor 1.0 => full white
        self.assertEqual(tint_color((100, 150, 200), 1.0), (255, 255, 255))

    def test_tint_color_no_tint(self):
        # Tint factor 0.0 => original color
        self.assertEqual(tint_color((100, 150, 200), 0.0), (100, 150, 200))

    def test_tint_color_half(self):
        # Tint factor 0.5 => halfway to white
        self.assertEqual(tint_color((0, 0, 0), 0.5), (127, 127, 127))
        self.assertEqual(tint_color((100, 100, 100), 0.5), (177, 177, 177))

    def test_validate_config_enums_rejects_invalid_value(self):
        schema_path = Path(__file__).resolve().parents[1] / "tsumiki.schema.json"

        with self.assertRaisesRegex(ValueError, r"config\.modules\.bar\.location"):
            validate_config_enums(
                {"modules": {"bar": {"location": "middle"}}}, str(schema_path)
            )


class ParseMarkupTest(unittest.TestCase):
    """Test the SwayNC-inspired markup whitelist in parse_markup()."""

    def test_plain_text_untouched(self):
        self.assertEqual(parse_markup("hello world"), "hello world")

    def test_newlines_are_flattened(self):
        self.assertEqual(parse_markup("line1\nline2"), "line1 line2")

    def test_html_is_escaped(self):
        self.assertEqual(
            parse_markup("<script>alert(1)</script> & <b>bold</b>"),
            "&lt;script&gt;alert(1)&lt;/script&gt; &amp; <b>bold</b>",
        )

    def test_whitelisted_tags_are_re_enabled(self):
        self.assertEqual(
            parse_markup("<b>b</b> <i>i</i> <u>u</u>"), "<b>b</b> <i>i</i> <u>u</u>"
        )

    def test_malformed_markup_falls_back_to_escaped(self):
        self.assertEqual(
            parse_markup("<b>unclosed <i>mess"), "&lt;b&gt;unclosed &lt;i&gt;mess"
        )

    def test_double_escaped_entities_are_unescaped(self):
        # Discord sends literal "<" pre-escaped as "&lt;"; after our own
        # escaping it would render as "&lt;" unless "&amp;" is restored to "&".
        self.assertEqual(parse_markup("&lt;b&gt;hi&lt;/b&gt;"), "&lt;b&gt;hi&lt;/b&gt;")
        self.assertEqual(parse_markup("a &amp;lt; b"), "a &amp;lt; b")


class ExtractOneTimeCodeTest(unittest.TestCase):
    """Test 2FA/OTP code detection from notification bodies."""

    def test_plain_code(self):
        self.assertEqual(extract_one_time_code("Your code is 482913"), "482913")

    def test_hyphenated_pair(self):
        self.assertEqual(extract_one_time_code("code: 123-456."), "123456")

    def test_google_prefix(self):
        self.assertEqual(
            extract_one_time_code("G-741258 is your verification code"), "741258"
        )

    def test_code_inside_markup_tags(self):
        self.assertEqual(extract_one_time_code("G-<b>741258</b>"), "741258")

    def test_no_code(self):
        self.assertIsNone(extract_one_time_code("no code here"))
        self.assertIsNone(extract_one_time_code(""))
        self.assertIsNone(extract_one_time_code("version 123 is out"))

    def test_first_match_wins(self):
        self.assertEqual(extract_one_time_code("1111 or 2222"), "1111")


class ExtractBodyImageTest(unittest.TestCase):
    """Test <img src=...> extraction from notification bodies."""

    def test_extracts_first_image_and_strips_tags(self):
        cleaned, src = extract_body_image('look <img src="/tmp/a.png" alt="x"> now')
        self.assertEqual(src, "/tmp/a.png")
        self.assertNotIn("<img", cleaned)

    def test_single_quoted_src(self):
        self.assertEqual(extract_body_image("<img src='~/b.png'>")[1], "~/b.png")

    def test_no_image(self):
        self.assertEqual(extract_body_image("just text"), ("just text", None))
        self.assertEqual(extract_body_image(""), ("", None))


class FormatRelativeTimestampTest(unittest.TestCase):
    """Test compact relative timestamp formatting (time is pinned)."""

    def test_formats(self):
        now = 1_000_000.0
        with mock.patch.object(functions.time, "time", return_value=now):
            self.assertEqual(format_relative_timestamp(None), "")
            self.assertEqual(format_relative_timestamp("garbage"), "")
            self.assertEqual(format_relative_timestamp(now), "Now")
            self.assertEqual(format_relative_timestamp(now - 90), "1m ago")
            self.assertEqual(format_relative_timestamp(now - 3 * 3600), "3h ago")
            self.assertEqual(format_relative_timestamp(now - 2 * 86400), "2d ago")
            # Millisecond input is normalized.
            self.assertEqual(format_relative_timestamp(now * 1000), "Now")


class CopyToClipboardTest(unittest.TestCase):
    """Test clipboard tool selection for both copy modes."""

    def _make_launcher(self):
        launcher = mock.Mock()
        launcher.spawnv.return_value = mock.Mock()
        return launcher

    def test_prefers_wl_copy(self):
        launcher = self._make_launcher()
        with (
            mock.patch.object(functions, "find_executable", return_value="wl-copy"),
            mock.patch.object(
                functions.Gio.SubprocessLauncher, "new", return_value=launcher
            ),
        ):
            copy_to_clipboard("123456", asynchronous=True)
        launcher.spawnv.assert_called_once_with(["wl-copy", "--type", "text/plain"])

    def test_falls_back_to_xclip(self):
        launcher = self._make_launcher()

        def find(name):
            return "xclip" if name == "xclip" else None

        with (
            mock.patch.object(functions, "find_executable", side_effect=find),
            mock.patch.object(
                functions.Gio.SubprocessLauncher, "new", return_value=launcher
            ),
        ):
            copy_to_clipboard("123456", asynchronous=True)
        launcher.spawnv.assert_called_once_with(["xclip", "-selection", "clipboard"])

    def test_no_tool_is_a_noop(self):
        with (
            mock.patch.object(functions, "find_executable", return_value=None),
            mock.patch.object(functions.Gio.SubprocessLauncher, "new") as launcher_new,
        ):
            copy_to_clipboard("123456", asynchronous=True)
        launcher_new.assert_not_called()


class FindExecutableTest(unittest.TestCase):
    """Test the TTL-cached find_executable() PATH lookup helper.

    Probe names are unique per test because the helper is wrapped in
    ``ttl_lru_cache`` (keyed on the time bucket + argument), so the shared
    cache must not leak between tests. Time is pinned to control the bucket.
    """

    def test_finds_executable_on_path(self):
        with mock.patch.object(
            functions.GLib, "find_program_in_path", return_value="/usr/bin/ss"
        ) as mock_lookup:
            self.assertEqual(find_executable("fe-found-probe"), "/usr/bin/ss")
        mock_lookup.assert_called_once_with("fe-found-probe")

    def test_missing_executable_returns_none(self):
        with mock.patch.object(
            functions.GLib, "find_program_in_path", return_value=None
        ) as mock_lookup:
            self.assertIsNone(find_executable("fe-missing-probe"))
        mock_lookup.assert_called_once_with("fe-missing-probe")

    def test_results_are_cached_within_ttl_window(self):
        with (
            mock.patch.object(
                functions.GLib, "find_program_in_path", return_value="/usr/bin/ss"
            ) as mock_lookup,
            mock.patch.object(functions.time, "time", return_value=1000.0),
        ):
            self.assertEqual(find_executable("fe-cache-probe"), "/usr/bin/ss")
            self.assertEqual(find_executable("fe-cache-probe"), "/usr/bin/ss")
        # The second call is served from the TTL cache, not PATH.
        self.assertEqual(mock_lookup.call_count, 1)

    def test_cache_expires_after_ttl_window(self):
        lookup = mock.Mock(return_value="/usr/bin/ss")
        with (
            mock.patch.object(functions.GLib, "find_program_in_path", lookup),
            mock.patch.object(functions.time, "time", return_value=1000.0),
        ):
            self.assertEqual(find_executable("fe-expiry-probe"), "/usr/bin/ss")

        # Same key, new TTL bucket, tool no longer on PATH: fresh lookup.
        lookup.return_value = None
        with (
            mock.patch.object(functions.GLib, "find_program_in_path", lookup),
            mock.patch.object(functions.time, "time", return_value=1600.0),
        ):
            self.assertIsNone(find_executable("fe-expiry-probe"))
        self.assertEqual(lookup.call_count, 2)


class ReadJsonFileTest(unittest.TestCase):
    """The shared JSON reader handles missing, invalid, and unreadable files."""

    def test_reads_json_object(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "data.json"
            payload = {"key": "café"}
            path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )

            self.assertEqual(read_json_file(str(path)), payload)

    def test_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertIsNone(read_json_file(str(Path(tmpdir) / "missing.json")))

    def test_invalid_json_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "invalid.json"
            path.write_text("not json", encoding="utf-8")

            self.assertIsNone(read_json_file(str(path)))

    def test_file_read_error_returns_none(self):
        with (
            mock.patch.object(functions.os.path, "exists", return_value=True),
            mock.patch("builtins.open", side_effect=PermissionError("denied")),
        ):
            self.assertIsNone(read_json_file("/tmp/unreadable.json"))


class WriteJsonFileTest(unittest.TestCase):
    """The JSON writer can run inline for callers that need completion."""

    def test_sync_mode_writes_before_returning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "data.json"
            payload = {"key": "value"}

            result = write_json_file(str(path), payload, sync=True)

            self.assertIsNone(result)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), payload)

    def test_default_mode_returns_a_future(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "data.json"
            payload = {"key": "value"}

            future = write_json_file(str(path), payload)
            future.result()

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), payload)


if __name__ == "__main__":
    unittest.main()
