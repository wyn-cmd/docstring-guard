#!/usr/bin/env python3
# Find Python docstrings and optionally rewrite them as # comments.
# Uses the ast module so only real docstrings are flagged, never ordinary string literals.

import argparse
import ast
import inspect
import os
import sys

# Directories that are never worth scanning by default.
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "build",
    "dist",
}


def iter_python_files(root):
    # Yield .py files from a single file or by walking a directory.
    if os.path.isfile(root):
        if root.endswith(".py"):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def find_docstrings(source, path="<source>"):
    # Return one record per module, class or function docstring found in the source text.
    tree = ast.parse(source, filename=path)
    source_lines = source.splitlines()
    found = []

    def check_body(body, qualname):
        # A docstring is only a bare string literal occupying the first statement slot.
        if not body:
            return
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            start_line = first.lineno - 1
            line_text = source_lines[start_line] if start_line < len(source_lines) else ""
            indent = line_text[: len(line_text) - len(line_text.lstrip())]
            found.append(
                {
                    "path": path,
                    "lineno": first.lineno,
                    "end_lineno": first.end_lineno,
                    "col_offset": first.col_offset,
                    "indent": indent,
                    "inline": first.col_offset > len(indent),
                    "body_len": len(body),
                    "qualname": qualname,
                    "text": first.value.value,
                }
            )

    def walk(node, prefix):
        # Recurse through the tree while building dotted names for nested scopes.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            check_body(node.body, prefix + node.name + "()")
            for child in node.body:
                walk(child, prefix + node.name + ".")
        elif isinstance(node, ast.ClassDef):
            check_body(node.body, prefix + node.name)
            for child in node.body:
                walk(child, prefix + node.name + ".")
        else:
            for child in ast.iter_child_nodes(node):
                walk(child, prefix)

    check_body(tree.body, "module")
    for child in tree.body:
        walk(child, "")
    return found


def convert_source(source, records):
    # Rewrite every block docstring as a run of # comments at the same indentation.
    # Records are applied bottom up so earlier line numbers stay valid.
    lines = source.splitlines(keepends=True)
    skipped = []
    for item in sorted(records, key=lambda d: d["lineno"], reverse=True):
        # Inline docstrings share a line with other code, so rewriting them needs guesswork.
        if item["inline"]:
            skipped.append(item)
            continue
        start = item["lineno"] - 1
        end = item["end_lineno"] - 1
        indent = item["indent"]
        new_lines = []
        # cleandoc strips the indentation the literal picked up from the function body.
        for text_line in inspect.cleandoc(item["text"]).splitlines():
            stripped = text_line.rstrip()
            if stripped:
                new_lines.append(indent + "# " + stripped + "\n")
            else:
                new_lines.append(indent + "#\n")
        # A body that held only the docstring still needs a statement after the comments.
        if item["body_len"] == 1:
            new_lines.append(indent + "pass\n")
        lines[start : end + 1] = new_lines
    return "".join(lines), skipped


def scan(paths):
    # Walk every requested path and return records plus a list of unreadable files.
    records = []
    errors = []
    for root in paths:
        for file_path in iter_python_files(root):
            try:
                with open(file_path, "r", encoding="utf-8") as handle:
                    source = handle.read()
            except OSError as exc:
                errors.append((file_path, str(exc)))
                continue
            try:
                records.extend(find_docstrings(source, file_path))
            except SyntaxError as exc:
                errors.append((file_path, "syntax error: " + str(exc)))
    return records, errors


def fix_file(path, records, quiet):
    # Rewrite one file in place, refusing to write output that no longer parses.
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()
    fixed, skipped = convert_source(source, records)
    try:
        remaining = find_docstrings(fixed, path)
    except SyntaxError as exc:
        print(f"{path}: refusing to write, rewrite broke the syntax: {exc}", file=sys.stderr)
        return None, skipped
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(fixed)
    if not quiet:
        for item in records:
            print(f"converted {path}:{item['lineno']}: {item['qualname']}")
    return len(remaining), skipped


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="docstring-guard",
        description="Report Python docstrings and optionally convert them into # comments.",
    )
    parser.add_argument("paths", nargs="+", help="file or directory paths to scan")
    parser.add_argument("--fix", action="store_true", help="rewrite docstrings as # comments in place")
    parser.add_argument("--quiet", action="store_true", help="print only the final summary")
    parser.add_argument(
        "--allow-inline",
        action="store_true",
        help="do not report docstrings that start on a line with other code",
    )
    args = parser.parse_args(argv)

    records, errors = scan(args.paths)
    for file_path, message in errors:
        print(f"{file_path}: {message}", file=sys.stderr)

    if args.allow_inline:
        records = [item for item in records if not item["inline"]]

    if args.fix and records:
        skipped_all = []
        by_file = {}
        failures = 0
        for item in records:
            by_file.setdefault(item["path"], []).append(item)
        for file_path, file_records in sorted(by_file.items()):
            remaining, skipped = fix_file(file_path, file_records, args.quiet)
            if remaining is None:
                failures += 1
            skipped_all.extend(skipped)
        for item in skipped_all:
            print(
                f"{item['path']}:{item['lineno']}: inline docstring left alone, move it onto its own line",
                file=sys.stderr,
            )
        if not args.quiet:
            print(f"converted {len(records) - len(skipped_all)} docstring(s) in {len(by_file)} file(s)")
        return 2 if failures else 0

    if not args.quiet:
        for item in records:
            print(f"{item['path']}:{item['lineno']}: {item['qualname']}")

    if records:
        if not args.quiet:
            print(f"{len(records)} docstring(s) found", file=sys.stderr)
        return 1

    if errors:
        return 2

    if not args.quiet:
        print("no docstrings found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
