from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock, Thread
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from .config import AgentConfigError, ChannelAgentConfig, load_agent_config, save_agent_config
from .onboarding import (
    ChannelAgentOnboardingService,
    OnboardingError,
    PairingConfirmation,
)


DOCTOR_SCHEMA_VERSION = "channel-agent-doctor.v1"
CONFIG_CENTER_SCHEMA_VERSION = "channel-agent-config-center.v1"
REPAIR_SCHEMA_VERSION = "channel-agent-repair.v1"

_BASIC_FIELDS = {
    "server_url",
    "ai_cs_platform_url",
    "connect_timeout_seconds",
    "heartbeat_interval_seconds",
}
_ADVANCED_FIELDS = {
    "runtime_mode",
    "browser_enabled",
    "pdd_login_observation_enabled",
    "customer_assistant_enabled",
    "pdd_login_url",
    "pdd_customer_service_url",
    "conversation_buffer_window_seconds",
}
_LOCKED_FIELDS = {
    "manual_approval_required",
    "auto_reply_enabled",
    "real_send_enabled",
    "real_platform_activation_allowed",
}
_SENSITIVE_PARTS = ("password", "cookie", "token", "secret", "private_key", "authorization")
_RESTART_FIELDS = {
    "server_url",
    "connect_timeout_seconds",
    "heartbeat_interval_seconds",
    "runtime_mode",
    "browser_enabled",
    "pdd_login_observation_enabled",
    "customer_assistant_enabled",
    "pdd_login_url",
    "pdd_customer_service_url",
    "conversation_buffer_window_seconds",
}


class OperationsCenterError(RuntimeError):
    def __init__(self, message: str, *, code: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class ChannelAgentOperationsCenter:
    """Credential-free local diagnostics, configuration and bounded repair.

    This service deliberately owns no message, AI, approval or execution code.
    It may only inspect local public state, validate allowlisted configuration,
    and request a controlled Agent reload that preserves the browser profile.
    """

    def __init__(
        self,
        *,
        data_root: str | Path,
        config_path: str | Path,
        onboarding: ChannelAgentOnboardingService | None = None,
        http_client_factory: Any = httpx.Client,
    ) -> None:
        self.data_root = Path(data_root).resolve()
        self.config_path = Path(config_path).resolve()
        self._http_client_factory = http_client_factory
        self._onboarding = onboarding
        self._lock = RLock()
        self._repairs: dict[str, dict[str, Any]] = {}
        self._active_repair_id: str | None = None

    @property
    def onboarding(self) -> ChannelAgentOnboardingService:
        with self._lock:
            if self._onboarding is None:
                self._onboarding = ChannelAgentOnboardingService(
                    data_root=self.data_root,
                    config_path=self.config_path,
                )
            return self._onboarding

    def doctor(self, *, deep: bool = False) -> dict[str, Any]:
        checked_at = _now()
        state = _read_json(self.data_root / "runtime" / "channel-agent-state.json")
        components: list[dict[str, Any]] = []
        config: ChannelAgentConfig | None = None
        try:
            config = load_agent_config(self.config_path)
            components.append(_component(
                "本地配置文件", "PASS", "CONFIG_VALID", "配置格式正确。",
                checked_at, False, "无需操作。", scope="LOGIN",
            ))
        except AgentConfigError:
            components.append(_component(
                "本地配置文件", "BLOCKED", "CONFIG_INVALID_OR_MISSING",
                "Agent 配置缺失或格式不正确。", checked_at, True,
                "打开手动配置，修正标记字段；如已有备份可使用一键修复。",
                scope="LOGIN",
            ))

        process_status = str(state.get("process_status") or "STARTING")
        components.append(_component(
            "ChannelAgent进程",
            "PASS" if process_status in {"RUNNING", "DEGRADED", "STARTING"} else "BLOCKED",
            "AGENT_PROCESS_RUNNING" if process_status in {"RUNNING", "DEGRADED", "STARTING"} else "AGENT_PROCESS_NOT_RUNNING",
            "Agent 本地进程正在运行。" if process_status in {"RUNNING", "DEGRADED", "STARTING"} else "Agent Runtime 未正常运行。",
            checked_at, process_status not in {"RUNNING", "DEGRADED", "STARTING"},
            "无需操作。" if process_status in {"RUNNING", "DEGRADED", "STARTING"} else "点击一键修复以安全重载 Agent。",
            {"processStatus": process_status},
            scope="LOGIN",
        ))

        if config is not None:
            components.extend(self._service_checks(config, checked_at, deep=deep))
            components.extend(self._runtime_checks(config, state, checked_at))
        else:
            components.extend([
                _component("AI-CS身份服务", "BLOCKED", "AI_CS_CONFIG_UNAVAILABLE", "配置不可用，无法确定身份服务地址。", checked_at, True, "先修复或填写本地配置。", scope="LOGIN"),
                _component("Channel Engine", "BLOCKED", "CHANNEL_ENGINE_CONFIG_UNAVAILABLE", "配置不可用，无法确定 Channel Engine 地址。", checked_at, True, "先修复或填写本地配置。", scope="LOGIN"),
            ])

        overall: Literal["PASS", "WARNING", "BLOCKED"] = "PASS"
        if any(item["status"] == "BLOCKED" for item in components):
            overall = "BLOCKED"
        elif any(item["status"] == "WARNING" for item in components):
            overall = "WARNING"
        return {
            "schema_version": DOCTOR_SCHEMA_VERSION,
            "overall": overall,
            "checked_at": checked_at,
            "mode": "DEEP" if deep else "QUICK",
            "auto_expand": overall == "BLOCKED",
            "components": components,
            "safe_to_continue": overall != "BLOCKED",
            "login_allowed": not any(
                item["status"] == "BLOCKED" and item["scope"] == "LOGIN"
                for item in components
            ),
            "sanitized": True,
        }

    def config_view(self) -> dict[str, Any]:
        try:
            config = load_agent_config(self.config_path)
        except AgentConfigError as exc:
            return {
                "schema_version": CONFIG_CENTER_SCHEMA_VERSION,
                "status": "BLOCKED",
                "error": {"code": "CONFIG_INVALID_OR_MISSING", "message": str(exc)},
                "basic": {}, "advanced": {}, "read_only": self._read_only(None),
                "safety": self._safety(),
            }
        public = config.public_view()
        return {
            "schema_version": CONFIG_CENTER_SCHEMA_VERSION,
            "status": "PASS",
            "basic": {key: public.get(key) for key in sorted(_BASIC_FIELDS)},
            "advanced": {key: public.get(key) for key in sorted(_ADVANCED_FIELDS)},
            "read_only": self._read_only(config),
            "safety": self._safety(),
            "advanced_confirmation_phrase": "继续高级配置",
        }

    def validate_changes(self, payload: dict[str, Any], *, probe: bool = True) -> dict[str, Any]:
        changes = payload.get("changes")
        if not isinstance(changes, dict) or not changes:
            raise OperationsCenterError("没有可校验的配置字段。", code="CONFIG_CHANGES_REQUIRED")
        self._reject_sensitive(changes)
        unknown = set(changes) - _BASIC_FIELDS - _ADVANCED_FIELDS - _LOCKED_FIELDS
        if unknown:
            raise OperationsCenterError(
                f"不允许修改字段：{', '.join(sorted(unknown))}", code="CONFIG_FIELD_NOT_ALLOWED"
            )
        locked = set(changes) & _LOCKED_FIELDS
        if locked:
            raise OperationsCenterError(
                f"安全锁不可修改：{', '.join(sorted(locked))}", code="SAFETY_LOCKED_FIELD"
            )
        if set(changes) & _ADVANCED_FIELDS and payload.get("advanced_confirmation") != "继续高级配置":
            raise OperationsCenterError(
                "请输入“继续高级配置”后再修改高级配置。", code="ADVANCED_CONFIRMATION_REQUIRED"
            )
        if changes.get("runtime_mode") == "PRODUCTION":
            raise OperationsCenterError("本地界面禁止开启生产模式。", code="PRODUCTION_MODE_FORBIDDEN")
        try:
            current = load_agent_config(self.config_path)
        except AgentConfigError as exc:
            raise OperationsCenterError(str(exc), code="CONFIG_INVALID_OR_MISSING", status=409) from exc
        merged = current.model_dump(mode="python")
        merged.update(changes)
        merged.update(self._safety())
        try:
            candidate = ChannelAgentConfig.model_validate(merged)
        except ValidationError as exc:
            errors = [
                {"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
                for item in exc.errors(include_url=False)
            ]
            return {"valid": False, "status": "BLOCKED", "errors": errors, "probes": []}
        probes: list[dict[str, Any]] = []
        if probe:
            probes = self._candidate_probes(candidate, changes)
        valid = not any(item["status"] == "BLOCKED" for item in probes)
        return {
            "valid": valid,
            "status": "PASS" if valid else "BLOCKED",
            "errors": [],
            "probes": probes,
            "changed_fields": sorted(key for key, value in changes.items() if getattr(current, key) != value),
            "restart_required": bool(set(changes) & _RESTART_FIELDS),
            "candidate": candidate,
        }

    def save_changes(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.validate_changes(payload, probe=True)
        if not result["valid"]:
            return {key: value for key, value in result.items() if key != "candidate"}
        candidate = result.pop("candidate")
        assert isinstance(candidate, ChannelAgentConfig)
        save_probes = self._candidate_probes(
            candidate,
            {
                "server_url": candidate.server_url,
                "ai_cs_platform_url": candidate.ai_cs_platform_url,
            },
        )
        result["probes"] = save_probes
        if any(item["status"] == "BLOCKED" for item in save_probes):
            return {
                **result,
                "valid": False,
                "status": "BLOCKED",
                "saved": False,
            }
        backup = self._backup_path()
        backup.parent.mkdir(parents=True, exist_ok=True)
        if self.config_path.is_file():
            _atomic_bytes(backup, self.config_path.read_bytes())
        save_agent_config(self.config_path, candidate)
        changed = result["changed_fields"]
        if result["restart_required"]:
            _atomic_bytes(
                self.data_root / "runtime" / "config-reload-pending.json",
                (json.dumps(
                    {
                        "schema_version": "channel-agent-config-reload.v1",
                        "candidate_sha256": hashlib.sha256(self.config_path.read_bytes()).hexdigest(),
                        "requested_at": _now(),
                        "rollback_attempted": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                ) + "\n").encode("utf-8"),
            )
            self.request_reload("CONFIGURATION_CHANGED", preserve_browser=True)
        else:
            _atomic_bytes(self._last_known_good_path(), self.config_path.read_bytes())
        return {
            **result,
            "saved": True,
            "reload_requested": result["restart_required"],
            "backup_created": backup.is_file(),
        }

    def start_repair(self) -> dict[str, Any]:
        with self._lock:
            if self._active_repair_id is not None:
                active = self._repairs.get(self._active_repair_id, {})
                if active.get("status") == "RUNNING":
                    raise OperationsCenterError("已有修复任务正在运行。", code="REPAIR_ALREADY_RUNNING", status=409)
            if self._recent_repair_count() >= 3:
                raise OperationsCenterError("一小时内修复次数已达上限，请人工检查。", code="REPAIR_RATE_LIMITED", status=429)
            repair_id = uuid.uuid4().hex
            record = {
                "schema_version": REPAIR_SCHEMA_VERSION,
                "repair_id": repair_id,
                "status": "RUNNING",
                "started_at": _now(),
                "steps": [],
                "requires_human": False,
            }
            self._repairs[repair_id] = record
            self._active_repair_id = repair_id
            self._append_repair_history(repair_id)
        Thread(target=self._repair_worker, args=(repair_id,), daemon=True, name="channel-agent-safe-repair").start()
        return dict(record)

    def repair_status(self, repair_id: str) -> dict[str, Any]:
        if len(repair_id) != 32 or any(char not in "0123456789abcdef" for char in repair_id):
            raise OperationsCenterError("修复任务编号无效。", code="REPAIR_ID_INVALID")
        with self._lock:
            record = self._repairs.get(repair_id)
            if record is None:
                stored = _read_json(self._repair_status_path())
                if stored.get("repair_id") == repair_id:
                    record = stored
            if record is None:
                raise OperationsCenterError("没有找到该修复任务。", code="REPAIR_NOT_FOUND", status=404)
            return json.loads(json.dumps(record, ensure_ascii=False))

    def discover_hosts(self) -> dict[str, Any]:
        try:
            return {"hosts": list(self.onboarding.discover_hosts()), "human_confirmation_required": True}
        except Exception as exc:
            raise OperationsCenterError("未发现可信主机，请检查主机端服务和局域网。", code="HOST_DISCOVERY_FAILED", status=503) from exc

    def pair_host(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            confirmation = PairingConfirmation.model_validate(payload)
            result = self.onboarding.pair(confirmation)
        except OnboardingError as exc:
            raise OperationsCenterError(str(exc), code=exc.error_code, status=409) from exc
        except Exception as exc:
            raise OperationsCenterError("连接码或主机信息无效。", code="PAIRING_REQUEST_INVALID") from exc
        self.request_reload("HOST_PAIRING_COMPLETED", preserve_browser=True)
        return result

    def request_reload(self, reason: str, *, preserve_browser: bool) -> None:
        payload = {
            "schema_version": "channel-agent-reload.v1",
            "reason": reason,
            "preserve_browser": bool(preserve_browser),
            "requested_at": _now(),
        }
        _atomic_bytes(
            self.data_root / "runtime" / "reload.request",
            (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
        _atomic_bytes(
            self.data_root / "runtime" / "restart-agent.request",
            (
                b"restart-preserve-assistant\n"
                if preserve_browser
                else b"restart\n"
            ),
        )

    def _repair_worker(self, repair_id: str) -> None:
        steps: list[dict[str, Any]] = []
        try:
            config: ChannelAgentConfig | None = None
            try:
                config = load_agent_config(self.config_path)
                steps.append(_repair_step("CHECK_AGENT_AND_CONFIG", "PASS", "Agent 状态文件和配置可读取。"))
            except AgentConfigError:
                restored = self._restore_last_known_good()
                steps.append(_repair_step("RESTORE_LAST_VERIFIED_CONFIG", "PASS" if restored else "BLOCKED", "已恢复最近验证配置。" if restored else "没有可用的最近验证配置。"))
                if restored:
                    config = load_agent_config(self.config_path)
            if config is None:
                self._finish_repair(repair_id, "NEEDS_HUMAN", steps, requires_human=True, message="请人工填写配置或使用连接码绑定可信主机。")
                return
            if config.ai_cs_platform_url is None:
                restored = self._restore_ai_cs_from_verified_source(config)
                steps.append(_repair_step("RESTORE_AI_CS_ADDRESS", "PASS" if restored else "BLOCKED", "已从已验证配置补齐 AI-CS 地址。" if restored else "没有可信 AI-CS 地址可自动补齐。"))
                if not restored:
                    self._finish_repair(repair_id, "NEEDS_HUMAN", steps, requires_human=True, message="请人工选择可信主机或填写 AI-CS 地址。")
                    return
                config = load_agent_config(self.config_path)
            probes = self._candidate_probes(config, {"server_url": config.server_url, "ai_cs_platform_url": config.ai_cs_platform_url})
            for probe in probes:
                steps.append(_repair_step(f"CHECK_{probe['component_code']}", probe["status"], probe["message"]))
            if any(item["status"] == "BLOCKED" for item in probes):
                self._finish_repair(repair_id, "NEEDS_HUMAN", steps, requires_human=True, message="服务仍不可达，请在主机端启动服务后重新检测。")
                return
            self.request_reload("ONE_CLICK_REPAIR", preserve_browser=True)
            steps.append(_repair_step("SAFE_RELOAD", "PASS", "已请求安全重载；PDD Profile 与 Session 保持不变。"))
            self._finish_repair(repair_id, "RELOAD_REQUESTED", steps, requires_human=False, message="修复检查通过，Agent 正在安全重载。")
        except Exception:
            self._finish_repair(repair_id, "FAILED", steps, requires_human=True, message=f"修复未完成，故障编号：{repair_id[:12]}。")

    def _service_checks(self, config: ChannelAgentConfig, checked_at: str, *, deep: bool) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        if config.ai_cs_platform_url is None:
            checks.append(_component("AI-CS身份服务", "BLOCKED", "AI_CS_ADDRESS_MISSING", "未配置 AI-CS 身份服务地址。", checked_at, True, "点击一键修复，或在基础配置中填写身份服务地址。", scope="LOGIN"))
        else:
            status, code, message = self._probe(config.ai_cs_platform_url, "/health", config.connect_timeout_seconds if deep else min(config.connect_timeout_seconds, 0.45), config.ai_cs_ca_certificate_path)
            checks.append(_component("AI-CS身份服务", status, code, message, checked_at, status == "BLOCKED", "服务不可达时请启动主机端 AI-CS，或检查地址和端口。", {"origin": _safe_origin(config.ai_cs_platform_url)}, scope="LOGIN"))
        status, code, message = self._probe(config.server_url, "/health", config.connect_timeout_seconds if deep else min(config.connect_timeout_seconds, 0.45), config.server_ca_certificate_path)
        checks.append(_component("Channel Engine", status, code, message, checked_at, status == "BLOCKED", "检查 Channel Engine 服务、设备注册与网络。", {"origin": _safe_origin(config.server_url)}, scope="LOGIN"))
        return checks

    def _runtime_checks(self, config: ChannelAgentConfig, state: dict[str, Any], checked_at: str) -> list[dict[str, Any]]:
        identity = str(state.get("identity_status") or "UNBOUND")
        active_store = state.get("active_store_id") or state.get("store_id")
        browser_status = str(state.get("browser_status") or "STOPPED")
        pdd_state = state.get("pdd_login_state")
        checks = [
            _component("设备注册与身份绑定", "PASS" if identity in {"BOUND", "ACTIVE"} else "BLOCKED", "IDENTITY_BOUND" if identity in {"BOUND", "ACTIVE"} else "CHANNEL_ENGINE_IDENTITY_UNBOUND", "设备已完成身份绑定。" if identity in {"BOUND", "ACTIVE"} else "这是这台电脑第一次使用，尚未和客服账号绑定；不是密码错误。", checked_at, False, "请先登录客服账号，程序会引导您绑定这台电脑。", {"identityStatus": identity}, scope="ONBOARDING"),
            _component("当前店铺绑定", "PASS" if active_store else "WARNING", "ACTIVE_STORE_SELECTED" if active_store else "ACTIVE_STORE_NOT_SELECTED", "已选择当前工作店铺。" if active_store else ("等待完成设备绑定后读取授权店铺。" if identity not in {"BOUND", "ACTIVE"} else "尚未确认当前工作店铺。"), checked_at, False, "先完成设备绑定；登录 PDD 后再确认程序识别到的店铺。", {"dependsOn": "CHANNEL_ENGINE_IDENTITY_UNBOUND"} if identity not in {"BOUND", "ACTIVE"} else {}, scope="ONBOARDING"),
            _component("Edge运行环境", "PASS" if not config.browser_enabled or browser_status in {"OPENED", "READY", "WAITING_LOGIN"} else "WARNING", "BROWSER_READY" if not config.browser_enabled or browser_status in {"OPENED", "READY", "WAITING_LOGIN"} else "BROWSER_NOT_READY", "浏览器运行状态可用。" if not config.browser_enabled or browser_status in {"OPENED", "READY", "WAITING_LOGIN"} else "浏览器尚未就绪。", checked_at, False, "需要时由客服人工打开或恢复浏览器。", {"browserStatus": browser_status}),
            _component("PDD Session状态", "PASS" if not config.pdd_login_observation_enabled or pdd_state in {"PDD_LOGIN_SUCCESS", "CUSTOMER_SERVICE_READY", "CUSTOMER_SERVICE_RUNNING"} else "WARNING", "PDD_SESSION_READY" if not config.pdd_login_observation_enabled or pdd_state in {"PDD_LOGIN_SUCCESS", "CUSTOMER_SERVICE_READY", "CUSTOMER_SERVICE_RUNNING"} else "PDD_SESSION_REQUIRES_HUMAN", "PDD Session 可用。" if not config.pdd_login_observation_enabled or pdd_state in {"PDD_LOGIN_SUCCESS", "CUSTOMER_SERVICE_READY", "CUSTOMER_SERVICE_RUNNING"} else "PDD 需要人工扫码、验证或恢复。", checked_at, False, "请在 PDD 窗口完成人工操作；系统不会自动登录。"),
            _component("客服助手本地代理", "PASS" if config.ai_cs_platform_url else "BLOCKED", "LOCAL_PROXY_READY" if config.ai_cs_platform_url else "LOCAL_PROXY_TARGET_MISSING", "本地代理目标已配置。" if config.ai_cs_platform_url else "本地代理没有 AI-CS 目标。", checked_at, True, "补齐 AI-CS 身份服务地址。", scope="LOGIN"),
            _component("人工审批和发送安全", "PASS", "SAFETY_LOCKS_ENFORCED", "人工审批保持开启，自动回复和真实发送保持关闭。", checked_at, False, "无需操作。", self._safety()),
        ]
        return checks

    def _candidate_probes(self, config: ChannelAgentConfig, changes: dict[str, Any]) -> list[dict[str, Any]]:
        probes: list[dict[str, Any]] = []
        if "server_url" in changes:
            status, code, message = self._probe(config.server_url, "/health", config.connect_timeout_seconds, config.server_ca_certificate_path)
            probes.append({"component_code": "CHANNEL_ENGINE", "status": status, "code": code, "message": message})
        if "ai_cs_platform_url" in changes or config.ai_cs_platform_url is None:
            if config.ai_cs_platform_url is None:
                probes.append({"component_code": "AI_CS", "status": "BLOCKED", "code": "AI_CS_ADDRESS_MISSING", "message": "AI-CS 身份服务地址缺失。"})
            else:
                status, code, message = self._probe(config.ai_cs_platform_url, "/health", config.connect_timeout_seconds, config.ai_cs_ca_certificate_path)
                probes.append({"component_code": "AI_CS", "status": status, "code": code, "message": message})
        return probes

    def _probe(self, origin: str, path: str, timeout: float, ca_path: Path | None) -> tuple[str, str, str]:
        verify: bool | str = str(ca_path) if ca_path is not None else True
        try:
            with self._http_client_factory(timeout=min(max(timeout, 0.2), 10.0), follow_redirects=False, trust_env=False, verify=verify) as client:
                response = client.get(f"{origin.rstrip('/')}{path}")
            if response.status_code == 200:
                return "PASS", "SERVICE_HEALTHY", "服务健康检查通过。"
            if response.status_code in {401, 403}:
                return "BLOCKED", "SERVICE_AUTHENTICATION_REJECTED", f"服务拒绝访问（HTTP {response.status_code}）。"
            return "BLOCKED", f"SERVICE_HTTP_{response.status_code}", f"服务健康检查返回 HTTP {response.status_code}。"
        except httpx.TimeoutException:
            return "BLOCKED", "SERVICE_TIMEOUT", "服务连接超时。"
        except Exception:
            return "BLOCKED", "SERVICE_UNAVAILABLE", "服务未启动、地址错误或网络不可达。"

    def _restore_last_known_good(self) -> bool:
        source = self._last_known_good_path()
        if not source.is_file():
            source = self._backup_path()
        try:
            candidate = load_agent_config(source)
            save_agent_config(self.config_path, candidate)
            return True
        except AgentConfigError:
            return False

    def _restore_ai_cs_from_verified_source(self, current: ChannelAgentConfig) -> bool:
        for source in (self._last_known_good_path(), self._backup_path()):
            try:
                verified = load_agent_config(source)
            except AgentConfigError:
                continue
            if verified.ai_cs_platform_url:
                candidate = ChannelAgentConfig.model_validate({
                    **current.model_dump(mode="python"),
                    "ai_cs_platform_url": verified.ai_cs_platform_url,
                    "ai_cs_ca_certificate_path": verified.ai_cs_ca_certificate_path,
                    "ai_cs_platform_proxy_mode": verified.ai_cs_platform_proxy_mode,
                })
                save_agent_config(self.config_path, candidate)
                return True
        return False

    def _finish_repair(self, repair_id: str, status: str, steps: list[dict[str, Any]], *, requires_human: bool, message: str) -> None:
        with self._lock:
            record = self._repairs[repair_id]
            record.update({"status": status, "steps": steps, "requires_human": requires_human, "message": message, "finished_at": _now()})
            self._active_repair_id = None
            _atomic_bytes(self._repair_status_path(), (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    def _read_only(self, config: ChannelAgentConfig | None) -> dict[str, Any]:
        state = _read_json(self.data_root / "runtime" / "channel-agent-state.json")
        return {
            "agent_id": config.agent_id if config else state.get("agent_id"),
            "device_id": config.device_id if config else state.get("device_id"),
            "user_binding": state.get("user_id") or (config.user_reference if config else None),
            "authorized_store_ids": state.get("authorized_store_ids") or (list(config.store_references) if config else []),
            "active_store_id": state.get("active_store_id") or (config.store_reference if config else None),
            "credential_reference": config.device_credential_reference if config else None,
            "certificate_fingerprint": self._certificate_fingerprint(config.server_ca_certificate_path if config else None),
            "browser_profile_reference": state.get("browser_profile_reference"),
        }

    @staticmethod
    def _safety() -> dict[str, bool]:
        return {"manual_approval_required": True, "auto_reply_enabled": False, "real_send_enabled": False, "real_platform_activation_allowed": False}

    @staticmethod
    def _reject_sensitive(value: Any, path: str = "changes") -> None:
        if isinstance(value, dict):
            for raw_key, child in value.items():
                key = str(raw_key).casefold()
                if any(part in key for part in _SENSITIVE_PARTS):
                    raise OperationsCenterError(f"禁止提交敏感字段：{path}.{raw_key}", code="SENSITIVE_FIELD_REJECTED")
                ChannelAgentOperationsCenter._reject_sensitive(child, f"{path}.{raw_key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                ChannelAgentOperationsCenter._reject_sensitive(child, f"{path}[{index}]")

    @staticmethod
    def _certificate_fingerprint(path: Path | None) -> str | None:
        if path is None:
            return None
        try:
            return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None

    def _backup_path(self) -> Path:
        return self.data_root / "runtime" / "config-backups" / "agent.previous.json"

    def _last_known_good_path(self) -> Path:
        return self.data_root / "runtime" / "config-backups" / "agent.last-known-good.json"

    def _repair_status_path(self) -> Path:
        return self.data_root / "runtime" / "repair-status.json"

    def _repair_history_path(self) -> Path:
        return self.data_root / "runtime" / "repair-history.json"

    def _recent_repair_count(self) -> int:
        value = _read_json(self._repair_history_path())
        cutoff = time.time() - 3600
        return sum(1 for item in value.get("items", []) if isinstance(item, dict) and float(item.get("epoch", 0)) >= cutoff)

    def _append_repair_history(self, repair_id: str) -> None:
        path = self._repair_history_path()
        value = _read_json(path)
        items = [item for item in value.get("items", []) if isinstance(item, dict) and float(item.get("epoch", 0)) >= time.time() - 3600]
        items.append({"repair_id": repair_id, "epoch": time.time()})
        _atomic_bytes(path, (json.dumps({"items": items[-3:]}, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _component(
    name: str,
    status: str,
    code: str,
    reason: str,
    checked_at: str,
    repairable: bool,
    next_action: str,
    technical: dict[str, Any] | None = None,
    *,
    scope: Literal["LOGIN", "ONBOARDING", "RUNTIME"] | None = None,
) -> dict[str, Any]:
    resolved_scope = scope or (
        "LOGIN"
        if code.startswith(("CONFIG_", "AI_CS_", "CHANNEL_ENGINE_", "LOCAL_PROXY_"))
        and code != "CHANNEL_ENGINE_IDENTITY_UNBOUND"
        else "RUNTIME"
    )
    return {
        "component": name,
        "status": status,
        "status_label": {"PASS": "正常", "WARNING": "需关注", "BLOCKED": "已阻断"}[status],
        "error_code": code,
        "reason": reason,
        "checked_at": checked_at,
        "repairable": repairable,
        "next_action": next_action,
        "scope": resolved_scope,
        "technical": technical or {},
    }


def _repair_step(code: str, status: str, message: str) -> dict[str, Any]:
    return {"code": code, "status": status, "message": message, "timestamp": _now()}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if len(raw) > 2 * 1024 * 1024:
            return {}
        value = json.loads(raw.decode("utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def _safe_origin(value: str) -> str:
    from urllib.parse import urlsplit
    parsed = urlsplit(value)
    return f"{parsed.scheme}://{parsed.hostname}" + (f":{parsed.port}" if parsed.port else "")


def _now() -> str:
    return datetime.now(UTC).isoformat()


__all__ = ["ChannelAgentOperationsCenter", "OperationsCenterError"]
