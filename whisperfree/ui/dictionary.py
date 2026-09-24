"""Dictionary page: custom terms and replacement rules."""

from __future__ import annotations

from typing import List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from whisperfree.dictionary import Dictionary, Replacement
from whisperfree.ui.widgets import Card, FlowLayout, clear_layout, divider, make_label, scroll_page


def _pointer(button: QtWidgets.QPushButton) -> QtWidgets.QPushButton:
    button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
    return button


def _button(text: str, object_name: str) -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text)
    button.setObjectName(object_name)
    return _pointer(button)


class DictionaryPage(QtWidgets.QWidget):
    """Edit the shared Dictionary; every change is saved immediately."""

    def __init__(self, dictionary: Dictionary, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._dictionary = dictionary
        self._editing_index: Optional[int] = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 24)
        layout.setSpacing(12)
        header = QtWidgets.QVBoxLayout()
        header.setSpacing(4)
        header.addWidget(make_label("Dictionary", "PageTitle"))
        header.addWidget(
            make_label("Teach WhisperFree the words you use, and fix the ones it gets wrong.", "PageSubtitle")
        )
        layout.addLayout(header)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_terms_tab(), "Terms")
        self.tabs.addTab(self._build_replacements_tab(), "Replacements")
        layout.addWidget(self.tabs, 1)

        self.status_label = make_label("", "StatusError", wrap=True)
        self.status_label.hide()
        layout.addWidget(self.status_label)

        self._render_terms()
        self._render_rules()

    # ------------------------------------------------------------------ terms tab

    def _build_terms_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(
            make_label(
                "Names, acronyms, and jargon. WhisperFree passes these to the transcriber as spelling hints.",
                "Caption",
                wrap=True,
            )
        )

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        self.term_input = QtWidgets.QLineEdit()
        self.term_input.setPlaceholderText("Add a word or phrase, e.g. Kanishka")
        self.term_input.returnPressed.connect(self._handle_add_term)
        self.add_term_button = _button("Add", "PrimaryButton")
        self.add_term_button.clicked.connect(self._handle_add_term)
        row.addWidget(self.term_input, 1)
        row.addWidget(self.add_term_button)
        layout.addLayout(row)

        card = Card()
        self._chips_container = QtWidgets.QWidget()
        self._chips_layout = FlowLayout(self._chips_container, spacing=8)
        card.body.addWidget(self._chips_container)
        self._terms_empty = make_label("No terms yet. Add the names and jargon you say often.", "Muted", wrap=True)
        card.body.addWidget(self._terms_empty)

        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(card)
        content_layout.addStretch(1)
        layout.addWidget(scroll_page(content), 1)
        return page

    def _render_terms(self) -> None:
        clear_layout(self._chips_layout)
        terms = self._dictionary.terms()
        for term in terms:
            self._chips_layout.addWidget(self._make_chip(term))
        self._chips_container.setVisible(bool(terms))
        self._terms_empty.setVisible(not terms)

    def _make_chip(self, term: str) -> QtWidgets.QFrame:
        chip = QtWidgets.QFrame()
        chip.setObjectName("Chip")
        chip.setProperty("term", term)
        layout = QtWidgets.QHBoxLayout(chip)
        layout.setContentsMargins(12, 4, 6, 4)
        layout.setSpacing(4)
        layout.addWidget(make_label(term, "ChipText"))
        remove = _button("×", "ChipRemove")
        remove.setFixedSize(18, 18)
        remove.setToolTip(f"Remove {term}")
        remove.clicked.connect(lambda _checked=False, t=term: self._remove_term(t))
        layout.addWidget(remove)
        chip.remove_button = remove  # type: ignore[attr-defined]
        return chip

    def term_chips(self) -> List[QtWidgets.QFrame]:
        return [self._chips_layout.itemAt(i).widget() for i in range(self._chips_layout.count())]

    def _handle_add_term(self) -> None:
        text = self.term_input.text().strip()
        if not text:
            return
        if not self._dictionary.add_term(text):
            self._show_status(f"“{text}” is already in your dictionary.")
            return
        self.term_input.clear()
        self._render_terms()
        self._show_save_status()

    def _remove_term(self, term: str) -> None:
        self._dictionary.remove_term(term)
        self._render_terms()
        self._show_save_status()

    # ------------------------------------------------------------------ replacements tab

    def _build_replacements_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(
            make_label(
                "Swap what Whisper hears for what you want pasted. Matches whole words and ignores case.",
                "Caption",
                wrap=True,
            )
        )

        form = QtWidgets.QHBoxLayout()
        form.setSpacing(8)
        self.match_input = QtWidgets.QLineEdit()
        self.match_input.setPlaceholderText("When I say…")
        self.replace_input = QtWidgets.QLineEdit()
        self.replace_input.setPlaceholderText("Replace with… (leave empty to remove)")
        for field in (self.match_input, self.replace_input):
            field.returnPressed.connect(self._handle_save_rule)
        self.save_rule_button = _button("Add", "PrimaryButton")
        self.save_rule_button.clicked.connect(self._handle_save_rule)
        self.cancel_edit_button = _button("Cancel", "SecondaryButton")
        self.cancel_edit_button.clicked.connect(self._exit_edit_mode)
        self.cancel_edit_button.hide()
        form.addWidget(self.match_input, 1)
        form.addWidget(make_label("→", "Caption"))
        form.addWidget(self.replace_input, 1)
        form.addWidget(self.save_rule_button)
        form.addWidget(self.cancel_edit_button)
        layout.addLayout(form)

        card = Card(margins=(4, 4, 4, 4), spacing=0)
        self._rules_layout = QtWidgets.QVBoxLayout()
        self._rules_layout.setSpacing(0)
        card.body.addLayout(self._rules_layout)
        self._rules_empty = make_label("No replacement rules yet.", "Muted")
        self._rules_empty.setContentsMargins(16, 12, 16, 12)
        card.body.addWidget(self._rules_empty)

        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(card)
        content_layout.addStretch(1)
        layout.addWidget(scroll_page(content), 1)
        return page

    def _render_rules(self) -> None:
        clear_layout(self._rules_layout)
        rules = self._dictionary.replacements()
        for index, rule in enumerate(rules):
            if index:
                self._rules_layout.addWidget(divider())
            self._rules_layout.addWidget(self._make_rule_row(index, rule))
        self._rules_empty.setVisible(not rules)

    def _make_rule_row(self, index: int, rule: Replacement) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        row.setObjectName("RuleRow")
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.setSpacing(10)
        layout.addWidget(make_label(rule.match, "RuleMatch"))
        layout.addWidget(make_label("→", "Muted"))
        if rule.replace:
            layout.addWidget(make_label(rule.replace, "Body"), 1)
        else:
            layout.addWidget(make_label("(removed)", "Muted"), 1)
        edit = _button("Edit", "GhostButton")
        edit.clicked.connect(lambda _checked=False, i=index: self._start_edit(i))
        delete = _button("Delete", "DangerGhostButton")
        delete.clicked.connect(lambda _checked=False, i=index: self._delete_rule(i))
        layout.addWidget(edit)
        layout.addWidget(delete)
        row.edit_button = edit  # type: ignore[attr-defined]
        row.delete_button = delete  # type: ignore[attr-defined]
        return row

    def rule_rows(self) -> List[QtWidgets.QWidget]:
        rows = []
        for i in range(self._rules_layout.count()):
            widget = self._rules_layout.itemAt(i).widget()
            if widget is not None and widget.objectName() == "RuleRow":
                rows.append(widget)
        return rows

    def _handle_save_rule(self) -> None:
        match = self.match_input.text().strip()
        replace = self.replace_input.text()
        if not match:
            self._show_status("Enter the words to listen for.")
            return
        if self._editing_index is None:
            saved = self._dictionary.add_replacement(match, replace)
        else:
            saved = self._dictionary.update_replacement(self._editing_index, match, replace)
        if not saved:
            self._show_status(f"There's already a rule for “{match}”.")
            return
        self._exit_edit_mode()
        self._render_rules()
        self._show_save_status()

    def _start_edit(self, index: int) -> None:
        rules = self._dictionary.replacements()
        if not 0 <= index < len(rules):
            return
        self._editing_index = index
        self.match_input.setText(rules[index].match)
        self.replace_input.setText(rules[index].replace)
        self.save_rule_button.setText("Save")
        self.cancel_edit_button.show()
        self.match_input.setFocus()

    def _exit_edit_mode(self) -> None:
        self._editing_index = None
        self.match_input.clear()
        self.replace_input.clear()
        self.save_rule_button.setText("Add")
        self.cancel_edit_button.hide()
        self.status_label.hide()

    def _delete_rule(self, index: int) -> None:
        self._exit_edit_mode()
        self._dictionary.remove_replacement(index)
        self._render_rules()
        self._show_save_status()

    # ------------------------------------------------------------------ status

    def _show_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.show()

    def _show_save_status(self) -> None:
        error = self._dictionary.last_save_error
        if error:
            self._show_status(f"Couldn't save the dictionary: {error}")
        else:
            self.status_label.hide()
