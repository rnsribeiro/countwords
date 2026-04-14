from __future__ import annotations

import json
import sqlite3
from collections import Counter
from contextlib import contextmanager
from pathlib import Path


DATABASE_FILE = Path(__file__).with_name("countwords.db")
LEGACY_SECTIONS_FILE = Path(__file__).with_name("section_counts.json")
LEGACY_METADATA_FILE = Path(__file__).with_name("word_metadata_cache.json")


def normalize_section_title(title: str) -> str:
    return " ".join(title.strip().split())


class ProjectDatabase:
    def __init__(self, database_path: Path = DATABASE_FILE) -> None:
        self.database_path = database_path
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def session(self):
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.session() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sections (
                    title TEXT PRIMARY KEY
                );

                CREATE TABLE IF NOT EXISTS section_counts (
                    section_title TEXT NOT NULL,
                    word TEXT NOT NULL,
                    count INTEGER NOT NULL CHECK(count > 0),
                    PRIMARY KEY (section_title, word),
                    FOREIGN KEY (section_title) REFERENCES sections(title) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS word_metadata (
                    word TEXT PRIMARY KEY,
                    translation TEXT NOT NULL,
                    ipa TEXT NOT NULL,
                    audio_url TEXT NOT NULL
                );
                """
            )


class SectionRepository:
    def __init__(self, database_path: Path = DATABASE_FILE) -> None:
        self.database = ProjectDatabase(database_path)
        self.database_path = database_path
        self._migrate_legacy_sections_if_needed()

    def load_sections(self) -> dict[str, Counter[str]]:
        with self.database.session() as connection:
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

        sections: dict[str, Counter[str]] = {
            str(title): Counter() for (title,) in section_rows
        }

        for section_title, word, count in count_rows:
            sections[str(section_title)][str(word)] = int(count)

        return sections

    def save_sections(self, sections: dict[str, Counter[str]]) -> None:
        ordered_titles = sorted(sections, key=str.casefold)

        with self.database.session() as connection:
            connection.execute("DELETE FROM section_counts")
            connection.execute("DELETE FROM sections")

            for title in ordered_titles:
                connection.execute(
                    "INSERT INTO sections (title) VALUES (?)",
                    (title,),
                )

                for word, count in sorted(sections[title].items(), key=lambda item: item[0]):
                    connection.execute(
                        """
                        INSERT INTO section_counts (section_title, word, count)
                        VALUES (?, ?, ?)
                        """,
                        (title, word, int(count)),
                    )

    def _migrate_legacy_sections_if_needed(self) -> None:
        if not LEGACY_SECTIONS_FILE.exists():
            return

        with self.database.session() as connection:
            existing_sections = connection.execute(
                "SELECT COUNT(*) FROM sections"
            ).fetchone()[0]

        if existing_sections:
            return

        try:
            payload = json.loads(LEGACY_SECTIONS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(payload, dict):
            return

        raw_sections = payload.get("sections", {})

        if not isinstance(raw_sections, dict):
            return

        sections: dict[str, Counter[str]] = {}

        for raw_title, raw_counts in raw_sections.items():
            if not isinstance(raw_title, str):
                continue

            title = normalize_section_title(raw_title)

            if not title or not isinstance(raw_counts, dict):
                continue

            counter: Counter[str] = Counter()

            for raw_word, raw_count in raw_counts.items():
                if not isinstance(raw_word, str):
                    continue
                if type(raw_count) is not int or raw_count <= 0:
                    continue
                counter[raw_word] = raw_count

            sections[title] = counter

        if sections:
            self.save_sections(sections)


class MetadataCacheRepository:
    def __init__(self, database_path: Path = DATABASE_FILE) -> None:
        self.database = ProjectDatabase(database_path)
        self.database_path = database_path
        self._remove_legacy_metadata_file_if_needed()

    def load_cache(self) -> dict[str, dict[str, str]]:
        with self.database.session() as connection:
            rows = connection.execute(
                """
                SELECT word, translation, ipa, audio_url
                FROM word_metadata
                ORDER BY word
                """
            ).fetchall()

        cache: dict[str, dict[str, str]] = {}

        for word, translation, ipa, audio_url in rows:
            cache[str(word)] = {
                "translation": str(translation),
                "ipa": str(ipa),
                "audio_url": str(audio_url),
            }

        return cache

    def save_cache(self, cache: dict[str, dict[str, str]]) -> None:
        with self.database.session() as connection:
            connection.execute("DELETE FROM word_metadata")

            for word in sorted(cache, key=str.casefold):
                metadata = cache[word]
                connection.execute(
                    """
                    INSERT OR REPLACE INTO word_metadata (word, translation, ipa, audio_url)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        word,
                        metadata.get("translation", ""),
                        metadata.get("ipa", ""),
                        metadata.get("audio_url", ""),
                    ),
                )

    def _remove_legacy_metadata_file_if_needed(self) -> None:
        if LEGACY_METADATA_FILE.exists():
            try:
                LEGACY_METADATA_FILE.unlink()
            except OSError:
                pass
