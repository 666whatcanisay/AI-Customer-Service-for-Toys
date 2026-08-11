from __future__ import annotations

import json
import os
import socket
import uuid
import webbrowser
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import Any, Callable

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .client import ChannelEngineClient
from .config import AgentConfigError, ChannelAgentConfig, load_agent_config, save_agent_config
from .contract import AgentRuntimeStatus
from .control_v2 import (
    LANDiscoveryAnnouncement,
    PairDeviceRequest,
    PairDeviceResponse,
    certificate_sha256,
    discover_lan_hosts,
    normalize_pairing_code,
    verify_announcement,
)
from .security import DeviceCredentialStore, WindowsDeviceCredentialStore


class OnboardingError(RuntimeError):
    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class OnboardingModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PairingConfirmation(OnboardingModel):
    host_id: str = Field(min_length=1, max_length=128)
    pairing_code: str = Field(min_length=12, max_length=32, repr=False)
    human_confirmed: bool


class ChannelAgentOnboardingService:
    def __init__(
        self,
        *,
        data_root: str | Path,
        config_path: str | Path,
        credential_store: DeviceCredentialStore | None = None,
        discover: Callable[..., tuple[LANDiscoveryAnnouncement, ...]] = discover_lan_hosts,
        http_client_factory: Callable[..., Any] = httpx.Client,
        channel_client_factory: Callable[..., ChannelEngineClient] = ChannelEngineClient,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.data_root = Path(data_root).resolve()
        self.config_path = Path(config_path).resolve()
        self._credential_store = credential_store or WindowsDeviceCredentialStore()
        self._discover = discover
        self._http_client_factory = http_client_factory
        self._channel_client_factory = channel_client_factory
        self._clock = clock
        self._announcements: dict[str, LANDiscoveryAnnouncement] = {}
        self.agent_id, self.device_id = self._load_or_create_device_identity()

    def status(self) -> dict[str, object]:
        return {
            "schemaVersion": "channel-agent-onboarding.v1",
            "state": "CONFIGURED" if self.config_path.is_file() else "INSTALLED",
            "agentId": self.agent_id,
            "deviceId": self.device_id,
            "hostCount": len(self._announcements),
            "humanConfirmationRequired": True,
            "automaticBinding": False,
        }

    def discover_hosts(self) -> tuple[dict[str, object], ...]:
        announcements = self._discover(timeout_seconds=2.0)
        self._announcements = {
            item.candidate.host_id: item for item in announcements
        }
        return tuple(self._public_candidate(item) for item in announcements)

    def pair(self, confirmation: PairingConfirmation) -> dict[str, object]:
        if not confirmation.human_confirmed:
            raise OnboardingError(
                "必须由客服确认绑定所选主机",
                error_code="HUMAN_CONFIRMATION_REQUIRED",
            )
        try:
            announcement = self._announcements[confirmation.host_id]
        except KeyError as exc:
            raise OnboardingError(
                "所选主机不在本次发现结果中，请重新搜索",
                error_code="DISCOVERED_HOST_REQUIRED",
            ) from exc
        try:
            verify_announcement(announcement, confirmation.pairing_code)
        except Exception as exc:
            raise OnboardingError(
                "连接码无法验证所选主机",
                error_code="HOST_PAIRING_PROOF_INVALID",
            ) from exc
        candidate = announcement.candidate
        if certificate_sha256(candidate.ca_certificate_pem) != candidate.certificate_sha256:
            raise OnboardingError(
                "主机证书指纹与发现信息不一致",
                error_code="HOST_CERTIFICATE_FINGERPRINT_MISMATCH",
            )
        trust_path = self.data_root / "trust" / f"{candidate.host_id}.ca.pem"
        _atomic_bytes(trust_path, candidate.ca_certificate_pem.encode("utf-8"))
        ai_cs_trust_path: Path | None = None
        if candidate.customer_service_url is not None:
            if (
                candidate.customer_service_ca_certificate_pem is None
                or candidate.customer_service_certificate_sha256 is None
                or certificate_sha256(candidate.customer_service_ca_certificate_pem)
                != candidate.customer_service_certificate_sha256
            ):
                raise OnboardingError(
                    "AI-CS 客服页面证书信息不完整或不一致",
                    error_code="AI_CS_CERTIFICATE_FINGERPRINT_MISMATCH",
                )
            ai_cs_trust_path = self.data_root / "trust" / f"{candidate.host_id}.ai-cs.ca.pem"
            _atomic_bytes(
                ai_cs_trust_path,
                candidate.customer_service_ca_certificate_pem.encode("utf-8"),
            )
        request = PairDeviceRequest(
            host_id=candidate.host_id,
            agent_id=self.agent_id,
            device_id=self.device_id,
            pairing_code=normalize_pairing_code(confirmation.pairing_code),
            human_confirmed=True,
            requested_at=self._clock(),
        )
        try:
            with self._http_client_factory(
                base_url=candidate.server_url,
                verify=str(trust_path),
                timeout=10.0,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = client.post(
                    "/channel-agent/v2/pair",
                    content=request.model_dump_json().encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
            if response.status_code != 200:
                raise OnboardingError(
                    "主机拒绝了绑定请求，请检查连接码",
                    error_code="PAIRING_REQUEST_REJECTED",
                )
            paired = PairDeviceResponse.model_validate(response.json())
        except OnboardingError:
            raise
        except Exception as exc:
            raise OnboardingError(
                "无法与所选主机建立安全连接",
                error_code="PAIRING_CONNECTION_FAILED",
            ) from exc
        if (
            paired.host_id != candidate.host_id
            or paired.agent_id != self.agent_id
            or paired.device_id != self.device_id
        ):
            raise OnboardingError(
                "主机返回了不匹配的设备身份",
                error_code="PAIRING_IDENTITY_MISMATCH",
            )
        self._credential_store.put(
            paired.device_credential_reference,
            paired.secret_bytes(),
        )
        existing: ChannelAgentConfig | None = None
        try:
            existing = load_agent_config(self.config_path)
        except AgentConfigError:
            pass
        ai_cs_platform_url = candidate.customer_service_url or (
            existing.ai_cs_platform_url if existing is not None else None
        )
        ai_cs_proxy_mode = (
            "SAME_ORIGIN_GATEWAY"
            if candidate.customer_service_url is not None
            else (
                existing.ai_cs_platform_proxy_mode
                if existing is not None
                else "DIRECT_API"
            )
        )
        ai_cs_ca_path = ai_cs_trust_path or (
            existing.ai_cs_ca_certificate_path if existing is not None else None
        )
        config = ChannelAgentConfig(
            config_version="2.0",
            server_url=candidate.server_url,
            host_id=candidate.host_id,
            agent_id=self.agent_id,
            device_id=self.device_id,
            device_credential_reference=paired.device_credential_reference,
            server_ca_certificate_path=trust_path,
            runtime_mode=(
                "PRODUCTION"
                if candidate.environment == "PRODUCTION"
                else "STAGING"
            ),
            desktop_ui_enabled=True,
            ai_cs_platform_url=ai_cs_platform_url,
            ai_cs_platform_proxy_mode=ai_cs_proxy_mode,
            ai_cs_ca_certificate_path=ai_cs_ca_path,
            browser_enabled=True,
            pdd_login_observation_enabled=True,
            pdd_login_url="https://mms.pinduoduo.com/login/",
            pdd_customer_service_url=(
                "https://mms.pinduoduo.com/chat-merchant/index.html#/"
            ),
            customer_assistant_enabled=True,
            manual_approval_required=True,
            auto_reply_enabled=False,
            real_send_enabled=False,
            log_directory=Path("logs"),
        )
        save_agent_config(self.config_path, config)
        connected = False
        try:
            client = self._channel_client_factory(
                config,
                credential_store=self._credential_store,
            )
            client.register(
                hostname=socket.gethostname(),
                status=AgentRuntimeStatus.STARTING,
                timestamp=self._clock(),
            )
            client.close()
            connected = True
        except Exception:
            connected = False
        return {
            "state": "CONNECTED" if connected else "PAIRED_RETRY_REQUIRED",
            "host": self._public_candidate(announcement),
            "agentId": self.agent_id,
            "deviceId": self.device_id,
            "configPath": str(self.config_path),
            "manualApprovalRequired": True,
            "autoReplyEnabled": False,
            "realSendEnabled": False,
            "nextStep": "启动客服助手并完成用户绑定与人工扫码",
        }

    def _load_or_create_device_identity(self) -> tuple[str, str]:
        path = self.data_root / "runtime" / "bootstrap-device.json"
        if path.is_file():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                return str(value["agent_id"]), str(value["device_id"])
            except (OSError, ValueError, KeyError, TypeError):
                raise OnboardingError(
                    "本机设备标识损坏，禁止自动覆盖",
                    error_code="DEVICE_IDENTITY_INVALID",
                )
        device_id = f"device-{uuid.uuid4().hex}"
        agent_id = f"agent-{uuid.uuid4().hex}"
        _atomic_bytes(
            path,
            (json.dumps(
                {"agent_id": agent_id, "device_id": device_id},
                ensure_ascii=False,
                indent=2,
            ) + "\n").encode("utf-8"),
        )
        return agent_id, device_id

    @staticmethod
    def _public_candidate(
        announcement: LANDiscoveryAnnouncement,
    ) -> dict[str, object]:
        candidate = announcement.candidate
        parsed = candidate.server_url.split("://", 1)[-1]
        return {
            "hostId": candidate.host_id,
            "hostName": candidate.host_name,
            "environment": candidate.environment,
            "serverAddress": parsed,
            "serverVersion": candidate.server_version,
            "certificateFingerprint": candidate.certificate_sha256,
            "customerServiceAddress": candidate.customer_service_url,
            "verified": False,
            "requiresConnectionCode": True,
            "requiresHumanConfirmation": True,
        }


class OnboardingWebServer:
    def __init__(
        self,
        service: ChannelAgentOnboardingService,
        *,
        port: int = 0,
    ) -> None:
        self.service = service
        self._server = _OnboardingHTTPServer(("127.0.0.1", port), _OnboardingHandler)
        self._server.service = service
        self._thread: Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/"

    def start(self, *, open_browser: bool = True) -> str:
        if self._thread is not None:
            return self.url
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        if open_browser:
            webbrowser.open(self.url)
        return self.url

    def serve_until(self, stop_event: Event) -> None:
        self.start()
        stop_event.wait()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=3)
        self._thread = None


class _OnboardingHTTPServer(ThreadingHTTPServer):
    service: ChannelAgentOnboardingService


class _OnboardingHandler(BaseHTTPRequestHandler):
    server: _OnboardingHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        if not self._valid_host():
            self._json(HTTPStatus.BAD_REQUEST, {"errorCode": "HOST_DENIED"})
            return
        if self.path == "/":
            payload = _ONBOARDING_HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/api/status":
            self._json(HTTPStatus.OK, self.server.service.status())
            return
        self._json(HTTPStatus.NOT_FOUND, {"errorCode": "NOT_FOUND"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._valid_host():
            self._json(HTTPStatus.BAD_REQUEST, {"errorCode": "HOST_DENIED"})
            return
        try:
            if self.path == "/api/discover":
                self._json(
                    HTTPStatus.OK,
                    {"hosts": list(self.server.service.discover_hosts())},
                )
                return
            if self.path == "/api/pair":
                payload = PairingConfirmation.model_validate(self._read_json())
                self._json(HTTPStatus.OK, self.server.service.pair(payload))
                return
        except OnboardingError as exc:
            self._json(
                HTTPStatus.CONFLICT,
                {"errorCode": exc.error_code, "message": str(exc)},
            )
            return
        except Exception:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"errorCode": "ONBOARDING_REQUEST_INVALID"},
            )
            return
        self._json(HTTPStatus.NOT_FOUND, {"errorCode": "NOT_FOUND"})

    def _read_json(self) -> object:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 1 <= length <= 65_536:
            raise ValueError("request size is invalid")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _valid_host(self) -> bool:
        return self.headers.get("Host", "").split(":", 1)[0] in {
            "127.0.0.1",
            "localhost",
        }

    def _json(self, status: int, value: object) -> None:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


_ONBOARDING_HTML = """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>连接 AI-CS 客服主机</title>
<style>body{font-family:"Microsoft YaHei",sans-serif;background:#f2f7f4;color:#173d2c;margin:0}.box{max-width:760px;margin:7vh auto;background:#fff;border:1px solid #cfe1d6;border-radius:18px;padding:32px;box-shadow:0 16px 45px #153d2420}h1{margin:0 0 8px}.muted{color:#668074}.host{border:1px solid #bcd7c7;padding:16px;border-radius:12px;margin:12px 0}.selected{border-color:#248653;background:#effaf3}button{background:#237a4b;color:#fff;border:0;border-radius:9px;padding:11px 18px;cursor:pointer}input{padding:11px;border:1px solid #9ebcab;border-radius:8px;font-size:18px;letter-spacing:2px}.danger{color:#a33}.ok{color:#176a3d}</style>
<div class="box"><h1>连接 AI-CS 客服主机</h1><p class="muted">系统只会发现主机，不会自动绑定。请核对主机后输入连接码并人工确认。</p><button onclick="discover()">搜索局域网主机</button><div id="hosts"></div><div id="pair" hidden><p>连接码</p><input id="code" maxlength="14" placeholder="例如 7K3M-9Q2X-4T8R"><label><input id="confirm" type="checkbox"> 我已核对主机信息并确认绑定这台电脑</label><p><button onclick="pair()">确认绑定</button></p></div><p id="message"></p></div>
<script>let selected=null;async function discover(){msg('正在搜索…');let r=await fetch('/api/discover',{method:'POST'}),j=await r.json();let h=document.getElementById('hosts');h.innerHTML='';j.hosts.forEach(x=>{let d=document.createElement('div');d.className='host';d.innerHTML=`<b>${x.hostName}</b><br>${x.serverAddress}<br>环境：${x.environment}　版本：${x.serverVersion}<br><small>证书：${x.certificateFingerprint.slice(0,16)}…</small>`;d.onclick=()=>{document.querySelectorAll('.host').forEach(n=>n.classList.remove('selected'));d.classList.add('selected');selected=x.hostId;document.getElementById('pair').hidden=false};h.appendChild(d)});msg(j.hosts.length?'请选择主机并输入连接码':'没有发现主机，请确认主机已启动');}async function pair(){if(!selected||!document.getElementById('confirm').checked){msg('请先选择主机并勾选人工确认',true);return}msg('正在建立安全连接…');let r=await fetch('/api/pair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({host_id:selected,pairing_code:document.getElementById('code').value,human_confirmed:true})}),j=await r.json();if(!r.ok){msg(j.message||'绑定失败',true);return}msg('绑定完成。现在可以启动客服助手并人工扫码登录 PDD。');}function msg(t,e=false){let n=document.getElementById('message');n.textContent=t;n.className=e?'danger':'ok'}</script>"""


__all__ = [
    "ChannelAgentOnboardingService",
    "OnboardingError",
    "OnboardingWebServer",
    "PairingConfirmation",
]
