"""Validate repository project Skills without third-party dependencies."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".agents" / "skills"
REQUIRED = {
    "project-context-maintainer", "cross-line-contract-manager", "task-gate-reviewer",
    "rag-baseline-guardian", "rag-regression-evaluator", "contract-first-client",
    "browser-adapter-builder", "knowledge-lifecycle-governor", "privacy-and-audit-governor",
}
FIELD = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.+?)\s*$")

def metadata(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening YAML frontmatter delimiter")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration as exc:
        raise ValueError("missing closing YAML frontmatter delimiter") from exc
    result: dict[str, str] = {}
    for line in lines[1:end]:
        match = FIELD.fullmatch(line)
        if not match:
            raise ValueError(f"invalid frontmatter line: {line!r}")
        key, value = match.groups()
        if key in result:
            raise ValueError(f"duplicate frontmatter field: {key}")
        result[key] = value.strip("'\"")
    if set(result) != {"name", "description"}:
        raise ValueError("frontmatter must contain only name and description")
    if not result["name"] or not result["description"]:
        raise ValueError("name and description must be non-empty")
    if not any(line.strip() for line in lines[end + 1:]):
        raise ValueError("skill body is empty")
    return result

def main() -> int:
    errors: list[str] = []
    seen: dict[str, Path] = {}
    paths = sorted(SKILLS.glob("*/SKILL.md"))
    present = {path.parent.name for path in paths}
    for missing in sorted(REQUIRED - present):
        errors.append(f"missing required Skill: {missing}")
    for path in paths:
        try:
            data = metadata(path.read_text(encoding="utf-8"))
            name = data["name"]
            if name != path.parent.name:
                errors.append(f"{path}: name {name!r} does not match directory")
            if name in seen:
                errors.append(f"duplicate Skill name {name!r}: {seen[name]} and {path}")
            else:
                seen[name] = path
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: validated {len(paths)} Skills; all {len(REQUIRED)} required Skills are present")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
