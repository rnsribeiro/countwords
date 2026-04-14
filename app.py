from __future__ import annotations

import json
import re
import sys
from collections import Counter
from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from storage_db import SectionRepository


TOKEN_PATTERN = re.compile(
    r"[\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u00FFA-Za-z0-9]+"
    r"(?:[-'][\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u00FFA-Za-z0-9]+)*"
)
SORT_OPTIONS = [
    "Quantidade (maior para menor)",
    "Quantidade (menor para maior)",
    "Alfabetica (A-Z)",
    "Alfabetica (Z-A)",
]


def extract_words(text: str) -> list[str]:
    normalized = text.casefold()
    return TOKEN_PATTERN.findall(normalized)


def count_words(text: str) -> Counter[str]:
    return Counter(extract_words(text))


def sort_word_counts(items: list[tuple[str, int]], option: str) -> list[tuple[str, int]]:
    if option == "Quantidade (menor para maior)":
        return sorted(items, key=lambda item: (item[1], item[0]))
    if option == "Alfabetica (A-Z)":
        return sorted(items, key=lambda item: item[0])
    if option == "Alfabetica (Z-A)":
        return sorted(items, key=lambda item: item[0], reverse=True)

    return sorted(items, key=lambda item: (-item[1], item[0]))


def filter_and_sort_words(
    counter: Counter[str], query: str, sort_option: str
) -> list[tuple[str, int]]:
    items = list(counter.items())
    normalized_query = query.strip().casefold()

    if normalized_query:
        items = [
            (word, count) for word, count in items if normalized_query in word.casefold()
        ]

    return sort_word_counts(items, sort_option)


def make_histogram_bar(count: int, max_count: int, width: int = 28) -> str:
    if max_count == 0:
        return ""

    bar_length = max(1, round((count / max_count) * width))
    return "#" * bar_length


def normalize_section_title(title: str) -> str:
    return " ".join(title.strip().split())


def merge_counters(counters: Iterable[Counter[str]]) -> Counter[str]:
    merged: Counter[str] = Counter()

    for counter in counters:
        merged.update(counter)

    return merged


def combine_section_counters(
    sections: dict[str, Counter[str]], section_titles: Iterable[str] | None = None
) -> Counter[str]:
    if section_titles is None:
        return merge_counters(sections.values())

    return merge_counters(
        sections[title] for title in section_titles if title in sections
    )


def add_text_to_section(
    sections: dict[str, Counter[str]], section_title: str, text: str
) -> Counter[str]:
    normalized_title = normalize_section_title(section_title)

    if not normalized_title:
        raise ValueError("Informe um título de seção válido.")

    added_words = count_words(text)

    if not added_words:
        raise ValueError("Nenhuma palavra foi encontrada no texto informado.")

    section_counter = sections.setdefault(normalized_title, Counter())
    section_counter.update(added_words)
    return section_counter


def remove_section(
    sections: dict[str, Counter[str]], section_title: str
) -> Counter[str]:
    normalized_title = normalize_section_title(section_title)

    if normalized_title not in sections:
        raise ValueError("A seção informada não foi encontrada.")

    return sections.pop(normalized_title)


def remove_word_from_section(
    sections: dict[str, Counter[str]], section_title: str, word: str
) -> int:
    normalized_title = normalize_section_title(section_title)
    normalized_word = word.strip().casefold()

    if not normalized_title or normalized_title not in sections:
        raise ValueError("A seção informada não foi encontrada.")

    if not normalized_word:
        raise ValueError("Informe uma palavra válida para exclusão.")

    removed_count = sections[normalized_title].pop(normalized_word, None)

    if removed_count is None:
        raise ValueError(
            f"A palavra '{normalized_word}' não existe na seção '{normalized_title}'."
        )

    return removed_count


def serialize_sections(sections: dict[str, Counter[str]]) -> dict[str, object]:
    ordered_titles = sorted(sections, key=str.casefold)
    payload: dict[str, object] = {"version": 1, "sections": {}}
    section_payload: dict[str, dict[str, int]] = {}

    for title in ordered_titles:
        sorted_counts = dict(sorted(sections[title].items(), key=lambda item: item[0]))
        section_payload[title] = sorted_counts

    payload["sections"] = section_payload
    return payload


def deserialize_sections(payload: dict[str, object]) -> dict[str, Counter[str]]:
    raw_sections = payload.get("sections", {})

    if not isinstance(raw_sections, dict):
        raise ValueError("Formato inválido para as seções salvas.")

    sections: dict[str, Counter[str]] = {}

    for raw_title, raw_counts in raw_sections.items():
        if not isinstance(raw_title, str):
            continue

        title = normalize_section_title(raw_title)

        if not title:
            continue

        if not isinstance(raw_counts, dict):
            continue

        counter: Counter[str] = Counter()

        for raw_word, raw_count in raw_counts.items():
            if not isinstance(raw_word, str):
                continue
            if type(raw_count) is not int or raw_count <= 0:
                continue
            counter[raw_word] = raw_count

        sections[title] = counter

    return dict(sorted(sections.items(), key=lambda item: item[0].casefold()))



class HistogramWindow(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Histograma Detalhado")
        self.resize(1080, 720)
        self.setMinimumSize(860, 520)
        self.delete_word_callback = None
        self.base_counter: Counter[str] = Counter()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.summary_label = QLabel(
            "Abra esta janela para visualizar o histograma, pesquisar palavras e excluir itens."
        )
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        controls_layout = QGridLayout()
        controls_layout.setHorizontalSpacing(12)
        controls_layout.setVerticalSpacing(8)
        layout.addLayout(controls_layout)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Pesquisar palavra dentro do histograma")
        controls_layout.addWidget(self.search_input, 0, 0)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(SORT_OPTIONS)
        controls_layout.addWidget(self.sort_combo, 0, 1)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Palavra", "Excluir", "Histograma"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table, stretch=1)

        self.search_input.textChanged.connect(self.refresh_view)
        self.sort_combo.currentTextChanged.connect(self.refresh_view)

    def populate(
        self,
        counter: Counter[str],
        selection_summary: str,
        delete_word_callback,
        search_query: str = "",
        sort_option: str = "Quantidade (maior para menor)",
    ) -> None:
        self.base_counter = Counter(counter)
        self.delete_word_callback = delete_word_callback
        self.summary_label.setText(selection_summary)
        self.search_input.blockSignals(True)
        self.sort_combo.blockSignals(True)
        self.search_input.setText(search_query)
        self.sort_combo.setCurrentText(sort_option)
        self.search_input.blockSignals(False)
        self.sort_combo.blockSignals(False)
        self.refresh_view()

    def refresh_view(self) -> None:
        items = filter_and_sort_words(
            self.base_counter,
            self.search_input.text(),
            self.sort_combo.currentText(),
        )
        self.table.setRowCount(len(items))
        max_count = max((count for _, count in items), default=0)

        for row_index, (word, count) in enumerate(items):
            self.table.setItem(row_index, 0, QTableWidgetItem(word))

            delete_button = QPushButton("Excluir")
            delete_button.clicked.connect(
                lambda _checked=False, current_word=word: self._delete_word(current_word)
            )
            self.table.setCellWidget(row_index, 1, delete_button)

            progress_bar = QProgressBar()
            progress_bar.setRange(0, max_count if max_count else 1)
            progress_bar.setValue(count)
            progress_bar.setTextVisible(True)
            progress_bar.setFormat(f"{count}")
            self.table.setCellWidget(row_index, 2, progress_bar)

        self.table.resizeRowsToContents()

    def _delete_word(self, word: str) -> None:
        if self.delete_word_callback is not None:
            self.delete_word_callback(word)


class WordCounterApp(QWidget):

    def __init__(
        self,
        repository: SectionRepository | None = None,
    ) -> None:
        super().__init__()
        self.repository = repository or SectionRepository()
        self.sections: dict[str, Counter[str]] = {}
        self.current_combined_counter: Counter[str] = Counter()
        self.filtered_items: list[tuple[str, int]] = []
        self.current_row_by_word: dict[str, int] = {}
        self.histogram_window: HistogramWindow | None = None

        try:
            self.sections = self.repository.load_sections()
            self.initial_status_message = (
                f"{len(self.sections)} seção(oes) carregada(s) do armazenamento local."
                if self.sections
                else "Crie uma seção para comecar. Apenas as contagens seráo persistidas."
            )
        except (OSError, ValueError, json.JSONDecodeError):
            self.sections = {}
            self.initial_status_message = (
                "não foi possivel carregar os dados salvos. Um novo arquivo será criado ao salvar."
            )

        self._build_window()
        self._build_ui()
        self._bind_events()
        self._apply_styles()
        self._sync_section_controls()
        self.entry_status_label.setText(self.initial_status_message)
        self.refresh_results()

    def _build_window(self) -> None:
        self.setWindowTitle("Contador de Palavras por seções")
        self.resize(1200, 800)
        self.setMinimumSize(980, 680)

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(14)

        title_label = QLabel("Histograma de Palavras por seções")
        title_label.setProperty("role", "title")
        root_layout.addWidget(title_label)

        subtitle_label = QLabel(
            "Crie seções com o título de um livro, envie mais texto para cada uma delas e "
            "abra o histograma detalhado para pesquisar e excluir palavras."
        )
        subtitle_label.setWordWrap(True)
        subtitle_label.setProperty("role", "muted")
        root_layout.addWidget(subtitle_label)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)
        root_layout.addLayout(content_layout, stretch=1)

        left_panel = self._create_panel()
        right_panel = self._create_panel()
        content_layout.addWidget(left_panel, stretch=10)
        content_layout.addWidget(right_panel, stretch=9)

        left_layout = left_panel.layout()
        right_layout = right_panel.layout()

        title_section_label = QLabel("Criar nova seção")
        title_section_label.setProperty("role", "section")
        left_layout.addWidget(title_section_label)

        create_layout = QHBoxLayout()
        create_layout.setSpacing(10)
        left_layout.addLayout(create_layout)

        self.section_title_input = QLineEdit()
        self.section_title_input.setPlaceholderText("Ex.: Dom Casmurro")
        create_layout.addWidget(self.section_title_input, stretch=1)

        self.create_section_button = QPushButton("Criar seção")
        create_layout.addWidget(self.create_section_button)

        target_label = QLabel("seção de destino para o texto")
        target_label.setProperty("role", "section")
        left_layout.addWidget(target_label)

        self.target_section_combo = QComboBox()
        self.target_section_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        left_layout.addWidget(self.target_section_combo)

        section_actions_layout = QHBoxLayout()
        section_actions_layout.setSpacing(10)
        left_layout.addLayout(section_actions_layout)

        self.delete_section_button = QPushButton("Excluir seção selecionada")
        section_actions_layout.addWidget(self.delete_section_button)
        section_actions_layout.addStretch(1)

        text_label = QLabel("Texto a incorporar na seção")
        text_label.setProperty("role", "section")
        left_layout.addWidget(text_label)

        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText(
            "Cole um trecho aqui. O texto não será guardado; apenas a contagem das palavras "
            "será somada a seção escolhida."
        )
        self.text_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        left_layout.addWidget(self.text_input, stretch=1)

        lexical_note_label = QLabel(
            "A tradução sugerida e o IPA assumem que as palavras do texto estão em ingles. "
            "A tradução para portugues e uma aproximacao automatica por palavra."
        )
        lexical_note_label.setWordWrap(True)
        lexical_note_label.setProperty("role", "muted")
        left_layout.addWidget(lexical_note_label)

        entry_actions_layout = QHBoxLayout()
        entry_actions_layout.setSpacing(10)
        left_layout.addLayout(entry_actions_layout)

        self.add_text_button = QPushButton("Adicionar texto a seção")
        self.add_text_button.setProperty("role", "primary")
        entry_actions_layout.addWidget(self.add_text_button)

        self.clear_text_button = QPushButton("Limpar texto")
        entry_actions_layout.addWidget(self.clear_text_button)

        entry_actions_layout.addStretch(1)

        storage_note_label = QLabel(
            "Persistencia local: o arquivo salvo contem apenas as palavras e suas contagens "
            "por seção. O texto original não fica armazenado."
        )
        storage_note_label.setWordWrap(True)
        storage_note_label.setProperty("role", "muted")
        left_layout.addWidget(storage_note_label)

        self.entry_status_label = QLabel("")
        self.entry_status_label.setWordWrap(True)
        self.entry_status_label.setProperty("role", "status")
        left_layout.addWidget(self.entry_status_label)

        sections_label = QLabel("seções para visualização")
        sections_label.setProperty("role", "section")
        right_layout.addWidget(sections_label)

        sections_help_label = QLabel(
            "Marque uma ou mais seções. Se nenhuma estiver marcada, a visualização usa todas."
        )
        sections_help_label.setWordWrap(True)
        sections_help_label.setProperty("role", "muted")
        right_layout.addWidget(sections_help_label)

        self.section_list = QListWidget()
        self.section_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.section_list.setMinimumHeight(220)
        right_layout.addWidget(self.section_list)

        selection_buttons_layout = QHBoxLayout()
        selection_buttons_layout.setSpacing(10)
        right_layout.addLayout(selection_buttons_layout)

        self.select_all_button = QPushButton("Selecionar todas")
        selection_buttons_layout.addWidget(self.select_all_button)

        self.clear_selection_button = QPushButton("Limpar marcacoes")
        selection_buttons_layout.addWidget(self.clear_selection_button)

        selection_buttons_layout.addStretch(1)

        self.open_histogram_button = QPushButton("Abrir histograma em janela")
        self.open_histogram_button.setProperty("role", "primary")
        right_layout.addWidget(self.open_histogram_button)

        self.selection_summary_label = QLabel("Visualizando: nenhuma seção")
        self.selection_summary_label.setWordWrap(True)
        self.selection_summary_label.setProperty("role", "section")
        right_layout.addWidget(self.selection_summary_label)

        self.lookup_status_label = QLabel(
            "A busca, a ordenação e a exclusão por palavra ficam na janela do histograma."
        )
        self.lookup_status_label.setWordWrap(True)
        self.lookup_status_label.setProperty("role", "muted")
        right_layout.addWidget(self.lookup_status_label)

        self.total_words_label = QLabel("Total de palavras na visualização: 0")
        self.total_words_label.setProperty("role", "section")
        right_layout.addWidget(self.total_words_label)

        self.unique_words_label = QLabel("Palavras unicas na visualização: 0")
        self.unique_words_label.setProperty("role", "section")
        right_layout.addWidget(self.unique_words_label)

        info_label = QLabel(
            "Para excluir uma palavra, abra o histograma detalhado e use o botão Excluir "
            "na mesma linha da palavra desejada."
        )
        info_label.setWordWrap(True)
        info_label.setProperty("role", "muted")
        right_layout.addWidget(info_label)

        right_layout.addStretch(1)

    def _create_panel(self) -> QFrame:
        panel = QFrame()
        panel.setProperty("class", "panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        return panel

    def _bind_events(self) -> None:
        self.create_section_button.clicked.connect(self.create_section)
        self.delete_section_button.clicked.connect(self.delete_current_section)
        self.add_text_button.clicked.connect(self.add_text_to_current_section)
        self.clear_text_button.clicked.connect(self.text_input.clear)
        self.open_histogram_button.clicked.connect(self.open_histogram_window)
        self.section_list.itemChanged.connect(self._handle_section_item_changed)
        self.select_all_button.clicked.connect(
            lambda: self._set_all_section_checks(Qt.CheckState.Checked)
        )
        self.clear_selection_button.clicked.connect(
            lambda: self._set_all_section_checks(Qt.CheckState.Unchecked)
        )

        create_shortcut = QShortcut(QKeySequence("Ctrl+Shift+N"), self)
        create_shortcut.activated.connect(self.create_section)
        self._create_shortcut = create_shortcut

        add_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        add_shortcut.activated.connect(self.add_text_to_current_section)
        self._add_shortcut = add_shortcut

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #f3efe7;
                color: #1f2933;
                font-family: "Segoe UI";
                font-size: 10.5pt;
            }
            QFrame[class="panel"] {
                background: #fffdf8;
                border: 1px solid #e4ddd1;
                border-radius: 16px;
            }
            QLabel[role="title"] {
                color: #2f3e46;
                font-size: 21pt;
                font-weight: 600;
            }
            QLabel[role="section"] {
                color: #36454f;
                font-weight: 600;
            }
            QLabel[role="muted"] {
                color: #5c6770;
            }
            QLabel[role="status"] {
                color: #2b5f58;
                background: #e5f0ee;
                border: 1px solid #c5dbd6;
                border-radius: 10px;
                padding: 10px;
            }
            QTextEdit, QLineEdit, QComboBox, QTableWidget, QListWidget {
                background: #fffdf8;
                border: 1px solid #d7d1c7;
                border-radius: 12px;
                padding: 8px;
                selection-background-color: #9fd7cf;
                selection-color: #183531;
            }
            QTextEdit:focus, QLineEdit:focus, QComboBox:focus, QTableWidget:focus, QListWidget:focus {
                border: 1px solid #2f7f73;
            }
            QPushButton {
                background: #e8e2d7;
                border: 1px solid #d0c8bc;
                border-radius: 12px;
                padding: 9px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #ddd6ca;
            }
            QPushButton[role="primary"] {
                background: #2f7f73;
                color: white;
                border: 1px solid #2f7f73;
            }
            QPushButton[role="primary"]:hover {
                background: #276c61;
            }
            QHeaderView::section {
                background: #dce5df;
                color: #243b3b;
                border: none;
                border-bottom: 1px solid #ccd7cf;
                padding: 8px;
                font-weight: 600;
            }
            QTableWidget {
                gridline-color: #ece6dc;
                alternate-background-color: #faf7f2;
            }
            QListWidget::item {
                padding: 6px 4px;
            }
            """
        )

    def _section_titles(self) -> list[str]:
        return sorted(self.sections, key=str.casefold)

    def _checked_section_titles(self) -> list[str]:
        checked_titles: list[str] = []

        for index in range(self.section_list.count()):
            item = self.section_list.item(index)
            title = item.data(Qt.ItemDataRole.UserRole)

            if item.checkState() == Qt.CheckState.Checked and isinstance(title, str):
                checked_titles.append(title)

        return checked_titles

    def _effective_section_titles(self) -> list[str]:
        titles = self._section_titles()

        if not titles:
            return []

        checked_titles = self._checked_section_titles()
        return checked_titles or titles

    def _sync_section_controls(
        self,
        preferred_target_title: str | None = None,
        checked_titles: Iterable[str] | None = None,
    ) -> None:
        titles = self._section_titles()
        checked_set = set(checked_titles or self._checked_section_titles())

        current_target = preferred_target_title

        if current_target is None:
            current_target = self.target_section_combo.currentText()

        self.target_section_combo.blockSignals(True)
        self.section_list.blockSignals(True)

        self.target_section_combo.clear()
        self.target_section_combo.addItems(titles)

        if titles:
            if current_target not in titles:
                current_target = titles[0]

            combo_index = self.target_section_combo.findText(current_target)

            if combo_index >= 0:
                self.target_section_combo.setCurrentIndex(combo_index)

        self.section_list.clear()

        for title in titles:
            item = QListWidgetItem(title)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(Qt.ItemDataRole.UserRole, title)
            item.setCheckState(
                Qt.CheckState.Checked if title in checked_set else Qt.CheckState.Unchecked
            )

            counter = self.sections[title]
            item.setToolTip(
                f"Total: {sum(counter.values())} palavra(s) | "
                f"Unicas: {len(counter)}"
            )
            self.section_list.addItem(item)

        has_titles = bool(titles)
        self.target_section_combo.setEnabled(has_titles)
        self.add_text_button.setEnabled(has_titles)
        self.delete_section_button.setEnabled(has_titles)
        self.select_all_button.setEnabled(has_titles)
        self.clear_selection_button.setEnabled(has_titles)
        self.open_histogram_button.setEnabled(has_titles)

        self.section_list.blockSignals(False)
        self.target_section_combo.blockSignals(False)

    def _save_sections(self) -> bool:
        try:
            self.repository.save_sections(self.sections)
            return True
        except OSError:
            self.entry_status_label.setText(
                "não foi possivel salvar as contagens no armazenamento local."
            )
            return False


    def create_section(self) -> None:
        title = normalize_section_title(self.section_title_input.text())

        if not title:
            self.entry_status_label.setText("Informe um título de seção antes de criar.")
            return

        section_already_exists = title in self.sections

        if not section_already_exists:
            self.sections[title] = Counter()

            if not self._save_sections():
                self.sections.pop(title, None)
                return

        checked_titles = self._checked_section_titles()
        if title not in checked_titles:
            checked_titles.append(title)

        self._sync_section_controls(
            preferred_target_title=title,
            checked_titles=checked_titles,
        )
        self.section_title_input.clear()
        self.refresh_results()

        if section_already_exists:
            self.entry_status_label.setText(
                f"A seção '{title}' já existia e foi selecionada."
            )
        else:
            self.entry_status_label.setText(
                f"seção '{title}' criada. Agora você já pode adicionar texto nela."
            )

    def add_text_to_current_section(self) -> None:
        section_title = normalize_section_title(self.target_section_combo.currentText())
        text = self.text_input.toPlainText().strip()

        if not section_title:
            self.entry_status_label.setText(
                "Crie pelo menos uma seção antes de adicionar texto."
            )
            return

        if not text:
            self.entry_status_label.setText("Cole algum texto antes de adicionar a seção.")
            return

        section_existed_before = section_title in self.sections
        previous_counter = self.sections.get(section_title, Counter()).copy()

        try:
            updated_counter = add_text_to_section(self.sections, section_title, text)
        except ValueError as error:
            self.entry_status_label.setText(str(error))
            return

        if not self._save_sections():
            if section_existed_before:
                self.sections[section_title] = previous_counter
            else:
                self.sections.pop(section_title, None)
            return

        checked_titles = self._checked_section_titles()
        if section_title not in checked_titles:
            checked_titles.append(section_title)

        self._sync_section_controls(
            preferred_target_title=section_title,
            checked_titles=checked_titles,
        )
        self.text_input.clear()
        self.refresh_results()
        self.entry_status_label.setText(
            f"Texto incorporado na seção '{section_title}'. "
            f"Ela agora possui {sum(updated_counter.values())} palavra(s) acumulada(s)."
        )

    def delete_current_section(self) -> None:
        section_title = normalize_section_title(self.target_section_combo.currentText())

        if not section_title:
            self.entry_status_label.setText("Selecione uma seção para excluir.")
            return

        confirmation = QMessageBox.question(
            self,
            "Excluir seção",
            (
                f"Deseja realmente excluir a seção '{section_title}'?\n\n"
                "As contagens dessa seção serão removidas do banco."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if confirmation != QMessageBox.StandardButton.Yes:
            return

        backup_sections = {
            title: counter.copy() for title, counter in self.sections.items()
        }

        try:
            remove_section(self.sections, section_title)
        except ValueError as error:
            self.entry_status_label.setText(str(error))
            return

        if not self._save_sections():
            self.sections = backup_sections
            return

        checked_titles = [
            title for title in self._checked_section_titles() if title != section_title
        ]
        preferred_target_title = checked_titles[0] if checked_titles else None
        self._sync_section_controls(
            preferred_target_title=preferred_target_title,
            checked_titles=checked_titles,
        )
        self.refresh_results()
        self.entry_status_label.setText(f"seção '{section_title}' excluída com sucesso.")

    def delete_word_from_histogram_scope(self, word: str) -> None:
        normalized_word = word.strip().casefold()
        effective_titles = self._effective_section_titles()

        if not normalized_word or not effective_titles:
            self.entry_status_label.setText(
                "não foi possivel identificar a palavra ou a seção para exclusão."
            )
            return

        target_titles = [
            title
            for title in effective_titles
            if normalized_word in self.sections.get(title, Counter())
        ]

        if not target_titles:
            self.entry_status_label.setText(
                f"A palavra '{normalized_word}' não foi encontrada nas seções visiveis."
            )
            return

        if len(target_titles) == 1:
            question = (
                f"Deseja remover a palavra '{normalized_word}' da seção "
                f"'{target_titles[0]}'?"
            )
        else:
            question = (
                f"Deseja remover a palavra '{normalized_word}' de {len(target_titles)} "
                "seções visiveis?\n\n"
                + "\n".join(f"• {title}" for title in target_titles)
            )

        confirmation = QMessageBox.question(
            self,
            "Excluir palavra",
            question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if confirmation != QMessageBox.StandardButton.Yes:
            return

        backup_sections = {
            title: counter.copy() for title, counter in self.sections.items()
        }
        removed_total = 0

        try:
            for title in target_titles:
                removed_total += remove_word_from_section(
                    self.sections, title, normalized_word
                )
        except ValueError as error:
            self.sections = backup_sections
            self.entry_status_label.setText(str(error))
            return

        if not self._save_sections():
            self.sections = backup_sections
            return

        self._sync_section_controls(
            preferred_target_title=self.target_section_combo.currentText(),
            checked_titles=self._checked_section_titles(),
        )
        self.refresh_results()
        self.entry_status_label.setText(
            f"Palavra '{normalized_word}' removida das seções visiveis "
            f"(ocorrencias excluídas: {removed_total})."
        )

    def open_histogram_window(self) -> None:
        if not self.current_combined_counter:
            self.entry_status_label.setText(
                "não há dados disponiveis para abrir no histograma detalhado."
            )
            return

        if self.histogram_window is None:
            self.histogram_window = HistogramWindow(self)

        self.histogram_window.populate(
            self.current_combined_counter,
            self.selection_summary_label.text(),
            self.delete_word_from_histogram_scope,
        )
        self.histogram_window.show()
        self.histogram_window.raise_()
        self.histogram_window.activateWindow()

    def _handle_section_item_changed(self, _item: QListWidgetItem) -> None:
        self.refresh_results()

    def _set_all_section_checks(self, check_state: Qt.CheckState) -> None:
        self.section_list.blockSignals(True)

        for index in range(self.section_list.count()):
            item = self.section_list.item(index)
            item.setCheckState(check_state)

        self.section_list.blockSignals(False)
        self.refresh_results()



    def refresh_results(self) -> None:
        effective_titles = self._effective_section_titles()

        if not effective_titles:
            self.filtered_items = []
            self.current_row_by_word = {}
            self.current_combined_counter = Counter()
            self.selection_summary_label.setText("Visualizando: nenhuma seção")
            self.total_words_label.setText("Total de palavras na visualização: 0")
            self.unique_words_label.setText("Palavras unicas na visualização: 0")
            if self.histogram_window is not None:
                self.histogram_window.populate(
                    Counter(),
                    "Visualizando: nenhuma seção",
                    self.delete_word_from_histogram_scope,
                )
            return

        checked_titles = self._checked_section_titles()
        aggregate_all_sections = not checked_titles
        combined_counter = combine_section_counters(self.sections, effective_titles)
        self.current_combined_counter = combined_counter
        self.filtered_items = list(combined_counter.items())

        if aggregate_all_sections:
            selection_text = "Visualizando: todas as seções"
        elif len(effective_titles) == 1:
            selection_text = f"Visualizando: {effective_titles[0]}"
        else:
            selection_text = (
                f"Visualizando {len(effective_titles)} seções combinadas: "
                + ", ".join(effective_titles)
            )

        self.selection_summary_label.setText(selection_text)
        self.total_words_label.setText(
            f"Total de palavras na visualização: {sum(combined_counter.values())}"
        )
        self.unique_words_label.setText(
            f"Palavras unicas na visualização: {len(combined_counter)}"
        )

        if self.histogram_window is not None and self.histogram_window.isVisible():
            self.histogram_window.populate(
                combined_counter,
                self.selection_summary_label.text(),
                self.delete_word_from_histogram_scope,
                self.histogram_window.search_input.text(),
                self.histogram_window.sort_combo.currentText(),
            )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.histogram_window is not None:
            self.histogram_window.close()
        super().closeEvent(event)


def main() -> int:
    application = QApplication(sys.argv)
    window = WordCounterApp()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
