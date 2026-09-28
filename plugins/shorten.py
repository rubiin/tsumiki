"""Launcher slash command: /shorten — shorten a URL (is.gd, TinyURL fallback)."""

from typing import ClassVar
from urllib.parse import urlparse

from utils.plugin_manager import (
    LauncherPlugin,
    PluginCancelledError,
    PluginResult,
    cached_handle,
    copy_to_clipboard,
    http_request,
)

#: provider -> (endpoint, params); both return the short URL as plain text.
_SHORTENERS = {
    "is.gd": ("https://is.gd/create.php", {"format": "simple"}),
    "tinyurl": ("https://tinyurl.com/api-create.php", {}),
}


def normalize_url(text: str) -> str | None:
    """Return *text* as an absolute http(s) URL, or None if unusable."""
    text = text.strip()
    if not text:
        return None
    if "://" not in text:
        text = f"https://{text}"
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or not host:
        return None
    if "." not in host and host != "localhost":
        return None
    return text


def shorten_url(url: str, provider: str = "is.gd", cancelled=None) -> str:
    """Shorten *url*; *cancelled* aborts a superseded request mid-flight."""
    base, extra_params = _SHORTENERS[provider]
    response = http_request(cancelled, "GET", base, params={**extra_params, "url": url})
    response.raise_for_status()
    short = response.text.strip()
    if short.startswith("Error:"):
        raise ValueError(short)
    if not short.startswith("http"):
        raise ValueError(f"unexpected response: {short[:60]}")
    return short


class ShortenPlugin(LauncherPlugin):
    """Slash command: /shorten — shorten a URL and copy it."""

    name = "shorten"
    description = "Shorten a URL (is.gd / TinyURL)"
    icon = "insert-link-symbolic"
    aliases: ClassVar[list[str]] = ["short", "tiny"]
    # Each query is a network request — debounce like the other plugins.
    debounce_ms = 500
    #: Session cache TTL — short URLs are permanent.
    cache_ttl_seconds = 3600

    @cached_handle()
    def handle(self, args: str) -> list[PluginResult]:
        url = normalize_url(args)
        if url is None:
            return [
                PluginResult(
                    "That doesn't look like a URL",
                    subtitle=(
                        "e.g. /shorten https://github.com/rubiin/tsumiki  ·  "
                        "/shorten example.com (https:// is added)"
                    ),
                    icon=self.icon,
                )
            ]
        if self.is_cancelled():
            return []  # superseded before the request went out

        errors = []
        for provider in ("is.gd", "tinyurl"):
            if self.is_cancelled():
                return []
            try:
                short = shorten_url(url, provider, cancelled=self.is_cancelled)
            except PluginCancelledError:
                return []
            except Exception as exc:
                errors.append(f"{provider}: {exc}")
                continue
            return [
                PluginResult(
                    short,
                    subtitle=f"via {provider} · Press Enter to copy",
                    icon=self.icon,
                    data=short,
                )
            ]
        return [
            PluginResult(
                "Shortening failed",
                subtitle="; ".join(errors)[:120],
                icon="network-error-symbolic",
            )
        ]

    def execute(self, result: PluginResult | None = None) -> bool:
        if result is not None and result.data:
            copy_to_clipboard(str(result.data))
        return False  # close the launcher after copying
