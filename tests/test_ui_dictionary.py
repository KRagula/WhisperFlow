from whisperfree.dictionary import Dictionary, Replacement
from whisperfree.ui.dictionary import DictionaryPage


def make_page(tmp_path):
    dictionary = Dictionary(tmp_path / "dictionary.json")
    return dictionary, DictionaryPage(dictionary)


def test_add_term_via_input(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    page.term_input.setText("Kanishka")
    page.add_term_button.click()
    assert dictionary.terms() == ["Kanishka"]
    assert page.term_input.text() == ""
    assert [chip.property("term") for chip in page.term_chips()] == ["Kanishka"]


def test_enter_key_adds_term(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    page.term_input.setText("PyQt6")
    page.term_input.returnPressed.emit()
    assert dictionary.terms() == ["PyQt6"]


def test_duplicate_term_shows_status(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    dictionary.add_term("5Point")
    page.term_input.setText("5point")
    page.add_term_button.click()
    assert not page.status_label.isHidden()
    assert "already" in page.status_label.text()
    assert page.term_input.text() == "5point"  # kept so the user can fix it


def test_remove_term_chip(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    dictionary.add_term("A")
    dictionary.add_term("B")
    page = DictionaryPage(dictionary)
    page.term_chips()[0].remove_button.click()
    assert dictionary.terms() == ["B"]
    assert len(page.term_chips()) == 1


def test_add_edit_delete_rule(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    page.match_input.setText("five point")
    page.replace_input.setText("5Point")
    page.save_rule_button.click()
    assert dictionary.replacements() == [Replacement("five point", "5Point")]
    assert len(page.rule_rows()) == 1

    page.rule_rows()[0].edit_button.click()
    assert page.match_input.text() == "five point"
    assert page.save_rule_button.text() == "Save"
    assert not page.cancel_edit_button.isHidden()
    page.replace_input.setText("5 Point")
    page.save_rule_button.click()
    assert dictionary.replacements() == [Replacement("five point", "5 Point")]
    assert page.save_rule_button.text() == "Add"
    assert page.match_input.text() == ""

    page.rule_rows()[0].delete_button.click()
    assert dictionary.replacements() == []
    assert page.rule_rows() == []


def test_cancel_edit_restores_add_mode(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    dictionary.add_replacement("a", "b")
    page = DictionaryPage(dictionary)
    page.rule_rows()[0].edit_button.click()
    page.cancel_edit_button.click()
    assert page.save_rule_button.text() == "Add"
    assert page.match_input.text() == ""
    assert page.cancel_edit_button.isHidden()


def test_rule_validation_messages(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    page.save_rule_button.click()
    assert "Enter the words" in page.status_label.text()
    dictionary.add_replacement("um", "")
    page.match_input.setText("UM")
    page.save_rule_button.click()
    assert "already a rule" in page.status_label.text()


def test_blank_replacement_allowed(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    page.match_input.setText("um")
    page.save_rule_button.click()
    assert dictionary.replacements() == [Replacement("um", "")]
