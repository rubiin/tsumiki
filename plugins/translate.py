"""Launcher slash command: /translate — translate text and copy the result.

The target language can be given with "in <language>" or "to <language>",
e.g. ``/translate hello in nepali``; otherwise the plugin default is used.
"""

import re
from typing import ClassVar

from utils.plugin_manager import (
    LauncherPlugin,
    PluginCancelledError,
    PluginResult,
    cached_handle,
    copy_to_clipboard,
)

_TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
#: Google rejects longer payloads ("400. That's an error...").
_MAX_TEXT_LENGTH = 1830

#: Language name -> Google code; unknown names fall back to the default target.
_LANGUAGES = {
    "afrikaans": "af",
    "albanian": "sq",
    "amharic": "am",
    "arabic": "ar",
    "armenian": "hy",
    "azerbaijani": "az",
    "basque": "eu",
    "belarusian": "be",
    "bengali": "bn",
    "bosnian": "bs",
    "bulgarian": "bg",
    "catalan": "ca",
    "cebuano": "ceb",
    "chichewa": "ny",
    "chinese": "zh-CN",
    "chinese simplified": "zh-CN",
    "chinese traditional": "zh-TW",
    "corsican": "co",
    "croatian": "hr",
    "czech": "cs",
    "danish": "da",
    "dutch": "nl",
    "english": "en",
    "esperanto": "eo",
    "estonian": "et",
    "filipino": "tl",
    "finnish": "fi",
    "french": "fr",
    "frisian": "fy",
    "galician": "gl",
    "georgian": "ka",
    "german": "de",
    "greek": "el",
    "gujarati": "gu",
    "haitian creole": "ht",
    "hausa": "ha",
    "hawaiian": "haw",
    "hebrew": "he",
    "hindi": "hi",
    "hmong": "hmn",
    "hungarian": "hu",
    "icelandic": "is",
    "igbo": "ig",
    "indonesian": "id",
    "irish": "ga",
    "italian": "it",
    "japanese": "ja",
    "javanese": "jw",
    "kannada": "kn",
    "kazakh": "kk",
    "khmer": "km",
    "korean": "ko",
    "kurdish (kurmanji)": "ku",
    "kyrgyz": "ky",
    "lao": "lo",
    "latin": "la",
    "latvian": "lv",
    "lithuanian": "lt",
    "luxembourgish": "lb",
    "macedonian": "mk",
    "malagasy": "mg",
    "malay": "ms",
    "malayalam": "ml",
    "maltese": "mt",
    "maori": "mi",
    "marathi": "mr",
    "mongolian": "mn",
    "myanmar (burmese)": "my",
    "nepali": "ne",
    "norwegian": "no",
    "odia": "or",
    "pashto": "ps",
    "persian": "fa",
    "polish": "pl",
    "portuguese": "pt",
    "punjabi": "pa",
    "romanian": "ro",
    "russian": "ru",
    "samoan": "sm",
    "scots gaelic": "gd",
    "serbian": "sr",
    "sesotho": "st",
    "shona": "sn",
    "sindhi": "sd",
    "sinhala": "si",
    "slovak": "sk",
    "slovenian": "sl",
    "somali": "so",
    "spanish": "es",
    "sundanese": "su",
    "swahili": "sw",
    "swedish": "sv",
    "tajik": "tg",
    "tamil": "ta",
    "telugu": "te",
    "thai": "th",
    "turkish": "tr",
    "ukrainian": "uk",
    "urdu": "ur",
    "uzbek": "uz",
    "vietnamese": "vi",
    "welsh": "cy",
    "xhosa": "xh",
    "yiddish": "yi",
    "yoruba": "yo",
    "zulu": "zu",
}


#: Matched against the original text, never a casefolded copy: casefold() is not
#: length-preserving (ß -> ss, ﬃ -> ffi), so casefolded offsets cut mid-word.
_DIRECTIVE_RE = re.compile(r"\s+(?:in|to)\s+(\S.*?)\s*$", re.IGNORECASE)
#: Bare directive with no text, e.g. "/translate in nepali".
_BARE_DIRECTIVE_RE = re.compile(r"^(?:in|to)\s+(\S.*?)\s*$", re.IGNORECASE)


def _find_directive(pattern: re.Pattern[str], text: str) -> tuple[int, str] | None:
    """Return (split_index, language_code) for the last directive in *text*."""
    for match in reversed(list(pattern.finditer(text))):
        code = _LANGUAGES.get(match.group(1).casefold())
        if code is not None:
            return match.start(), code
    return None


def parse_target_language(text: str) -> tuple[str, str]:
    """Split *text* into (translate_text, target_lang) from a trailing
    "in <language>" / "to <language>" directive."""
    stripped = text.strip()
    for pattern in (_DIRECTIVE_RE, _BARE_DIRECTIVE_RE):
        found = _find_directive(pattern, stripped)
        if found is not None:
            return stripped[: found[0]], found[1]
    return text, None


class TranslatePlugin(LauncherPlugin):
    """Slash command: /translate — translate text and copy the result."""

    name = "translate"
    description = "Translate text (e.g. 'hello in nepali')"
    icon = "preferences-desktop-locale-symbolic"
    aliases: ClassVar[list[str]] = ["tr", "t"]
    # Each query is a network request; debounce instead of firing per keystroke.
    debounce_ms = 500
    #: Session cache TTL — repeat translations skip the network.
    cache_ttl_seconds = 300
    #: Default target language code (used when the query has no "in <lang>").
    target_lang = "en"

    def _fetch(self, text: str, target_lang: str) -> str:
        response = self.run_http(
            "GET",
            _TRANSLATE_URL,
            params={
                "client": "gtx",
                "sl": "auto",
                "tl": target_lang,
                "dt": "t",
                "q": text,
            },
        )
        response.raise_for_status()
        payload = response.json()
        segments = payload[0] if isinstance(payload, list) and payload else []
        return "".join(
            part[0] for part in segments if isinstance(part, list) and part and part[0]
        ).strip()

    @cached_handle()
    def handle(self, args: str) -> list[PluginResult]:
        text = args.strip()
        if len(text) > _MAX_TEXT_LENGTH:
            return [
                PluginResult(
                    "Text is too long",
                    subtitle=f"Google accepts up to {_MAX_TEXT_LENGTH} characters",
                    icon="dialog-warning-symbolic",
                )
            ]
        if not text:
            return [
                PluginResult(
                    "Usage: /translate <text>",
                    subtitle=(
                        "e.g. /translate bonjour  or  /translate hello in nepali"
                    ),
                    icon=self.icon,
                )
            ]

        text, target_lang = parse_target_language(text)
        if not text:
            # Query was only a language directive, e.g. "/translate in nepali".
            return [
                PluginResult(
                    "Usage: /translate <text> [in <language>]",
                    subtitle=(
                        "e.g. /translate hello in nepali  "
                        "(source language is auto-detected)"
                    ),
                    icon=self.icon,
                )
            ]
        target_lang = target_lang or self.target_lang

        try:
            translation = self._fetch(text, target_lang)
        except PluginCancelledError:
            return []
        except Exception as exc:
            return [
                PluginResult(
                    "Translation failed",
                    subtitle=f"{exc}",
                    icon="network-error-symbolic",
                )
            ]
        if not translation:
            return [
                PluginResult(
                    "No translation returned",
                    icon="dialog-warning-symbolic",
                )
            ]
        return [
            PluginResult(
                translation,
                subtitle=(
                    f"Press Enter to copy ({target_lang})"
                    if target_lang != self.target_lang
                    else "Press Enter to copy the translation"
                ),
                icon=self.icon,
                data=translation,
            )
        ]

    def execute(self, result: PluginResult | None = None) -> bool:
        if result is not None and result.data:
            copy_to_clipboard(str(result.data))
        return False  # close the launcher after copying
