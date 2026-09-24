import json

from whisperfree.dictionary import Dictionary, Replacement


def make(tmp_path):
    return Dictionary(tmp_path / "dictionary.json")


def test_add_term_trims_and_dedupes_case_insensitively(tmp_path):
    d = make(tmp_path)
    assert d.add_term("  Kanishka ")
    assert not d.add_term("kanishka")
    assert not d.add_term("   ")
    assert d.terms() == ["Kanishka"]


def test_remove_term_is_case_insensitive(tmp_path):
    d = make(tmp_path)
    d.add_term("PyQt6")
    assert d.remove_term("pyqt6")
    assert not d.remove_term("pyqt6")
    assert d.terms() == []


def test_changes_persist_to_disk(tmp_path):
    d = make(tmp_path)
    d.add_term("5Point")
    d.add_replacement("five point", "5Point")
    reloaded = make(tmp_path)
    assert reloaded.terms() == ["5Point"]
    assert reloaded.replacements() == [Replacement("five point", "5Point")]
    raw = json.loads((tmp_path / "dictionary.json").read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_build_prompt_empty_without_terms(tmp_path):
    assert make(tmp_path).build_prompt() == ""


def test_build_prompt_lists_terms(tmp_path):
    d = make(tmp_path)
    for term in ("Kanishka", "5Point", "PyQt6"):
        d.add_term(term)
    assert d.build_prompt() == "Glossary: Kanishka, 5Point, PyQt6."


def test_build_prompt_keeps_most_recent_terms_within_limit(tmp_path):
    d = make(tmp_path)
    for i in range(200):
        d.add_term(f"term{i:03d}")
    prompt = d.build_prompt()
    assert len(prompt) <= 800
    assert prompt.startswith("Glossary: ")
    assert prompt.endswith("term199.")
    assert "term000" not in prompt


def test_replacement_is_whole_word_and_case_insensitive(tmp_path):
    d = make(tmp_path)
    d.add_replacement("gpt four", "GPT-4")
    d.add_replacement("cat", "dog")
    assert d.apply_replacements("I asked GPT Four about my category.") == "I asked GPT-4 about my category."
    assert d.apply_replacements("Cat.") == "dog."


def test_longest_match_wins(tmp_path):
    d = make(tmp_path)
    d.add_replacement("new", "NEW")
    d.add_replacement("new york", "NYC")
    assert d.apply_replacements("I love New York and new things") == "I love NYC and NEW things"


def test_replacements_do_not_chain(tmp_path):
    d = make(tmp_path)
    d.add_replacement("a", "b")
    d.add_replacement("b", "c")
    assert d.apply_replacements("a b") == "b c"


def test_special_character_rules(tmp_path):
    d = make(tmp_path)
    d.add_replacement("c++", "C++")
    d.add_replacement("@me", "kragula@example.com")
    assert d.apply_replacements("I write c++ daily, ping @me") == "I write C++ daily, ping kragula@example.com"


def test_unicode_terms_match(tmp_path):
    d = make(tmp_path)
    d.add_replacement("josé", "José")
    assert d.apply_replacements("JOSÉ said hi") == "José said hi"


def test_blank_replacement_removes_phrase_and_collapses_spaces(tmp_path):
    d = make(tmp_path)
    d.add_replacement("um", "")
    assert d.apply_replacements("So um I think  um yes") == "So I think yes"
    assert d.apply_replacements("um") == ""


def test_text_without_matches_is_unchanged(tmp_path):
    d = make(tmp_path)
    d.add_replacement("foo", "bar")
    assert d.apply_replacements("  keep   spacing  ") == "  keep   spacing  "


def test_add_replacement_rejects_blank_and_duplicate_match(tmp_path):
    d = make(tmp_path)
    assert not d.add_replacement("  ", "x")
    assert d.add_replacement("Five Point", "5Point")
    assert not d.add_replacement("five point", "other")
    assert d.replacements() == [Replacement("Five Point", "5Point")]


def test_update_and_remove_replacement(tmp_path):
    d = make(tmp_path)
    d.add_replacement("a", "1")
    d.add_replacement("b", "2")
    assert not d.update_replacement(0, "B", "x")  # collides with rule 1
    assert d.update_replacement(0, "alpha", "A")
    assert not d.update_replacement(5, "z", "z")
    assert d.apply_replacements("alpha b") == "A 2"
    assert d.remove_replacement(0)
    assert not d.remove_replacement(3)
    assert d.replacements() == [Replacement("b", "2")]
    assert d.apply_replacements("alpha b") == "alpha 2"


def test_corrupt_file_is_moved_to_bak(tmp_path):
    path = tmp_path / "dictionary.json"
    path.write_text("{not json", encoding="utf-8")
    d = Dictionary(path)
    assert d.terms() == []
    assert (tmp_path / "dictionary.json.bak").read_text(encoding="utf-8") == "{not json"
    assert not path.exists()


def test_partially_invalid_file_keeps_valid_entries(tmp_path):
    path = tmp_path / "dictionary.json"
    path.write_text(
        json.dumps(
            {
                "terms": ["Good", 42, None, "good", "Also"],
                "replacements": [
                    {"match": "ok", "replace": "OK"},
                    {"replace": "missing match"},
                    {"match": 5, "replace": "x"},
                    {"match": "bad", "replace": 7},
                    "not a dict",
                    {"match": "no replace key"},
                ],
            }
        ),
        encoding="utf-8",
    )
    d = Dictionary(path)
    assert d.terms() == ["Good", "Also"]
    assert d.replacements() == [Replacement("ok", "OK"), Replacement("no replace key", "")]


def test_non_list_sections_are_ignored(tmp_path):
    path = tmp_path / "dictionary.json"
    path.write_text(json.dumps({"terms": "abc", "replacements": {"a": "b"}}), encoding="utf-8")
    d = Dictionary(path)
    assert d.terms() == []
    assert d.replacements() == []


def test_save_failure_is_reported_not_raised(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    d = Dictionary(blocker / "dictionary.json")
    assert d.add_term("Kanishka")
    assert d.terms() == ["Kanishka"]
    assert d.last_save_error
