from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: validate_channel_agent_composition.py REPO COMPOSITION")
    repo = Path(sys.argv[1]).resolve()
    composition_path = Path(sys.argv[2]).resolve()
    composition = json.loads(composition_path.read_text(encoding="utf-8-sig"))
    allowed = tuple(str(item) for item in composition["source_allowlist"])
    allowed_modules = {
        path.removeprefix("src/").removesuffix(".py").replace("/", ".")
        for path in allowed
    }
    forbidden = set(composition["forbidden_import_roots"])
    errors: list[str] = []
    for relative in allowed:
        source = repo / relative
        if not source.is_file():
            errors.append(f"missing allowlisted source: {relative}")
            continue
        tree = ast.parse(source.read_text(encoding="utf-8-sig"), filename=relative)
        package = relative.removeprefix("src/").split("/", 1)[0]
        module_parts = relative.removeprefix("src/").removesuffix(".py").split("/")
        package_parts = (
            module_parts[:-1]
            if module_parts[-1] != "__init__"
            else module_parts[:-1]
        )
        for node in ast.walk(tree):
            root: str | None = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in forbidden:
                        errors.append(f"forbidden import {alias.name} in {relative}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    root = node.module.split(".", 1)[0]
                    if root in forbidden:
                        errors.append(f"forbidden import {node.module} in {relative}:{node.lineno}")
                elif node.level > 0:
                    base = package_parts[: max(0, len(package_parts) - node.level + 1)]
                    target = ".".join(base + ((node.module or "").split(".") if node.module else []))
                    candidates = {target, target + ".__init__"}
                    if not any(item in allowed_modules for item in candidates):
                        errors.append(f"relative import target {target} is not allowlisted in {relative}:{node.lineno}")
        if package != "channel_agent":
            errors.append(f"non-Agent source in production allowlist: {relative}")
    if len(allowed) != len(set(allowed)):
        errors.append("production source allowlist contains duplicates")
    fixtures = tuple(str(item) for item in composition.get("offline_fixture_allowlist", ()))
    for relative in fixtures:
        source = repo / relative
        if not source.is_file():
            errors.append(f"missing allowlisted offline fixture: {relative}")
            continue
        if not relative.startswith("simulators/") or not relative.endswith(".json"):
            errors.append(f"unsafe offline fixture path: {relative}")
            continue
        try:
            fixture = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"invalid offline fixture {relative}: {type(exc).__name__}")
            continue
        if (
            fixture.get("schema_version") != "pdd-readonly-page-fixture.v1"
            or fixture.get("source") != "SYNTHETIC_SANITIZED"
            or fixture.get("sanitized") is not True
            or fixture.get("pdd_network_requests") != 0
        ):
            errors.append(f"offline fixture safety contract failed: {relative}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"validated_files={len(allowed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
