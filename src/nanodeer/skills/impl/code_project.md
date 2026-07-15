---
name: code_project
description: Inspect, change, and verify a multi-file software project.
disable-model-invocation: true
compatibility: read_file write_file edit_file ls glob grep bash
---

# Coding workflow

1. Use `ls`, `glob`, and `grep` to locate the real entry points, tests, and local conventions.
2. Read the relevant files completely enough to understand ownership and data flow.
3. Make the smallest coherent edit with `write_file` or `edit_file`; preserve unrelated work.
4. Use `bash` for formatting, compilation, tests, and Git inspection when available.
5. Report the changed files, verification performed, and any remaining risk.

Work under `/workspace`. Put user-facing build artifacts under `/outputs`. Never invent a
parallel framework when the existing project already has an extension point.
