from __future__ import annotations

import json
import os
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, Signal

from storage_db import MetadataCacheRepository


TRANSLATION_TARGET_LANGUAGE = "pt-BR"
PORTUGUESE_ARTICLES = ("o ", "a ", "os ", "as ", "um ", "uma ", "uns ", "umas ")
REQUEST_HEADERS = {"User-Agent": "CountWordsApp/1.0"}


def normalize_translation_text(text: object) -> str:
    return " ".join(str(text).replace("\n", " ").split())


def strip_portuguese_article(text: str) -> str:
    normalized = normalize_translation_text(text)
    lowered = normalized.casefold()

    for article in PORTUGUESE_ARTICLES:
        if lowered.startswith(article):
            return normalized[len(article) :].strip(" .,:;!?")

    return normalized.strip(" .,:;!?")


def safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def metadata_cache_key(word: str) -> str:
    return word.casefold()


def translation_mentions_source_word(translation: str, source_word: str) -> bool:
    normalized_translation = normalize_translation_text(translation).casefold()
    normalized_source_word = source_word.casefold()
    return normalized_source_word in normalized_translation


def select_translation_from_payload(payload: dict[str, object], source_word: str) -> str:
    matches = payload.get("matches", [])
    source_word_normalized = source_word.casefold()
    candidates: list[tuple[float, float, int, int, str]] = []

    if isinstance(matches, list):
        for raw_match in matches:
            if not isinstance(raw_match, dict):
                continue

            translation = normalize_translation_text(raw_match.get("translation", ""))

            if not translation:
                continue

            match_score = safe_float(raw_match.get("match"))
            quality = safe_float(raw_match.get("quality"))
            usage_count = safe_int(raw_match.get("usage-count"))
            translation_penalty = 0 if translation.casefold() != source_word_normalized else 1

            candidates.append(
                (match_score, quality, usage_count, -translation_penalty, translation)
            )

    if candidates:
        return max(candidates)[4]

    response_data = payload.get("responseData", {})

    if isinstance(response_data, dict):
        return normalize_translation_text(response_data.get("translatedText", ""))

    return ""


def extract_ipa_from_dictionary_payload(payload: object) -> str:
    if not isinstance(payload, list):
        return ""

    for entry in payload:
        if not isinstance(entry, dict):
            continue

        phonetic = normalize_translation_text(entry.get("phonetic", ""))
        if phonetic:
            return phonetic

        phonetics = entry.get("phonetics", [])

        if not isinstance(phonetics, list):
            continue

        for phonetic_item in phonetics:
            if not isinstance(phonetic_item, dict):
                continue

            phonetic_text = normalize_translation_text(phonetic_item.get("text", ""))

            if phonetic_text:
                return phonetic_text

    return ""


def extract_audio_url_from_dictionary_payload(payload: object) -> str:
    if not isinstance(payload, list):
        return ""

    for entry in payload:
        if not isinstance(entry, dict):
            continue

        phonetics = entry.get("phonetics", [])

        if not isinstance(phonetics, list):
            continue

        for phonetic_item in phonetics:
            if not isinstance(phonetic_item, dict):
                continue

            audio_url = normalize_translation_text(phonetic_item.get("audio", ""))

            if audio_url:
                if audio_url.startswith("//"):
                    return "https:" + audio_url
                return audio_url

    return ""


def extract_primary_part_of_speech(payload: object) -> str:
    if not isinstance(payload, list):
        return ""

    for entry in payload:
        if not isinstance(entry, dict):
            continue

        meanings = entry.get("meanings", [])

        if not isinstance(meanings, list):
            continue

        for meaning in meanings:
            if not isinstance(meaning, dict):
                continue

            part_of_speech = normalize_translation_text(meaning.get("partOfSpeech", ""))

            if part_of_speech:
                return part_of_speech.casefold()

    return ""


def serialize_metadata_cache(cache: dict[str, dict[str, str]]) -> dict[str, object]:
    return {
        "version": 1,
        "items": {
            key: {
                "translation": value.get("translation", ""),
                "ipa": value.get("ipa", ""),
                "audio_url": value.get("audio_url", ""),
            }
            for key, value in sorted(cache.items())
        },
    }


def deserialize_metadata_cache(payload: dict[str, object]) -> dict[str, dict[str, str]]:
    raw_items = payload.get("items", {})

    if not isinstance(raw_items, dict):
        raise ValueError("Formato invalido para o cache de metadados.")

    cache: dict[str, dict[str, str]] = {}

    for raw_key, raw_value in raw_items.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, dict):
            continue

        translation = normalize_translation_text(raw_value.get("translation", ""))
        ipa = normalize_translation_text(raw_value.get("ipa", ""))
        audio_url = normalize_translation_text(raw_value.get("audio_url", ""))
        cache[raw_key] = {
            "translation": translation,
            "ipa": ipa,
            "audio_url": audio_url,
        }

    return cache


class WordMetadataService:
    def __init__(self, repository: MetadataCacheRepository | None = None) -> None:
        self.repository = repository or MetadataCacheRepository()
        self.lock = Lock()

        try:
            self.cache = self.repository.load_cache()
        except (OSError, ValueError, json.JSONDecodeError):
            self.cache: dict[str, dict[str, str]] = {}

    def get_cached_metadata(self, word: str) -> dict[str, str] | None:
        with self.lock:
            metadata = self.cache.get(metadata_cache_key(word))
            return dict(metadata) if metadata else None

    def lookup_metadata(self, word: str) -> dict[str, str]:
        cached = self.get_cached_metadata(word)

        if cached:
            return cached

        dictionary_payload = self._fetch_dictionary_payload(word)
        ipa = extract_ipa_from_dictionary_payload(dictionary_payload) or "-"
        audio_url = extract_audio_url_from_dictionary_payload(dictionary_payload)
        part_of_speech = extract_primary_part_of_speech(dictionary_payload)
        translation = self._fetch_translation(word, part_of_speech) or "-"
        metadata = {"translation": translation, "ipa": ipa, "audio_url": audio_url}

        with self.lock:
            self.cache[metadata_cache_key(word)] = metadata

            try:
                self.repository.save_cache(self.cache)
            except OSError:
                pass

        return dict(metadata)

    def _fetch_translation(self, word: str, part_of_speech: str) -> str:
        noun_biased_translation = ""

        if part_of_speech == "noun":
            noun_payload = self._fetch_mymemory_payload(f"the {word}")
            noun_translation = select_translation_from_payload(noun_payload, word)
            noun_biased_translation = strip_portuguese_article(noun_translation)

        direct_payload = self._fetch_mymemory_payload(word)
        direct_translation = normalize_translation_text(
            select_translation_from_payload(direct_payload, word)
        )

        if noun_biased_translation and not translation_mentions_source_word(
            noun_biased_translation, word
        ):
            return noun_biased_translation

        return direct_translation

    def _fetch_mymemory_payload(self, query: str) -> dict[str, object]:
        params = {
            "q": query,
            "langpair": f"en|{TRANSLATION_TARGET_LANGUAGE}",
        }

        contact_email = os.getenv("MYMEMORY_EMAIL", "").strip()

        if contact_email:
            params["de"] = contact_email

        request = Request(
            "https://api.mymemory.translated.net/get?" + urlencode(params),
            headers=REQUEST_HEADERS,
        )

        try:
            with urlopen(request, timeout=20) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
            return {}

        return payload if isinstance(payload, dict) else {}

    def _fetch_dictionary_payload(self, word: str) -> object:
        request = Request(
            f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(word)}",
            headers=REQUEST_HEADERS,
        )

        try:
            with urlopen(request, timeout=20) as response:
                payload = json.load(response)
        except HTTPError:
            return []
        except (URLError, TimeoutError, OSError, json.JSONDecodeError):
            return []

        return payload


class MetadataLookupWorker(QObject):
    metadata_ready = Signal(int, str, dict)
    finished = Signal(int)

    def __init__(
        self,
        request_id: int,
        words: list[str],
        metadata_service: WordMetadataService,
    ) -> None:
        super().__init__()
        self.request_id = request_id
        self.words = words
        self.metadata_service = metadata_service
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        for word in self.words:
            if self._cancelled:
                break

            metadata = self.metadata_service.lookup_metadata(word)

            if self._cancelled:
                break

            self.metadata_ready.emit(self.request_id, word, metadata)

        self.finished.emit(self.request_id)
