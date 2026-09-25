import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import ClassVar

from utils.plugin_manager import PluginManager, get_plugin_manager


def _write(path: Path, content: str, name: str = "hello.py"):
    (path / name).write_text(content)


class PluginManagerTest(unittest.TestCase):
    """Test the launcher plugin loader and registry."""

    def test_loads_single_file_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = Path(tmp)
            _write(
                plugins_dir,
                "from utils.plugin_manager import LauncherPlugin, PluginResult\n"
                "class Hello(LauncherPlugin):\n"
                "    name = 'hello'\n"
                "    description = 'Say hi'\n"
                "    def handle(self, args):\n"
                "        return [PluginResult('hi ' + args)]\n",
            )
            manager = PluginManager(str(plugins_dir))
            self.assertEqual(manager.load(), 1)
            plugin = manager.get("hello")
            self.assertIsNotNone(plugin)
            self.assertEqual(plugin.handle("there")[0].title, "hi there")

    def test_aliases_and_prefix_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = Path(tmp)
            _write(
                plugins_dir,
                "from utils.plugin_manager import LauncherPlugin\n"
                "class Two(LauncherPlugin):\n"
                "    name = 'two'\n"
                "    aliases = ['t', 'tw']\n"
                "    description = 'second'\n",
            )
            manager = PluginManager(str(plugins_dir))
            manager.load()
            self.assertIs(manager.get("TWO"), manager.get("two"))
            self.assertIs(manager.get("t"), manager.get("two"))
            self.assertIs(manager.get("tw"), manager.get("two"))
            self.assertEqual([p.name for p in manager.match("t")], ["two"])
            self.assertEqual(manager.match("zzz"), [])

    def test_skips_broken_and_unrelated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = Path(tmp)
            _write(plugins_dir, "this is not python {{", name="broken.py")
            _write(
                plugins_dir,
                "class NotAPlugin:\n    pass\n",
                name="unrelated.py",
            )
            _write(plugins_dir, "", name="__init__.py")
            manager = PluginManager(str(plugins_dir))
            # No valid plugins -> 0 registered, but nothing crashes.
            self.assertEqual(manager.load(), 0)
            self.assertEqual(manager.all(), [])

    def test_package_plugin_with_relative_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = Path(tmp)
            pkg = plugins_dir / "pkgdemo"
            pkg.mkdir()
            (pkg / "core.py").write_text(
                "from utils.plugin_manager import LauncherPlugin, PluginResult\n"
                "class Pkg(LauncherPlugin):\n"
                "    name = 'pkg'\n"
                "    description = 'pkg demo'\n"
            )
            (pkg / "__init__.py").write_text("from .core import Pkg\n")
            manager = PluginManager(str(plugins_dir))
            self.assertEqual(manager.load(), 1)
            self.assertIsNotNone(manager.get("pkg"))

    def test_plugin_without_name_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = Path(tmp)
            _write(
                plugins_dir,
                "from utils.plugin_manager import LauncherPlugin\n"
                "class Nameless(LauncherPlugin):\n"
                "    description = 'no name here'\n",
            )
            manager = PluginManager(str(plugins_dir))
            self.assertEqual(manager.load(), 0)

    def test_default_debounce_is_none(self):
        from utils.plugin_manager import LauncherPlugin

        self.assertIsNone(LauncherPlugin.debounce_ms)

    def test_singleton_caches_per_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIs(get_plugin_manager(tmp), get_plugin_manager(tmp))
            with tempfile.TemporaryDirectory() as other:
                self.assertIsNot(get_plugin_manager(tmp), get_plugin_manager(other))

    def _write_two_plugins(self, plugins_dir: Path):
        _write(
            plugins_dir,
            "from utils.plugin_manager import LauncherPlugin\n"
            "class Alpha(LauncherPlugin):\n"
            "    name = 'alpha'\n"
            "    description = 'first'\n",
            name="alpha.py",
        )
        _write(
            plugins_dir,
            "from utils.plugin_manager import LauncherPlugin\n"
            "class Beta(LauncherPlugin):\n"
            "    name = 'beta'\n"
            "    description = 'second'\n",
            name="beta.py",
        )

    def test_plugins_allowlist_loads_only_named_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = Path(tmp)
            self._write_two_plugins(plugins_dir)
            manager = PluginManager(str(plugins_dir), plugin_names=["alpha"])
            self.assertEqual(manager.load(), 1)
            self.assertIsNotNone(manager.get("alpha"))
            self.assertIsNone(manager.get("beta"))

    def test_plugins_allowlist_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = Path(tmp)
            self._write_two_plugins(plugins_dir)
            manager = PluginManager(str(plugins_dir), plugin_names=["ALPHA"])
            self.assertEqual(manager.load(), 1)
            self.assertIsNotNone(manager.get("alpha"))

    def test_empty_plugins_allowlist_loads_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = Path(tmp)
            self._write_two_plugins(plugins_dir)
            manager = PluginManager(str(plugins_dir), plugin_names=[])
            self.assertEqual(manager.load(), 0)
            self.assertIsNone(manager.get("alpha"))
            self.assertIsNone(manager.get("beta"))

    def test_plugins_allowlist_keeps_aliases_of_allowed_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = Path(tmp)
            _write(
                plugins_dir,
                "from utils.plugin_manager import LauncherPlugin\n"
                "class Gamma(LauncherPlugin):\n"
                "    name = 'gamma'\n"
                "    aliases = ['g']\n"
                "    description = 'third'\n",
                name="gamma.py",
            )
            manager = PluginManager(str(plugins_dir), plugin_names=["gamma"])
            self.assertEqual(manager.load(), 1)
            self.assertIsNotNone(manager.get("g"))
            # Allowlisting an alias alone does not load the plugin — the
            # allowlist matches plugin names, not aliases.
            manager = PluginManager(str(plugins_dir), plugin_names=["g"])
            self.assertEqual(manager.load(), 0)
            self.assertIsNone(manager.get("gamma"))

    def test_plugins_allowlist_none_loads_everything(self):
        # ``plugin_names=None`` keeps the legacy load-all behavior.
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = Path(tmp)
            self._write_two_plugins(plugins_dir)
            manager = PluginManager(str(plugins_dir), plugin_names=None)
            self.assertEqual(manager.load(), 2)
            self.assertIsNotNone(manager.get("alpha"))
            self.assertIsNotNone(manager.get("beta"))

    def test_singleton_caches_per_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = Path(tmp)
            self._write_two_plugins(plugins_dir)
            all_plugins = get_plugin_manager(tmp)
            subset = get_plugin_manager(tmp, plugin_names=["alpha"])
            self.assertIsNot(all_plugins, subset)
            self.assertIsNotNone(subset.get("alpha"))
            self.assertIsNone(subset.get("beta"))
            # Same allowlist again reuses the cached instance.
            self.assertIs(get_plugin_manager(tmp, plugin_names=["alpha"]), subset)


class CalcPluginTest(unittest.TestCase):
    """Test the bundled /calc plugin (libqalculate backend)."""

    def setUp(self):
        from plugins import calc as calc_module
        from plugins.calc import CalcPlugin, evaluate, find_qalc

        self.plugin = CalcPlugin()
        self.evaluate = evaluate
        self.find_qalc = find_qalc
        self.calc_module = calc_module

    @unittest.skipUnless(
        __import__("shutil").which("qalc"), "qalc (libqalculate) not installed"
    )
    def test_evaluate_basic_arithmetic(self):
        self.assertEqual(self.evaluate("2 + 2"), "4")
        self.assertEqual(self.evaluate("2 + 2 * 2"), "6")
        self.assertTrue(self.evaluate("sqrt(2)").startswith("1.41421"))

    @unittest.skipUnless(
        __import__("shutil").which("qalc"), "qalc (libqalculate) not installed"
    )
    def test_evaluate_units_and_conversions(self):
        result = self.evaluate("100 cm to inches")
        self.assertIn("39.37", result)
        self.assertTrue(result.endswith("in"))
        self.assertIn("0.3", self.evaluate("0.1 + 0.2"))

    @unittest.skipUnless(
        __import__("shutil").which("qalc"), "qalc (libqalculate) not installed"
    )
    def test_evaluate_normalizes_unicode_minus(self):
        self.assertEqual(self.evaluate("-5 + 3"), "-2")

    def test_evaluate_raises_when_qalc_missing(self):
        with (
            unittest.mock.patch.object(
                self.calc_module, "find_qalc", return_value=None
            ),
            self.assertRaises(ValueError),
        ):
            self.evaluate("2 + 2")

    def test_evaluate_raises_on_timeout(self):
        from utils.plugin_manager import SubprocessTimeoutError

        with (
            unittest.mock.patch.object(
                self.calc_module,
                "run_subprocess",
                side_effect=SubprocessTimeoutError(["qalc"], 10),
            ),
            self.assertRaises(ValueError),
        ):
            self.evaluate("2 + 2", qalc_path="/usr/bin/qalc")

    def test_missing_qalc_returns_install_hint(self):
        with unittest.mock.patch.object(
            self.calc_module, "find_qalc", return_value=None
        ):
            plugin = self.calc_module.CalcPlugin()
            results = plugin.handle("2 + 2")
        self.assertIn("libqalculate", results[0].title)

    def test_handle_formats_result(self):
        results = self.plugin.handle("2 + 2")
        self.assertIn("4", results[0].title)
        self.assertEqual(results[0].data, "4")

    def test_handle_without_args_returns_usage(self):
        results = self.plugin.handle("")
        self.assertIn("Usage:", results[0].title)

    def test_debounce_before_calculation(self):
        # /calc forks qalc per query, so it must debounce harder than the
        # launcher default (150ms) rather than recalculate per keystroke.
        self.assertGreaterEqual(self.plugin.debounce_ms or 0, 400)


class TranslatePluginTest(unittest.TestCase):
    """Test the bundled /translate plugin (no network in tests)."""

    def test_usage_hint_without_args(self):
        from plugins.translate import TranslatePlugin

        results = TranslatePlugin().handle("")
        self.assertIn("Usage:", results[0].title)

    def test_debounce_before_translation(self):
        # /translate hits a network endpoint per query, so it must debounce
        # harder than the launcher default (150ms), like /calc.
        from plugins.translate import TranslatePlugin

        self.assertGreaterEqual(TranslatePlugin.debounce_ms or 0, 400)


class CurrencyPluginTest(unittest.TestCase):
    """Test the bundled /currency plugin (network + cache file mocked)."""

    _SAMPLE_RATES: ClassVar[dict] = {
        "date": "2026-08-12",
        "fetched": "2026-08-12",
        "rates": {"EUR": 1.0, "USD": 1.1552, "JPY": 183.91, "GBP": 0.8634},
    }

    def setUp(self):
        from plugins import currency as currency_module
        from plugins.currency import (
            CurrencyPlugin,
            fetch_rate,
            format_money,
            load_rates,
            normalize_rows,
            parse_query,
        )

        self.plugin = CurrencyPlugin()
        self.currency_module = currency_module
        self.fetch_rate = fetch_rate
        self.format_money = format_money
        self.load_rates = load_rates
        self.normalize_rows = normalize_rows
        self.parse_query = parse_query

        # Isolate the per-day cache file and pin "today" for determinism.
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.cache_file = str(Path(self._tmpdir.name) / "fx_rates.json")
        self.enterContext(
            unittest.mock.patch.object(
                self.currency_module, "FX_RATES_CACHE_FILE", self.cache_file
            )
        )
        self.enterContext(
            unittest.mock.patch.object(
                self.currency_module, "_today", return_value="2026-08-12"
            )
        )

    def _write_cache(self, payload=None):
        payload = payload if payload is not None else self._SAMPLE_RATES
        Path(self.cache_file).write_text(json.dumps(payload), encoding="utf-8")

    def test_parse_query_forms(self):
        self.assertEqual(self.parse_query("100 usd to eur"), (100.0, "USD", "EUR"))
        self.assertEqual(self.parse_query("100 usd eur"), (100.0, "USD", "EUR"))
        self.assertEqual(self.parse_query("usd eur"), (1.0, "USD", "EUR"))
        self.assertEqual(self.parse_query("1,000 EUR GBP"), (1000.0, "EUR", "GBP"))
        self.assertIsNone(self.parse_query(""))

    def test_parse_query_common_names(self):
        self.assertEqual(self.parse_query("10 dollars euros"), (10.0, "USD", "EUR"))
        self.assertEqual(self.parse_query("5 € $"), (5.0, "EUR", "USD"))

    def test_parse_query_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            self.parse_query("10 usd")  # missing target currency
        with self.assertRaises(ValueError):
            self.parse_query("ten usd eur")  # bad amount
        with self.assertRaises(ValueError):
            self.parse_query("10 usd usd")  # same currency
        with self.assertRaises(ValueError):
            self.parse_query("0 usd eur")  # zero amount

    def test_format_money(self):
        self.assertEqual(self.format_money(1.0), "1")
        self.assertEqual(self.format_money(92.35), "92.35")
        self.assertEqual(self.format_money(1234567.89), "1,234,567.89")

    def test_handle_without_args_returns_usage(self):
        results = self.plugin.handle("")
        self.assertIn("Usage:", results[0].title)

    def test_normalize_rows(self):
        rows = [
            {"date": "2026-08-11", "base": "EUR", "quote": "USD", "rate": 1.1},
            {"date": "2026-08-12", "base": "EUR", "quote": "JPY", "rate": 183.91},
            {"date": "2026-08-12", "base": "EUR", "quote": "EUR", "rate": 1.0},
        ]
        fx_date, rates = self.normalize_rows(rows)
        self.assertEqual(fx_date, "2026-08-12")
        self.assertEqual(rates["USD"], 1.1)
        self.assertEqual(rates["JPY"], 183.91)
        self.assertEqual(rates["EUR"], 1.0)

    def test_write_cache_uses_shared_json_writer(self):
        payload = self._SAMPLE_RATES

        with unittest.mock.patch.object(
            self.currency_module, "write_json_file"
        ) as writer:
            self.currency_module._write_cache(payload)

        writer.assert_called_once_with(self.cache_file, payload, sync=True)

    def test_load_rates_reads_fresh_cache_without_network(self):
        self._write_cache()
        with unittest.mock.patch(
            "plugins.currency.http_request",
            side_effect=AssertionError("network must not be touched"),
        ):
            payload = self.load_rates()
        self.assertEqual(payload, self._SAMPLE_RATES)

    def test_load_rates_downloads_and_writes_cache_when_missing(self):
        with unittest.mock.patch.object(
            self.currency_module,
            "_download_rates",
            return_value=("2026-08-12", {"EUR": 1.0, "USD": 1.1552}),
        ) as mock_download:
            self.load_rates()
            payload = self.load_rates()  # second call hits the cache
        self.assertEqual(mock_download.call_count, 1)
        self.assertEqual(payload["date"], "2026-08-12")
        self.assertTrue(Path(self.cache_file).exists())

    def test_load_rates_refreshes_stale_cache(self):
        stale = {
            "date": "2026-08-11",
            "fetched": "2026-08-11",
            "rates": {"EUR": 1.0, "USD": 1.1},
        }
        self._write_cache(stale)
        with unittest.mock.patch.object(
            self.currency_module,
            "_download_rates",
            return_value=("2026-08-12", {"EUR": 1.0, "USD": 1.2}),
        ):
            payload = self.load_rates()
        self.assertEqual(payload["date"], "2026-08-12")
        self.assertEqual(payload["rates"]["USD"], 1.2)

    def test_load_rates_falls_back_to_stale_cache_on_download_error(self):
        stale = {
            "date": "2026-08-11",
            "fetched": "2026-08-11",
            "rates": {"EUR": 1.0, "USD": 1.1},
        }
        self._write_cache(stale)
        with unittest.mock.patch.object(
            self.currency_module,
            "_download_rates",
            side_effect=RuntimeError("down"),
        ):
            payload = self.load_rates()
        self.assertEqual(payload, stale)

    def test_load_rates_raises_when_no_cache_and_download_fails(self):
        with (
            unittest.mock.patch.object(
                self.currency_module,
                "_download_rates",
                side_effect=RuntimeError("down"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self.load_rates()

    def test_incomplete_cache_is_not_used_as_fallback(self):
        self._write_cache({"rates": {"USD": 1.0}})

        with (
            unittest.mock.patch.object(
                self.currency_module,
                "_download_rates",
                side_effect=RuntimeError("down"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self.load_rates()

    def test_fetch_rate_reads_cross_rates_from_cache(self):
        self._write_cache()
        rate, fx_date = self.fetch_rate("USD", "JPY")
        self.assertAlmostEqual(rate, 183.91 / 1.1552)
        self.assertEqual(fx_date, "2026-08-12")
        self.assertEqual(self.fetch_rate("EUR", "USD"), (1.1552, "2026-08-12"))
        self.assertEqual(self.fetch_rate("USD", "USD"), (1.0, "2026-08-12"))

    def test_fetch_rate_unknown_currency(self):
        self._write_cache()
        with self.assertRaises(ValueError):
            self.fetch_rate("USD", "ZZZ")

    def test_handle_formats_conversion_from_cache(self):
        self._write_cache()
        results = self.plugin.handle("100 usd to eur")
        # Sample rate 1.1552 is EUR->USD, so USD->EUR = 1 / 1.1552.
        self.assertIn("86.565097", results[0].title)
        self.assertEqual(results[0].data, "86.565097 EUR")

    def test_handle_network_failure_without_cache(self):
        with unittest.mock.patch.object(
            self.currency_module,
            "_download_rates",
            side_effect=RuntimeError("down"),
        ):
            results = self.plugin.handle("100 usd eur")
        self.assertIn("failed", results[0].title.casefold())

    def test_download_retries_transient_failure(self):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                rows = [
                    {
                        "date": "2026-08-12",
                        "base": "EUR",
                        "quote": "USD",
                        "rate": 1.1552,
                    },
                    {
                        "date": "2026-08-12",
                        "base": "EUR",
                        "quote": "JPY",
                        "rate": 183.91,
                    },
                ]
                # Pad with more currencies so the payload passes the size
                # sanity check (_MIN_RATES_COUNT).
                for i, code in enumerate(
                    ["GBP", "CHF", "CAD", "AUD", "INR", "CNY", "KRW", "MXN"]
                ):
                    rows.append(
                        {
                            "date": "2026-08-12",
                            "base": "EUR",
                            "quote": code,
                            "rate": 10.0 + i,
                        }
                    )
                return rows

        calls = {"n": 0}

        def fake_http(cancelled, method, url, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("first attempt timed out")
            return FakeResponse()

        with (
            unittest.mock.patch.object(self.currency_module.time, "sleep"),
            unittest.mock.patch("plugins.currency.http_request", side_effect=fake_http),
        ):
            payload = self.load_rates()
        self.assertEqual(calls["n"], 2)
        self.assertEqual(payload["rates"]["USD"], 1.1552)

    def test_load_rates_rejects_sparse_download(self):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return []  # malformed / empty payload

        with (
            unittest.mock.patch.object(self.currency_module.time, "sleep"),
            unittest.mock.patch(
                "plugins.currency.http_request", return_value=FakeResponse()
            ),
            self.assertRaises(ValueError),
        ):
            self.load_rates()
        # A nearly-empty table must not be cached as a valid daily snapshot.
        self.assertFalse(Path(self.cache_file).exists())

    def test_download_does_not_retry_client_errors(self):
        class ClientError(Exception):
            def __init__(self):
                super().__init__("unknown")
                self.response = type("Resp", (), {"status_code": 404})()

        calls = {"n": 0}

        def fake_http(cancelled, method, url, **kwargs):
            calls["n"] += 1
            raise ClientError()

        with (
            unittest.mock.patch.object(self.currency_module.time, "sleep"),
            unittest.mock.patch("plugins.currency.http_request", side_effect=fake_http),
            self.assertRaises(ClientError),
        ):
            self.load_rates()
        # 4xx (e.g. a bad request) is a client error — exactly one attempt.
        self.assertEqual(calls["n"], 1)

    def test_debounce_before_conversion(self):
        # /currency hits a network endpoint per query, so it must debounce
        # harder than the launcher default (150ms), like /calc and /translate.
        self.assertGreaterEqual(self.plugin.debounce_ms or 0, 400)

    def test_execute_copies_converted_amount(self):
        import unittest.mock

        from utils.plugin_manager import PluginResult

        with unittest.mock.patch("plugins.currency.copy_to_clipboard") as mock_copy:
            self.plugin.execute(PluginResult("x", data="87.39 EUR"))
        mock_copy.assert_called_once_with("87.39 EUR")


class RunSubprocessTest(unittest.TestCase):
    """Test the Gio-based run_subprocess helper (no stdlib subprocess)."""

    def test_module_level_run_subprocess_captures_output(self):
        from utils.plugin_manager import SubprocessResult, run_subprocess

        result = run_subprocess(["echo", "hello world"])
        self.assertIsInstance(result, SubprocessResult)
        self.assertEqual(result.stdout.strip(), "hello world")
        self.assertEqual(result.returncode, 0)

    def test_module_level_run_subprocess_reports_nonzero_status(self):
        from utils.plugin_manager import run_subprocess

        result = run_subprocess(["sh", "-c", "echo oops >&2; exit 3"])
        self.assertEqual(result.returncode, 3)
        self.assertIn("oops", result.stderr)

    def test_run_subprocess_raises_on_timeout(self):
        from utils.plugin_manager import SubprocessTimeoutError, run_subprocess

        with self.assertRaises(SubprocessTimeoutError):
            run_subprocess(["sleep", "30"], timeout=0.2)

    def test_plugin_run_subprocess_is_cancellable(self):
        import threading
        import time

        from utils.plugin_manager import LauncherPlugin

        plugin = LauncherPlugin()
        done = threading.Event()
        result: dict = {}

        def _run():
            try:
                result["value"] = plugin.run_subprocess(["sleep", "30"])
            finally:
                done.set()

        worker = threading.Thread(target=_run)
        worker.start()
        # Give the worker a moment to spawn and track the process.
        for _ in range(100):
            if plugin._subprocess is not None:
                break
            time.sleep(0.01)
        plugin.cancel()
        self.assertTrue(done.wait(5))
        worker.join(timeout=5)
        self.assertIn("value", result)
        self.assertNotEqual(result["value"].returncode, 0)  # killed, not exited


class HttpRequestTest(unittest.TestCase):
    """Test the cancellable http_request helper (streaming + abort)."""

    @staticmethod
    def _fake_client(response):
        """A get_http_client stand-in whose ``stream`` yields *response*."""

        class FakeStream:
            def __enter__(self):
                return response

            def __exit__(self, *exc):
                return False

        class FakeClient:
            def stream(self, method, url, **kwargs):
                return FakeStream()

        return FakeClient()

    def test_raises_when_cancelled_before_request(self):
        from utils.plugin_manager import PluginCancelledError, http_request

        with self.assertRaises(PluginCancelledError):
            http_request(lambda: True, "GET", "https://example.com")

    def test_raises_when_cancelled_mid_body(self):
        from utils.plugin_manager import PluginCancelledError, http_request

        state = {"cancelled": False}

        class Response:
            status_code = 200
            headers: ClassVar[dict] = {}

            def iter_bytes(self):
                yield b"first chunk"
                state["cancelled"] = True
                yield b"second chunk"

        with (
            unittest.mock.patch(
                "utils.plugin_manager.get_http_client",
                return_value=self._fake_client(Response()),
            ),
            self.assertRaises(PluginCancelledError),
        ):
            http_request(lambda: state["cancelled"], "GET", "https://example.com")

    def test_returns_fully_read_body_when_not_cancelled(self):
        from utils.plugin_manager import http_request

        class Response:
            status_code = 200
            headers: ClassVar[dict] = {}
            request = None
            extensions: ClassVar[dict] = {}

            def iter_bytes(self):
                yield b"hello"
                yield b" world"

        with (
            unittest.mock.patch(
                "utils.plugin_manager.get_http_client",
                return_value=self._fake_client(Response()),
            ),
            unittest.mock.patch(
                "utils.plugin_manager._materialize_response",
                return_value=("materialized", "hello world"),
            ) as mock_materialize,
        ):
            result = http_request(lambda: False, "GET", "https://example.com")
        self.assertEqual(result, ("materialized", "hello world"))
        # The helper must read the whole body before materializing, so
        # superseded queries abort instead of parsing a partial response.
        args, _ = mock_materialize.call_args
        self.assertEqual(args[1], b"hello world")

    def test_plugin_run_http_aborts_on_cancel(self):
        from utils.plugin_manager import LauncherPlugin, PluginCancelledError

        plugin = LauncherPlugin()
        plugin.cancel()  # superseded before the request goes out
        with self.assertRaises(PluginCancelledError):
            plugin.run_http("GET", "https://example.com")


class PluginCacheTest(unittest.TestCase):
    """Test the session result cache on LauncherPlugin."""

    def setUp(self):
        from utils.plugin_manager import LauncherPlugin

        self.plugin = LauncherPlugin()
        self.plugin.cache_ttl_seconds = 300

    def test_cache_get_put_roundtrip(self):
        from utils.plugin_manager import _CACHE_MISS

        self.assertIs(self.plugin.cache_get("k"), _CACHE_MISS)
        self.plugin.cache_put("k", "v")
        self.assertEqual(self.plugin.cache_get("k"), "v")

    def test_cache_ttl_zero_disables(self):
        from utils.plugin_manager import _CACHE_MISS

        self.plugin.cache_ttl_seconds = 0
        self.plugin.cache_put("k", "v")
        self.assertIs(self.plugin.cache_get("k"), _CACHE_MISS)

    def test_cache_expiry(self):
        from utils.plugin_manager import _CACHE_MISS

        self.plugin.cache_put("k", "v")
        # rewind the entry's deadline rather than sleeping for it
        self.plugin._cache._entries["k"] = (-1.0, "v")

        self.assertIs(self.plugin.cache_get("k"), _CACHE_MISS)
        self.assertNotIn("k", self.plugin._cache._entries)

    def test_cache_evicts_oldest_over_cap(self):
        from utils.plugin_manager import _CACHE_MAX_ENTRIES, _CACHE_MISS

        for i in range(_CACHE_MAX_ENTRIES + 10):
            self.plugin.cache_put(f"k{i}", i)
        self.assertLessEqual(len(self.plugin._cache), _CACHE_MAX_ENTRIES)
        # Newest entries survive; the oldest were evicted.
        self.assertEqual(
            self.plugin.cache_get(f"k{_CACHE_MAX_ENTRIES + 9}"), _CACHE_MAX_ENTRIES + 9
        )
        self.assertIs(self.plugin.cache_get("k0"), _CACHE_MISS)

    def test_cached_produces_once(self):
        state = {"n": 0}

        def producer():
            state["n"] += 1
            return "value"

        self.assertEqual(self.plugin.cached("k", producer), "value")
        self.assertEqual(self.plugin.cached("k", producer), "value")
        self.assertEqual(state["n"], 1)

    def test_cached_handle_serves_repeat_args_from_cache(self):
        from utils.plugin_manager import (
            LauncherPlugin,
            PluginResult,
            cached_handle,
        )

        class CounterPlugin(LauncherPlugin):
            cache_ttl_seconds = 300
            calls = 0

            @cached_handle()
            def handle(self, args):
                CounterPlugin.calls += 1
                return [PluginResult(args)]

        plugin = CounterPlugin()
        self.assertEqual(plugin.handle("hello"), plugin.handle("hello"))
        self.assertEqual(CounterPlugin.calls, 1)
        plugin.handle("world")
        self.assertEqual(CounterPlugin.calls, 2)  # different args miss the cache

    def test_cached_handle_skips_caching_cancelled_queries(self):
        from utils.plugin_manager import (
            LauncherPlugin,
            PluginResult,
            cached_handle,
        )

        class CounterPlugin(LauncherPlugin):
            cache_ttl_seconds = 300
            calls = 0

            @cached_handle()
            def handle(self, args):
                CounterPlugin.calls += 1
                if self.is_cancelled():
                    return []
                return [PluginResult(args)]

        plugin = CounterPlugin()
        plugin.cancel()
        self.assertEqual(plugin.handle("x"), [])
        plugin._reset_cancel()
        # PluginResult has no __eq__ — compare titles.
        self.assertEqual([result.title for result in plugin.handle("x")], ["x"])
        # The superseded empty result was not cached — the retry ran handle.
        self.assertEqual(CounterPlugin.calls, 2)


class KillPluginTest(unittest.TestCase):
    """Test the bundled /kill plugin (proc tree mocked)."""

    def setUp(self):
        from plugins.kill import (
            KillPlugin,
            find_pids_on_port,
            kill_process,
            list_port_processes,
            list_processes,
            parse_kill_args,
            parse_ss_output,
        )

        self.plugin = KillPlugin()
        self.find_pids_on_port = find_pids_on_port
        self.kill_process = kill_process
        self.list_port_processes = list_port_processes
        self.list_processes = list_processes
        self.parse_kill_args = parse_kill_args
        self.parse_ss_output = parse_ss_output

    def _fake_proc(self, tmp: Path) -> Path:
        """Build a minimal fake /proc tree for scanning."""
        for pid, comm, cmdline in [
            (1234, "firefox", "/usr/lib/firefox/firefox --new-window"),
            (5678, "spotify", "/usr/bin/spotify"),
            (9999, "sleep", "/usr/bin/sleep 60"),
        ]:
            d = tmp / str(pid)
            d.mkdir()
            (d / "comm").write_text(comm + "\n")
            (d / "cmdline").write_bytes(cmdline.replace(" ", "\x00").encode() + b"\x00")
        (tmp / "notapid").mkdir()
        return tmp

    def test_parse_kill_args(self):
        self.assertEqual(self.parse_kill_args(""), (False, ""))
        self.assertEqual(self.parse_kill_args("firefox"), (False, "firefox"))
        self.assertEqual(self.parse_kill_args("-9 firefox"), (True, "firefox"))
        self.assertEqual(self.parse_kill_args("--force spotify"), (True, "spotify"))

    def test_list_processes_matches_comm_and_cmdline(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._fake_proc(Path(tmp))
            self.assertEqual(
                self.list_processes("firefox", proc_dir=str(proc)),
                [(1234, "firefox", "/usr/lib/firefox/firefox --new-window")],
            )
            # Match against the command line, not just the process name.
            pids = [
                row[0] for row in self.list_processes("new-window", proc_dir=str(proc))
            ]
            self.assertEqual(pids, [1234])

    def test_list_processes_empty_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._fake_proc(Path(tmp))
            self.assertEqual(self.list_processes("", proc_dir=str(proc)), [])
            self.assertEqual(self.list_processes("zzz", proc_dir=str(proc)), [])

    def test_list_processes_respects_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._fake_proc(Path(tmp))
            matches = self.list_processes("e", limit=1, proc_dir=str(proc))
            self.assertLessEqual(len(matches), 1)

    def test_kill_process_signals(self):
        import signal

        with unittest.mock.patch("plugins.kill.os.kill") as mock_kill:
            self.assertIsNone(self.kill_process(1234))
            mock_kill.assert_called_once_with(1234, signal.SIGTERM)

        with unittest.mock.patch("plugins.kill.os.kill") as mock_kill:
            self.assertIsNone(self.kill_process(1234, force=True))
            mock_kill.assert_called_once_with(1234, signal.SIGKILL)

    def test_kill_process_reports_errors(self):
        with unittest.mock.patch(
            "plugins.kill.os.kill", side_effect=PermissionError("nope")
        ):
            self.assertIn("permission", self.kill_process(1234).casefold())

    def test_handle_without_args_returns_usage(self):
        results = self.plugin.handle("")
        self.assertIn("Usage:", results[0].title)

    def test_handle_no_match(self):
        with unittest.mock.patch("plugins.kill.list_processes", return_value=[]):
            results = self.plugin.handle("zzznope")
        self.assertIn("No process", results[0].title)

    def test_handle_builds_rows_with_kill_data(self):
        with unittest.mock.patch(
            "plugins.kill.list_processes",
            return_value=[(1234, "firefox", "/usr/lib/firefox/firefox")],
        ):
            results = self.plugin.handle("firefox")
            self.assertEqual(results[0].data, (1234, False))
            self.assertIn("SIGTERM", results[0].subtitle)
            results_force = self.plugin.handle("-9 firefox")
            self.assertEqual(results_force[0].data, (1234, True))
            self.assertIn("SIGKILL", results_force[0].subtitle)

    def test_execute_kills_selected_pid(self):
        import unittest.mock

        from utils.plugin_manager import PluginResult

        with unittest.mock.patch("plugins.kill.kill_process") as mock_kill:
            self.plugin.execute(PluginResult("x", data=(1234, True)))
        mock_kill.assert_called_once_with(1234, True)

    # -- port mode --------------------------------------------------

    def test_parse_ss_output_extracts_listening_pids(self):
        output = (
            "Netid State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
            "tcp LISTEN 0 4096 127.0.0.1:3000 0.0.0.0:* "
            'users:(("node",pid=1234,fd=16))\n'
            "tcp LISTEN 0 4096 [::]:3000 [::]:* "
            'users:(("node",pid=1234,fd=21))\n'
            "tcp LISTEN 0 4096 127.0.0.1:8080 0.0.0.0:* "
            'users:(("python",pid=5555,fd=9))\n'
            "tcp LISTEN 0 4096 127.0.0.1:3001 0.0.0.0:* "
            'users:(("other",pid=7777,fd=3))\n'
        )
        # IPv4 + IPv6 listeners on the same port share one pid — deduped.
        self.assertEqual(self.parse_ss_output(output, 3000), [1234])
        self.assertEqual(self.parse_ss_output(output, 8080), [5555])
        self.assertEqual(self.parse_ss_output(output, 9999), [])

    def test_find_pids_on_port_falls_back_to_lsof(self):
        from utils.plugin_manager import SubprocessResult

        fake = SubprocessResult(["lsof"], 0, stdout="1234\n5678\n", stderr="")
        with (
            unittest.mock.patch(
                "plugins.kill.find_executable",
                side_effect=lambda name: None if name == "ss" else "/usr/bin/lsof",
            ),
            unittest.mock.patch("plugins.kill.run_subprocess", return_value=fake),
        ):
            self.assertEqual(self.find_pids_on_port(3000), [1234, 5678])

    def test_handle_port_mode_uses_cancellable_runner(self):
        from utils.plugin_manager import SubprocessResult

        fake = SubprocessResult(["lsof"], 0, stdout="1234\n", stderr="")
        with (
            unittest.mock.patch(
                "plugins.kill.find_executable",
                side_effect=lambda name: None if name == "ss" else "/usr/bin/lsof",
            ),
            unittest.mock.patch.object(
                self.plugin, "run_subprocess", return_value=fake
            ),
        ):
            results = self.plugin.handle("3000")
        self.assertEqual(results[0].data, (1234, False))
        self.assertIn("Port 3000", results[0].title)

    def test_find_pids_on_port_returns_empty_when_no_tools(self):
        with unittest.mock.patch("plugins.kill.find_executable", return_value=None):
            self.assertEqual(self.find_pids_on_port(3000), [])

    def test_handle_port_mode(self):
        with unittest.mock.patch(
            "plugins.kill.list_port_processes", return_value=[(1234, "node")]
        ):
            results = self.plugin.handle("3000")
        self.assertEqual(results[0].data, (1234, False))
        self.assertIn("Port 3000", results[0].title)
        self.assertIn("node", results[0].title)
        self.assertIn("SIGTERM", results[0].subtitle)

        with unittest.mock.patch(
            "plugins.kill.list_port_processes", return_value=[(1234, "node")]
        ):
            results_force = self.plugin.handle("-9 3000")
        self.assertEqual(results_force[0].data, (1234, True))
        self.assertIn("SIGKILL", results_force[0].subtitle)

    def test_handle_port_no_listener(self):
        with unittest.mock.patch("plugins.kill.list_port_processes", return_value=[]):
            results = self.plugin.handle("39999")
        self.assertIn("Nothing is listening", results[0].title)


class EmojiPluginTest(unittest.TestCase):
    """Test the bundled /emoji plugin (offline)."""

    def setUp(self):
        from plugins.emoji import EmojiPlugin, search_emojis

        self.plugin = EmojiPlugin()
        self.search_emojis = search_emojis

    def test_search_finds_by_name(self):
        matches = self.search_emojis("grinning face")
        self.assertTrue(matches)
        self.assertEqual(matches[0][1]["name"], "grinning face")

    def test_handle_returns_glyph_rows(self):
        results = self.plugin.handle("rocket")
        self.assertTrue(results)
        row = results[0]
        self.assertEqual(row.data, row.title)  # the glyph itself is copied
        self.assertTrue(row.title)  # a non-empty emoji character

    def test_handle_without_args_returns_usage(self):
        results = self.plugin.handle("")
        self.assertIn("Usage:", results[0].title)

    def test_handle_no_match(self):
        results = self.plugin.handle("zzzznotanemoji")
        self.assertIn("No emoji", results[0].title)

    def test_handle_limits_results(self):
        results = self.plugin.handle("face")
        self.assertLessEqual(len(results), 24)


class UnicodePluginTest(unittest.TestCase):
    """Test the bundled /unicode plugin (offline)."""

    def setUp(self):
        from plugins.unicode import UnicodePlugin, search_unicode

        self.plugin = UnicodePlugin()
        self.search_unicode = search_unicode

    def test_search_finds_by_name(self):
        matches = self.search_unicode("copyright")
        self.assertTrue(matches)
        self.assertEqual(matches[0][1]["name"], "COPYRIGHT SIGN")

    def test_search_finds_by_codepoint(self):
        matches = self.search_unicode("U+00A9")
        self.assertTrue(matches)
        self.assertEqual(matches[0][0], "\u00a9")

    def test_handle_returns_rows_with_codepoint(self):
        results = self.plugin.handle("copyright")
        self.assertTrue(results)
        row = results[0]
        self.assertIn("U+00A9", row.title)
        self.assertEqual(row.data, "\u00a9")

    def test_handle_without_args_returns_usage(self):
        results = self.plugin.handle("")
        self.assertIn("Usage:", results[0].title)

    def test_handle_no_match(self):
        results = self.plugin.handle("zzzznotaunicode")
        self.assertIn("No Unicode", results[0].title)

    def test_handle_limits_results(self):
        results = self.plugin.handle("letter")
        self.assertLessEqual(len(results), 24)

    def test_aliases(self):
        self.assertIn("uni", self.plugin.aliases)
        self.assertIn("char", self.plugin.aliases)


class ClipboardHistoryPluginTest(unittest.TestCase):
    """Test the bundled /clipboard-history plugin (cliphist mocked)."""

    def setUp(self):
        from plugins.clipboard_history import (
            ClipboardHistoryPlugin,
            is_binary,
            parse_list,
        )

        self.plugin = ClipboardHistoryPlugin()
        self.parse_list = parse_list
        self.is_binary = is_binary

    def test_parse_list(self):
        output = "713\thello world\n712\tlibqalculate\n"
        self.assertEqual(
            self.parse_list(output),
            [("713", "hello world"), ("712", "libqalculate")],
        )

    def test_parse_list_skips_blank_and_html_artifacts(self):
        output = '\n711\t<meta http-equiv="refresh"\n710\tplain text\n'
        self.assertEqual(self.parse_list(output), [("710", "plain text")])

    def test_is_binary(self):
        self.assertTrue(self.is_binary("PNG\x00\x01\x02"))
        self.assertFalse(self.is_binary("hello world"))

    def test_handle_filters_by_query(self):
        from utils.plugin_manager import SubprocessResult

        fake = SubprocessResult(
            ["cliphist", "list"],
            0,
            stdout="1\taaa\n2\tbbb\n",
            stderr="",
        )
        with (
            unittest.mock.patch(
                "plugins.clipboard_history.find_executable",
                return_value="/usr/bin/cliphist",
            ),
            unittest.mock.patch.object(
                self.plugin, "run_subprocess", return_value=fake
            ),
        ):
            results = self.plugin.handle("bbb")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].data, "2")
        self.assertEqual(results[0].title, "bbb")

    def test_handle_empty_history(self):
        from utils.plugin_manager import SubprocessResult

        fake = SubprocessResult(["cliphist", "list"], 0, stdout="", stderr="")
        with (
            unittest.mock.patch(
                "plugins.clipboard_history.find_executable",
                return_value="/usr/bin/cliphist",
            ),
            unittest.mock.patch.object(
                self.plugin, "run_subprocess", return_value=fake
            ),
        ):
            results = self.plugin.handle("anything")
        self.assertEqual(results[0].title, "No matching clipboard items")

    def test_handle_missing_cliphist(self):
        with unittest.mock.patch(
            "plugins.clipboard_history.find_executable", return_value=None
        ):
            results = self.plugin.handle("")
        self.assertIn("cliphist", results[0].title)

    def test_execute_recopies_decoded_item(self):
        from utils.plugin_manager import PluginResult, SubprocessResult

        fake = SubprocessResult(
            ["cliphist", "decode", "5"], 0, stdout="decoded text", stderr=""
        )
        with (
            unittest.mock.patch(
                "plugins.clipboard_history.copy_to_clipboard"
            ) as mock_copy,
            unittest.mock.patch(
                "plugins.clipboard_history.run_subprocess", return_value=fake
            ),
        ):
            self.plugin.execute(PluginResult("x", data="5"))
        mock_copy.assert_called_once_with("decoded text")

    def test_handle_marks_binary_items(self):
        from utils.plugin_manager import SubprocessResult

        fake = SubprocessResult(
            ["cliphist", "list"], 0, stdout="9\tPNG\x00\x01\x02\n", stderr=""
        )
        with (
            unittest.mock.patch(
                "plugins.clipboard_history.find_executable",
                return_value="/usr/bin/cliphist",
            ),
            unittest.mock.patch.object(
                self.plugin, "run_subprocess", return_value=fake
            ),
        ):
            results = self.plugin.handle("")
        self.assertEqual(results[0].title, "[Image or binary]")

    def test_execute_skips_binary_content(self):
        from utils.plugin_manager import PluginResult, SubprocessResult

        fake = SubprocessResult(
            ["cliphist", "decode", "9"], 0, stdout="PNG\x00\x01", stderr=""
        )
        with (
            unittest.mock.patch(
                "plugins.clipboard_history.copy_to_clipboard"
            ) as mock_copy,
            unittest.mock.patch(
                "plugins.clipboard_history.run_subprocess", return_value=fake
            ),
        ):
            self.plugin.execute(PluginResult("x", data="9"))
        mock_copy.assert_not_called()


class SearchPluginTest(unittest.TestCase):
    """Test the bundled /search plugin (network mocked)."""

    _FAKE_HTML = """
    <html><body>
    <div class="result results_links results_links_deep web-result ">
      <h2 class="result__title">
        <a rel="nofollow" class="result__a"
           href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdocs&amp;rut=abc">
          Example Docs &amp; Guide
        </a>
      </h2>
      <a rel="nofollow" class="result__snippet" href="#">
        A short snippet about examples.
      </a>
    </div>
    <div class="result">
      <h2 class="result__title">
        <a rel="nofollow" class="result__a" href="https://plain.example.net/">
          Plain Link
        </a>
      </h2>
    </div>
    </body></html>
    """

    def setUp(self):
        from plugins.search import SearchPlugin, parse_results, resolve_url

        self.plugin = SearchPlugin()
        self.parse_results = parse_results
        self.resolve_url = resolve_url

    def test_parse_results_extracts_title_url_snippet(self):
        results = self.parse_results(self._FAKE_HTML)
        self.assertEqual(len(results), 2)
        title, url, snippet = results[0]
        self.assertEqual(title, "Example Docs & Guide")
        self.assertEqual(url, "https://example.com/docs")
        self.assertIn("short snippet", snippet)

    def test_resolve_url_decodes_redirect_and_protocol_relative(self):
        self.assertEqual(
            self.resolve_url(
                "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fx&rut=1"
            ),
            "https://example.com/x",
        )
        self.assertEqual(
            self.resolve_url("//cdn.example.net/a"), "https://cdn.example.net/a"
        )
        self.assertEqual(self.resolve_url("https://x.example/"), "https://x.example/")

    def test_resolve_url_keeps_literal_percent_encoding(self):
        # A target URL containing %xx must not be double-decoded into a
        # broken link (parse_qs already decodes the uddg value once).
        self.assertEqual(
            self.resolve_url(
                "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa%2520b&rut=1"
            ),
            "https://example.com/a%20b",
        )

    def test_handle_without_args_returns_usage(self):
        results = self.plugin.handle("")
        self.assertIn("Usage:", results[0].title)

    def test_handle_builds_result_rows(self):
        import unittest.mock

        with unittest.mock.patch(
            "plugins.search.search",
            return_value=[("Fabric docs", "https://fabric.example/", "A snip")],
        ):
            results = self.plugin.handle("fabric")
        self.assertEqual(results[0].data, "https://fabric.example/")
        self.assertIn("Enter to open", results[0].subtitle)

    def test_handle_no_results_offers_search_page(self):
        import unittest.mock

        with unittest.mock.patch("plugins.search.search", return_value=[]):
            results = self.plugin.handle("zzz nope")
        self.assertIn("No results", results[0].title)
        self.assertIn("duckduckgo.com", str(results[0].data))

    def test_handle_network_failure(self):
        import unittest.mock

        with unittest.mock.patch(
            "plugins.search.search", side_effect=RuntimeError("down")
        ):
            results = self.plugin.handle("anything")
        self.assertIn("failed", results[0].title.casefold())

    def test_execute_opens_and_copies_selected_url(self):
        import unittest.mock

        from utils.plugin_manager import PluginResult

        with (
            unittest.mock.patch("plugins.search.open_url") as mock_open,
            unittest.mock.patch("plugins.search.copy_to_clipboard") as mock_copy,
        ):
            self.plugin.execute(PluginResult("x", data="https://example.com/"))
        mock_open.assert_called_once_with("https://example.com/")
        mock_copy.assert_called_once_with("https://example.com/")

    def test_debounce_before_search(self):
        # /search hits a network endpoint per query, so it must debounce
        # harder than the launcher default (150ms), like /translate.
        self.assertGreaterEqual(self.plugin.debounce_ms or 0, 400)


class HistoryPluginTest(unittest.TestCase):
    """Test the bundled /history plugin (history files mocked)."""

    def setUp(self):
        from plugins.history import (
            HistoryPlugin,
            load_history,
            parse_bash_history,
            parse_fish_history,
            parse_zsh_history,
        )

        self.plugin = HistoryPlugin()
        self.load_history = load_history
        self.parse_bash_history = parse_bash_history
        self.parse_fish_history = parse_fish_history
        self.parse_zsh_history = parse_zsh_history

    def test_parse_bash_history(self):
        content = "ls\ncd /tmp\n\n# a comment\n"
        self.assertEqual(self.parse_bash_history(content), [(1, "ls"), (2, "cd /tmp")])

    def test_parse_zsh_extended_history(self):
        content = ": 1700000001:0;cd /tmp\n: 1700000002:3;git status\n"
        self.assertEqual(
            self.parse_zsh_history(content),
            [(1700000001, "cd /tmp"), (1700000002, "git status")],
        )

    def test_parse_zsh_plain_lines_are_ordered(self):
        entries = self.parse_zsh_history("first\nsecond\nthird\n")
        # Plain lines sort newer-first by their position in the file.
        self.assertEqual(
            [cmd for _, cmd in sorted(entries, reverse=True)],
            ["third", "second", "first"],
        )

    def test_parse_fish_history(self):
        content = "- cmd: ls\n  when: 1700000001\n- cmd: git pull\n  when: 1700000002\n"
        self.assertEqual(
            self.parse_fish_history(content),
            [(1700000001, "ls"), (1700000002, "git pull")],
        )

    def test_load_history_dedupes_and_sorts_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            bash = Path(tmp) / ".bash_history"
            zsh = Path(tmp) / ".zsh_history"
            bash.write_text("oldcmd\ngit status\n")
            zsh.write_text(": 1700000005:0;git status\n: 1700000006:0;ls -la\n")
            commands = self.load_history([str(bash), str(zsh)])
        # "git status" appears twice — the zsh copy (newer epoch) wins, and
        # the list is most-recent-first.
        self.assertEqual(commands[:3], ["ls -la", "git status", "oldcmd"])

    def test_handle_filters_by_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            bash = Path(tmp) / ".bash_history"
            bash.write_text("git commit\ngit push\ncd /tmp\n")
            with unittest.mock.patch(
                "plugins.history.default_history_files", return_value=[str(bash)]
            ):
                results = self.plugin.handle("git")
        self.assertEqual([row.title for row in results], ["git push", "git commit"])
        self.assertEqual(results[0].data, "git push")

    def test_handle_no_history(self):
        with unittest.mock.patch(
            "plugins.history.default_history_files", return_value=["/nonexistent"]
        ):
            results = self.plugin.handle("anything")
        self.assertIn("No shell history", results[0].title)

    def test_handle_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            bash = Path(tmp) / ".bash_history"
            bash.write_text("git push\n")
            with unittest.mock.patch(
                "plugins.history.default_history_files", return_value=[str(bash)]
            ):
                results = self.plugin.handle("zzz")
        self.assertIn("No history entry", results[0].title)

    def test_execute_copies_command(self):
        import unittest.mock

        from utils.plugin_manager import PluginResult

        with unittest.mock.patch("plugins.history.copy_to_clipboard") as mock_copy:
            self.plugin.execute(PluginResult("git push", data="git push"))
        mock_copy.assert_called_once_with("git push")


class DefinePluginTest(unittest.TestCase):
    """Test the bundled /define plugin (dict.org transcript mocked)."""

    _RESPONSE = (
        "220 dictd 1.12.1/rf on Linux <system.mail.dict.org>\r\n"
        "CLIENT tsumiki/1.0\r\n"
        "250 ok\r\n"
        "DEFINE wn serendipity\r\n"
        "150 1 definitions retrieved\r\n"
        '151 "serendipity" wn "WordNet (r) 3.0 (2006)"\r\n'
        "Serendipity\r\n"
        "n 1: good luck in making unexpected discoveries [syn: {serendipity}]\r\n"
        "n 2: a fortunate discovery happening by chance\r\n"
        ".\r\n"
        "250 ok [d/m/c = 1/1/1; 0.000r 0.000u 0.000s]\r\n"
        "QUIT\r\n"
        "221 bye [d/m/c = 1/0/0; 0.000r 0.000u 0.000s]\r\n"
    )

    def setUp(self):
        from plugins.define import (
            DefinePlugin,
            parse_define_args,
            parse_dict_response,
            query_dict,
            split_senses,
        )

        self.plugin = DefinePlugin()
        self.parse_define_args = parse_define_args
        self.parse_dict_response = parse_dict_response
        self.query_dict = query_dict
        self.split_senses = split_senses

    def test_parse_dict_response(self):
        blocks = self.parse_dict_response(self._RESPONSE)
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertEqual(block["word"], "serendipity")
        self.assertEqual(block["database"], "wn")
        self.assertEqual(block["description"], "WordNet (r) 3.0 (2006)")
        self.assertEqual(block["body"][0], "Serendipity")

    def test_parse_dict_response_no_match(self):
        self.assertEqual(self.parse_dict_response("552 No match\r\n"), [])

    def test_split_senses(self):
        block = {"body": ["Serendipity", "n 1: first sense", "n 2: second sense"]}
        self.assertEqual(
            self.split_senses(block), ["n 1: first sense", "n 2: second sense"]
        )

    def test_split_senses_falls_back_to_plain_text(self):
        block = {"body": ["a plain gcide-style definition"]}
        self.assertEqual(self.split_senses(block), ["a plain gcide-style definition"])

    def test_split_senses_handles_indented_dictorg_format(self):
        # dict.org WordNet indents senses and uses full part-of-speech
        # markers; continuation senses of the same POS are bare numbers.
        block = {
            "body": [
                "set",
                "    adj 1: on the point of doing something",
                "    2: fixed and unmoving",
                "    n 1: a group of things",
            ]
        }
        self.assertEqual(
            self.split_senses(block),
            [
                "adj 1: on the point of doing something",
                "2: fixed and unmoving",
                "n 1: a group of things",
            ],
        )

    def test_parse_define_args(self):
        self.assertEqual(self.parse_define_args("serendipity"), ("wn", "serendipity"))
        self.assertEqual(self.parse_define_args("-d gcide apple"), ("gcide", "apple"))
        self.assertEqual(self.parse_define_args("--database foldoc x"), ("foldoc", "x"))

    def test_handle_without_args_returns_usage(self):
        results = self.plugin.handle("")
        self.assertIn("Usage:", results[0].title)

    def test_handle_builds_sense_rows(self):
        block = {
            "word": "serendipity",
            "database": "wn",
            "description": "WordNet (r) 3.0 (2006)",
            "body": ["Serendipity", "n 1: good luck in making unexpected discoveries"],
        }
        with unittest.mock.patch("plugins.define.query_dict", return_value=[block]):
            results = self.plugin.handle("serendipity")
        self.assertEqual(len(results), 1)
        self.assertIn("good luck", results[0].title)
        self.assertIn("WordNet", results[0].subtitle)
        self.assertIn("serendipity", results[0].data)

    def test_handle_no_match(self):
        with unittest.mock.patch("plugins.define.query_dict", return_value=[]):
            results = self.plugin.handle("zzz")
        self.assertIn("No definition", results[0].title)

    def test_handle_network_failure(self):
        with unittest.mock.patch(
            "plugins.define.query_dict", side_effect=OSError("down")
        ):
            results = self.plugin.handle("serendipity")
        self.assertIn("failed", results[0].title.casefold())

    def test_debounce_before_lookup(self):
        # /define opens a TCP connection per query, so it must debounce
        # harder than the launcher default (150ms), like /translate.
        self.assertGreaterEqual(self.plugin.debounce_ms or 0, 400)

    def test_execute_copies_definition(self):
        import unittest.mock

        from utils.plugin_manager import PluginResult

        with unittest.mock.patch("plugins.define.copy_to_clipboard") as mock_copy:
            self.plugin.execute(PluginResult("x", data="serendipity: ..."))
        mock_copy.assert_called_once_with("serendipity: ...")


class ShortenPluginTest(unittest.TestCase):
    """Test the bundled /shorten plugin (HTTP mocked)."""

    @staticmethod
    def _fake_http(response, responses=None):
        """Build a side_effect for plugins.shorten.http_request returning
        *response* (or each of *responses* in turn)."""
        iterator = iter(responses) if responses is not None else None

        def fake_http(cancelled, method, url, **kwargs):
            return next(iterator) if iterator is not None else response

        return fake_http

    def setUp(self):
        from plugins.shorten import ShortenPlugin, normalize_url, shorten_url

        self.plugin = ShortenPlugin()
        self.normalize_url = normalize_url
        self.shorten_url = shorten_url

    def test_normalize_url(self):
        self.assertEqual(
            self.normalize_url("github.com/rubiin/tsumiki"),
            "https://github.com/rubiin/tsumiki",
        )
        self.assertEqual(
            self.normalize_url("https://example.com/a?b=c"),
            "https://example.com/a?b=c",
        )
        self.assertIsNone(self.normalize_url(""))
        self.assertIsNone(self.normalize_url("not a url"))
        self.assertIsNone(self.normalize_url("ftp://example.com/x"))

    def test_handle_shortens_with_is_gd(self):
        from types import SimpleNamespace

        response = SimpleNamespace(
            text="https://is.gd/AbCdEf", raise_for_status=lambda: None
        )
        with unittest.mock.patch(
            "plugins.shorten.http_request",
            side_effect=self._fake_http(response),
        ):
            results = self.plugin.handle("https://example.com/very/long")
        self.assertEqual(results[0].data, "https://is.gd/AbCdEf")
        self.assertIn("is.gd", results[0].subtitle)

    def test_handle_falls_back_to_tinyurl(self):
        from types import SimpleNamespace

        error = SimpleNamespace(
            text="Error: rate limited", raise_for_status=lambda: None
        )
        success = SimpleNamespace(
            text="https://tinyurl.com/abc123", raise_for_status=lambda: None
        )
        with unittest.mock.patch(
            "plugins.shorten.http_request",
            side_effect=self._fake_http(None, responses=[error, success]),
        ):
            results = self.plugin.handle("https://example.com/x")
        self.assertEqual(results[0].data, "https://tinyurl.com/abc123")
        self.assertIn("tinyurl", results[0].subtitle)

    def test_handle_invalid_url(self):
        results = self.plugin.handle("not a url")
        self.assertIn("doesn't look like a URL", results[0].title)

    def test_handle_all_providers_fail(self):
        from types import SimpleNamespace

        error = SimpleNamespace(text="Error: nope", raise_for_status=lambda: None)
        with unittest.mock.patch(
            "plugins.shorten.http_request",
            side_effect=self._fake_http(error),
        ):
            results = self.plugin.handle("https://example.com/x")
        self.assertIn("failed", results[0].title.casefold())

    def test_debounce_before_shorten(self):
        # /shorten hits a network endpoint per query, so it must debounce
        # harder than the launcher default (150ms), like /search.
        self.assertGreaterEqual(self.plugin.debounce_ms or 0, 400)

    def test_execute_copies_short_url(self):
        import unittest.mock

        from utils.plugin_manager import PluginResult

        with unittest.mock.patch("plugins.shorten.copy_to_clipboard") as mock_copy:
            self.plugin.execute(PluginResult("x", data="https://is.gd/x"))
        mock_copy.assert_called_once_with("https://is.gd/x")


if __name__ == "__main__":
    unittest.main()
