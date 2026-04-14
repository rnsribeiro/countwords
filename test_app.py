import sqlite3
import unittest
from collections import Counter
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from app import (
    SectionRepository,
    add_text_to_section,
    combine_section_counters,
    count_words,
    deserialize_sections,
    extract_words,
    filter_and_sort_words,
    make_histogram_bar,
    remove_section,
    remove_word_from_section,
    serialize_sections,
)
from lexical_lookup import (
    MetadataCacheRepository,
    deserialize_metadata_cache,
    extract_audio_url_from_dictionary_payload,
    extract_ipa_from_dictionary_payload,
    select_translation_from_payload,
    serialize_metadata_cache,
    strip_portuguese_article,
)


class WordCounterTests(unittest.TestCase):
    def test_extract_words_normalizes_case_and_keeps_accents(self) -> None:
        text = "Python, python! ma\u00e7\u00e3 e Jo\u00e3o-testam 2026."
        self.assertEqual(
            extract_words(text),
            ["python", "python", "ma\u00e7\u00e3", "e", "jo\u00e3o-testam", "2026"],
        )

    def test_count_words_counts_repeated_terms(self) -> None:
        counts = count_words("sol lua sol vento lua sol")
        self.assertEqual(counts["sol"], 3)
        self.assertEqual(counts["lua"], 2)
        self.assertEqual(counts["vento"], 1)

    def test_filter_and_sort_words_supports_search_and_alphabetic_order(self) -> None:
        counts = count_words("banana abacate banana amora amora amora")
        filtered = filter_and_sort_words(counts, "a", "Alfabetica (A-Z)")
        self.assertEqual(
            filtered,
            [("abacate", 1), ("amora", 3), ("banana", 2)],
        )

    def test_histogram_bar_scales_to_max_count(self) -> None:
        self.assertEqual(make_histogram_bar(5, 5), "#" * 28)
        self.assertEqual(make_histogram_bar(1, 5), "#" * 6)

    def test_select_translation_from_payload_prefers_best_match(self) -> None:
        payload = {
            "responseData": {"translatedText": "reserva"},
            "matches": [
                {"translation": "reserva", "match": 1, "quality": 74, "usage-count": 7},
                {"translation": "livro", "match": 1, "quality": 80, "usage-count": 9},
            ],
        }

        self.assertEqual(select_translation_from_payload(payload, "book"), "livro")

    def test_strip_portuguese_article_removes_leading_article(self) -> None:
        self.assertEqual(strip_portuguese_article("o livro"), "livro")
        self.assertEqual(strip_portuguese_article("as casas"), "casas")

    def test_extract_ipa_from_dictionary_payload_uses_first_available_phonetic(self) -> None:
        payload = [
            {
                "word": "hello",
                "phonetics": [{"text": "/h\u0259\u02c8l\u0259\u028a/"}],
            }
        ]

        self.assertEqual(
            extract_ipa_from_dictionary_payload(payload),
            "/h\u0259\u02c8l\u0259\u028a/",
        )

    def test_extract_audio_url_from_dictionary_payload_uses_first_audio(self) -> None:
        payload = [
            {
                "word": "book",
                "phonetics": [
                    {"audio": "https://example.com/book.mp3"},
                    {"audio": "https://example.com/book-alt.mp3"},
                ],
            }
        ]

        self.assertEqual(
            extract_audio_url_from_dictionary_payload(payload),
            "https://example.com/book.mp3",
        )

    def test_add_text_to_section_updates_existing_counter(self) -> None:
        sections = {"Livro A": Counter({"sol": 2})}
        updated = add_text_to_section(sections, "Livro A", "lua sol")

        self.assertEqual(updated, Counter({"sol": 3, "lua": 1}))
        self.assertEqual(sections["Livro A"], Counter({"sol": 3, "lua": 1}))

    def test_remove_word_from_section_removes_only_selected_word(self) -> None:
        sections = {"Livro A": Counter({"sol": 3, "lua": 1})}

        removed_count = remove_word_from_section(sections, "Livro A", "sol")

        self.assertEqual(removed_count, 3)
        self.assertEqual(sections["Livro A"], Counter({"lua": 1}))

    def test_remove_section_deletes_entire_section(self) -> None:
        sections = {
            "Livro A": Counter({"sol": 3}),
            "Livro B": Counter({"lua": 1}),
        }

        removed_counter = remove_section(sections, "Livro A")

        self.assertEqual(removed_counter, Counter({"sol": 3}))
        self.assertEqual(sections, {"Livro B": Counter({"lua": 1})})

    def test_combine_section_counters_merges_selected_sections(self) -> None:
        sections = {
            "Livro A": Counter({"sol": 2, "lua": 1}),
            "Livro B": Counter({"lua": 3, "vento": 1}),
            "Livro C": Counter({"mar": 4}),
        }

        combined = combine_section_counters(sections, ["Livro A", "Livro B"])
        self.assertEqual(combined, Counter({"lua": 4, "sol": 2, "vento": 1}))

    def test_serialize_and_deserialize_sections_keep_only_counts(self) -> None:
        payload = serialize_sections(
            {
                "Livro A": Counter({"sol": 2, "lua": 1}),
                "Livro B": Counter(),
            }
        )

        self.assertEqual(
            payload,
            {
                "version": 1,
                "sections": {
                    "Livro A": {"lua": 1, "sol": 2},
                    "Livro B": {},
                },
            },
        )

        loaded = deserialize_sections(payload)
        self.assertEqual(loaded["Livro A"], Counter({"sol": 2, "lua": 1}))
        self.assertEqual(loaded["Livro B"], Counter())

    def test_serialize_and_deserialize_metadata_cache(self) -> None:
        payload = serialize_metadata_cache(
            {
                "book": {
                    "translation": "livro",
                    "ipa": "/b\u028ak/",
                    "audio_url": "https://example.com/book.mp3",
                },
                "hello": {
                    "translation": "ola",
                    "ipa": "/h\u0259\u02c8l\u0259\u028a/",
                    "audio_url": "",
                },
            }
        )

        self.assertEqual(
            payload,
            {
                "version": 1,
                "items": {
                    "book": {
                        "translation": "livro",
                        "ipa": "/b\u028ak/",
                        "audio_url": "https://example.com/book.mp3",
                    },
                    "hello": {
                        "translation": "ola",
                        "ipa": "/h\u0259\u02c8l\u0259\u028a/",
                        "audio_url": "",
                    },
                },
            },
        )

        loaded = deserialize_metadata_cache(payload)
        self.assertEqual(loaded["book"]["translation"], "livro")
        self.assertEqual(loaded["hello"]["ipa"], "/h\u0259\u02c8l\u0259\u028a/")
        self.assertEqual(loaded["book"]["audio_url"], "https://example.com/book.mp3")

    def test_repository_persists_sections_to_disk(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            storage_path = Path(temporary_directory) / "countwords.db"
            repository = SectionRepository(storage_path)
            expected_sections = {
                "Livro A": Counter({"sol": 2, "lua": 1}),
                "Livro B": Counter(),
            }

            repository.save_sections(expected_sections)

            with closing(sqlite3.connect(storage_path)) as connection:
                section_rows = connection.execute(
                    "SELECT title FROM sections ORDER BY lower(title), title"
                ).fetchall()
                count_rows = connection.execute(
                    """
                    SELECT section_title, word, count
                    FROM section_counts
                    ORDER BY lower(section_title), section_title, word
                    """
                ).fetchall()

            self.assertEqual(
                section_rows,
                [("Livro A",), ("Livro B",)],
            )
            self.assertEqual(
                count_rows,
                [("Livro A", "lua", 1), ("Livro A", "sol", 2)],
            )

            loaded_sections = repository.load_sections()
            self.assertEqual(loaded_sections, expected_sections)

    def test_metadata_cache_repository_persists_to_disk(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            storage_path = Path(temporary_directory) / "countwords.db"
            repository = MetadataCacheRepository(storage_path)
            expected_cache = {
                "book": {
                    "translation": "livro",
                    "ipa": "/b\u028ak/",
                    "audio_url": "https://example.com/book.mp3",
                },
                "hello": {
                    "translation": "ola",
                    "ipa": "/h\u0259\u02c8l\u0259\u028a/",
                    "audio_url": "",
                },
            }

            repository.save_cache(expected_cache)

            with closing(sqlite3.connect(storage_path)) as connection:
                metadata_rows = connection.execute(
                    """
                    SELECT word, translation, ipa
                    , audio_url
                    FROM word_metadata
                    ORDER BY word
                    """
                ).fetchall()

            self.assertEqual(
                metadata_rows,
                [
                    ("book", "livro", "/b\u028ak/", "https://example.com/book.mp3"),
                    ("hello", "ola", "/h\u0259\u02c8l\u0259\u028a/", ""),
                ],
            )

            loaded_cache = repository.load_cache()
            self.assertEqual(loaded_cache, expected_cache)


if __name__ == "__main__":
    unittest.main()
