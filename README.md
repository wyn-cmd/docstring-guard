# docstring-guard

A small linter that finds Python docstrings and, with `--fix`, rewrites them as `#` comments at the same indentation. It parses files with `ast`, so only real docstrings are flagged: a bare string literal sitting in the first statement slot of a module, class, sync function or async function. Ordinary string literals, f-strings and comments are left untouched.

Built for codebases that keep comments above the code instead of docstrings below the signature, and for CI pipelines that want to enforce that rule. The project has no runtime dependencies beyond the Python standard library.

## Usage

```bash
python3 docstring_guard.py path/to/file.py
python3 docstring_guard.py src/ tests/ --quiet
python3 docstring_guard.py src/ --fix
```

Each finding prints as `path:line: qualname`, where the line number points at the opening quote of the string and not at the `def` or `class` line. Passing a directory walks it recursively and skips `.git`, `__pycache__`, virtual environments, `node_modules`, build output and the usual tool caches.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | No docstrings found, or every docstring was converted with `--fix` |
| 1 | Docstrings found and `--fix` is off |
| 2 | A file could not be read or does not parse |

The nonzero check mode is the point: drop `python3 docstring_guard.py .` into a pre-commit hook or a CI step and the build fails on the first docstring that slips in.

## What `--fix` does

- Replaces the whole string span, from the opening quote to the closing quote, with `#` comment lines using the same leading whitespace, so nested methods stay aligned.
- Splits multi-line docstrings on their newlines, prefixes every non-blank line with `# ` and turns blank lines into a bare `#`.
- Appends `pass` when the docstring was the only statement in the body, because a body made only of comments is a syntax error.
- Refuses to write a file whose converted version no longer parses, and reports the file instead.
- Leaves inline docstrings alone, such as `def quick(): "note"`, because the code before the string has to be preserved and guessing where it ends is not worth the risk. Those are reported on stderr with a hint to move the string onto its own line. `--allow-inline` suppresses them entirely.

Converting a docstring drops the original escape sequences and quote style, since the replacement text is the parsed string value. That is deliberate: the output is meant to read as prose comments, not to round-trip back into a literal.

## Tests

```bash
python3 -m pytest tests/ -q
```

The suite covers detection of module, class, method and nested function docstrings, ignoring plain literals, line numbers, multi-line conversion, the `pass` fallback, inline handling, all three exit codes and the `python3 docstring_guard.py docstring_guard.py` self check.

## Limits

Only docstrings in the sense of PEP 257 are detected. Attribute docstrings that follow an assignment or an annotated assignment are not, because the `ast` module does not mark them as anything special without extra heuristics.

## License

MIT.
