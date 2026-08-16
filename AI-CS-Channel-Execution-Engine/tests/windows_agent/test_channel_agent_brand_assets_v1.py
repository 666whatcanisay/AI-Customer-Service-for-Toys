from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
from pathlib import Path

import pytest

from channel_agent.version import AGENT_VERSION
from channel_agent.windows import WINDOWS_CLIENT_VERSION


ROOT = Path(__file__).resolve().parents[2]
BRAND_ROOT = ROOT / "packaging" / "windows-client-v2" / "branding"


def _ico_sizes(path: Path) -> list[int]:
    payload = path.read_bytes()
    reserved, icon_type, count = struct.unpack_from("<HHH", payload, 0)
    assert (reserved, icon_type) == (0, 1)
    sizes: list[int] = []
    for index in range(count):
        width, height, colors, reserved_byte, planes, bits, length, offset = (
            struct.unpack_from("<BBBBHHII", payload, 6 + (index * 16))
        )
        assert colors == reserved_byte == 0
        assert planes == 1
        assert bits == 32
        actual_width = width or 256
        assert (height or 256) == actual_width
        assert payload[offset : offset + 8] == b"\x89PNG\r\n\x1a\n"
        assert offset + length <= len(payload)
        sizes.append(actual_width)
    return sizes


def test_brand_source_is_version_locked_and_unmodified() -> None:
    manifest = json.loads((BRAND_ROOT / "brand-assets.json").read_text(encoding="utf-8"))
    source = BRAND_ROOT / manifest["source_file"]
    payload = source.read_bytes()

    assert hashlib.sha256(payload).hexdigest() == manifest["source_sha256"]
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", payload[16:24])
    assert [width, height] == [manifest["source_width"], manifest["source_height"]]
    assert manifest["product_version"] == AGENT_VERSION == WINDOWS_CLIENT_VERSION


@pytest.mark.skipif(os.name != "nt", reason="Windows icon generation")
def test_brand_asset_generator_builds_all_multisize_variants(tmp_path: Path) -> None:
    generated = tmp_path / "branding"
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "build_channel_agent_brand_assets.ps1"),
            "-OutputDirectory",
            str(generated),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    expected_sizes = [16, 20, 24, 32, 48, 64, 128, 256]
    icon_names = [
        "channel-agent.ico",
        "channel-agent-tray-normal.ico",
        "channel-agent-tray-warning.ico",
        "channel-agent-tray-error.ico",
        "channel-agent-tray-offline.ico",
    ]
    for name in icon_names:
        assert _ico_sizes(generated / name) == expected_sizes
    assert len({hashlib.sha256((generated / name).read_bytes()).digest() for name in icon_names}) == 5
    build_manifest = json.loads(
        (generated / "brand-build-manifest.json").read_text(encoding="utf-8-sig")
    )
    assert build_manifest["product_version"] == WINDOWS_CLIENT_VERSION
    assert build_manifest["icon_sizes"] == expected_sizes


@pytest.mark.skipif(os.name != "nt", reason="Windows brand gate validation")
def test_brand_asset_gate_rejects_tampered_source(
    tmp_path: Path,
) -> None:
    manifest = json.loads((BRAND_ROOT / "brand-assets.json").read_text(encoding="utf-8"))
    source = BRAND_ROOT / manifest["source_file"]
    tampered = bytearray(source.read_bytes())
    tampered[-1] ^= 1
    (tmp_path / manifest["source_file"]).write_bytes(tampered)
    manifest_path = tmp_path / "brand-assets.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "build_channel_agent_brand_assets.ps1"),
            "-BrandManifestPath",
            str(manifest_path),
            "-OutputDirectory",
            str(tmp_path / "generated"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Brand source hash mismatch" in (result.stdout + result.stderr)


def test_launcher_and_installer_use_branding_with_runtime_fallback() -> None:
    launcher = (
        ROOT / "packaging" / "windows-client-v1" / "ChannelAgentLauncher.cs"
    ).read_text(encoding="utf-8-sig")
    installer = (
        ROOT
        / "packaging"
        / "windows-client-v1"
        / "Install-AI-CS-Channel-Agent.ps1"
    ).read_text(encoding="utf-8-sig")
    build = (ROOT / "scripts" / "build_channel_agent_windows_client.ps1").read_text(
        encoding="utf-8-sig"
    )
    brand_upgrade = (
        ROOT / "scripts" / "upgrade_channel_agent_brand_only.ps1"
    ).read_text(encoding="utf-8-sig")

    assert 'BrandIcon("normal", SystemIcons.Information)' in launcher
    assert 'BrandIcon("warning", SystemIcons.Warning)' in launcher
    assert 'BrandIcon("error", SystemIcons.Error)' in launcher
    assert 'BrandIcon("offline", SystemIcons.Application)' in launcher
    assert "foreach (var icon in brandIcons.Values) icon.Dispose();" in launcher
    assert "$shortcut.IconLocation" in installer
    assert "[ValidateSet('official', 'fallback')]" in build
    assert "Brand Asset Gate" in build
    assert "branding_status = $BrandingMode" in build
    assert "CompilerParameters" in build
    assert "/win32icon:" in build
    assert "AssemblyInformationalVersion" in build
    assert "AssemblyFileVersion" in build
    assert "Upgrade-ChannelAgent-BrandOnly.ps1" in build
    assert "app\\channel-agent.pyz" in brand_upgrade
    assert "Agent Runtime PID changed during brand-only upgrade" in brand_upgrade
    assert "Authorized stores changed during brand upgrade" in brand_upgrade
    assert "Stop-Process -Id $tray.ProcessId" in brand_upgrade
    assert "$shortcutCreated = $true" in brand_upgrade
    assert "Remove-Item -LiteralPath $desktopShortcut -Force" in brand_upgrade
    assert 'new[] { "stop"' not in brand_upgrade
