# Tests for docstring_guard: detection, conversion and the command line behaviour.

import ast
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docstring_guard import convert_source, find_docstrings, main

SAMPLE = '''"""Module level note."""

import os


class Widget:
    """A widget."""

    def paint(self):
        """Paint it."""
        return os.name


def helper():
    # A real comment, not a docstring.
    text = "not a docstring either"
    return text
'''


def test_finds_module_class_and_function_docstrings():
    records = find_docstrings(SAMPLE, "sample.py")
    names = [item["qualname"] for item in records]
    assert names == ["module", "Widget", "Widget.paint()"]


def test_ignores_plain_string_literals():
    records = find_docstrings(SAMPLE, "sample.py")
    assert len(records) == 3


def test_reports_line_numbers_of_the_string_not_the_definition():
    records = find_docstrings(SAMPLE, "sample.py")
    by_name = {item["qualname"]: item for item in records}
    assert by_name["Widget.paint()"]["lineno"] == SAMPLE.splitlines().index('        """Paint it."""') + 1


def test_conversion_produces_parseable_source_without_docstrings():
    records = find_docstrings(SAMPLE, "sample.py")
    fixed, skipped = convert_source(SAMPLE, records)
    assert skipped == []
    assert find_docstrings(fixed, "sample.py") == []
    ast.parse(fixed)
    assert "# Module level note." in fixed
    assert "# Paint it." in fixed


def test_conversion_keeps_body_valid_when_docstring_was_the_only_statement():
    source = 'def lonely():\n    """Only a note."""\n'
    fixed, _ = convert_source(source, find_docstrings(source, "lonely.py"))
    ast.parse(fixed)
    assert "pass" in fixed
    assert find_docstrings(fixed, "lonely.py") == []


def test_multi_line_docstring_becomes_several_comments():
    source = 'def work():\n    """First line.\n\n    Second line.\n    """\n    return 1\n'
    fixed, _ = convert_source(source, find_docstrings(source, "work.py"))
    ast.parse(fixed)
    assert "    # First line." in fixed
    assert "    # Second line." in fixed


def test_inline_docstring_is_reported_but_left_alone():
    source = 'def quick(): """Inline note."""\n'
    records = find_docstrings(source, "quick.py")
    assert records[0]["inline"] is True
    fixed, skipped = convert_source(source, records)
    assert fixed == source
    assert len(skipped) == 1


def test_cli_check_mode_exits_one_and_fix_mode_cleans_the_file(tmp_path):
    target = tmp_path / "module.py"
    target.write_text(SAMPLE, encoding="utf-8")
    assert main([str(target), "--quiet"]) == 1
    assert main([str(target), "--fix", "--quiet"]) == 0
    assert find_docstrings(target.read_text(encoding="utf-8"), str(target)) == []


def test_cli_clean_tree_exits_zero(tmp_path):
    target = tmp_path / "clean.py"
    target.write_text("# Only comments here.\nvalue = 1\n", encoding="utf-8")
    assert main([str(target), "--quiet"]) == 0


def test_cli_reports_syntax_error_with_exit_two(tmp_path):
    target = tmp_path / "broken.py"
    target.write_text("def broken(:\n", encoding="utf-8")
    assert main([str(target), "--quiet"]) == 2


def test_module_entry_point_runs():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(root, "docstring_guard.py")
    result = subprocess.run(
        [sys.executable, script, script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "no docstrings found" in result.stdout
