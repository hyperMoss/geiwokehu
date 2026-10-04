"""Local-only configuration for the manual, OpenAI-compatible lead analysis call."""

from __future__ import annotations

import os
import re
import shlex
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
_ENV_LINE = re.compile(r"^(?P<prefix>\s*(?:export\s+)?(?P<name>[A-Z][A-Z0-9_]*)\s*=).*$", re.ASCII)
_MODEL_KEYS = ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL")
_DEFAULT_MODEL = "deepseek-flash"
_DEFAULT_BASE_URL = "https://api.deepseek.com"


class ModelConfigError(ValueError):
    """A configuration error that is safe to display in the local UI."""


@dataclass(frozen=True)
class ModelConfig:
    api_key: str
    model: str
    base_url: str

    def public(self) -> dict[str, str | bool]:
        return {
            "configured": bool(self.api_key),
            "model": self.model,
            "base_url": self.base_url,
        }


def current_model_config() -> ModelConfig:
    """Read the active in-process configuration. The secret never leaves this module."""
    model = os.environ.get("DEEPSEEK_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
    base_url = os.environ.get("DEEPSEEK_BASE_URL", _DEFAULT_BASE_URL).strip() or _DEFAULT_BASE_URL
    return ModelConfig(
        api_key=os.environ.get("DEEPSEEK_API_KEY", "").strip(),
        model=_validate_model(model),
        base_url=_validate_base_url(base_url),
    )


def public_model_config() -> dict[str, str | bool]:
    return current_model_config().public()


def update_model_config(payload: dict) -> dict[str, str | bool]:
    """Persist a manual model configuration without returning or logging its Key."""
    current = current_model_config()
    model = _validate_model(_required_text(payload, "model", 100))
    base_url = _validate_base_url(_required_text(payload, "base_url", 400))
    clear_api_key = payload.get("clear_api_key", False)
    if not isinstance(clear_api_key, bool):
        raise ModelConfigError("clear_api_key 格式无效")

    raw_key = payload.get("api_key")
    if raw_key is not None and (not isinstance(raw_key, str) or len(raw_key) > 2048):
        raise ModelConfigError("API Key 格式无效")
    api_key = raw_key.strip() if isinstance(raw_key, str) else ""
    if any(char in api_key for char in "\x00\r\n"):
        raise ModelConfigError("API Key 格式无效")
    if api_key and clear_api_key:
        raise ModelConfigError("不能同时保存和清除 API Key")

    updates: dict[str, str] = {
        "DEEPSEEK_MODEL": model,
        "DEEPSEEK_BASE_URL": base_url,
    }
    if api_key:
        updates["DEEPSEEK_API_KEY"] = api_key
    elif clear_api_key:
        updates["DEEPSEEK_API_KEY"] = ""

    _write_env_updates(updates)
    for key, value in updates.items():
        os.environ[key] = value
    return public_model_config()


def _env_path() -> Path:
    value = os.environ.get("CRAWLER_ENV_PATH", "").strip()
    return Path(value).expanduser().resolve() if value else ROOT / ".env.local"


def _write_env_updates(updates: dict[str, str]) -> None:
    path = _env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = original.splitlines(keepends=True)
    seen: set[str] = set()
    rewritten: list[str] = []
    for line in lines:
        match = _ENV_LINE.match(line.rstrip("\n"))
        name = match.group("name") if match else ""
        if name in updates:
            rewritten.append(f"{name}={shlex.quote(updates[name])}\n")
            seen.add(name)
        else:
            rewritten.append(line)
    if rewritten and not rewritten[-1].endswith("\n"):
        rewritten[-1] += "\n"
    for name in _MODEL_KEYS:
        if name in updates and name not in seen:
            rewritten.append(f"{name}={shlex.quote(updates[name])}\n")

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        stream.writelines(rewritten)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = Path(stream.name)
    try:
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _required_text(payload: dict, name: str, limit: int) -> str:
    value = payload.get(name)
    if not isinstance(value, str):
        raise ModelConfigError(f"{name} 格式无效")
    normalized = value.strip()
    if not normalized or len(normalized) > limit or any(char in normalized for char in "\x00\r\n"):
        raise ModelConfigError(f"{name} 格式无效")
    return normalized


def _validate_model(value: str) -> str:
    if not 1 <= len(value) <= 100 or any(char.isspace() or char in "\x00\r\n" for char in value):
        raise ModelConfigError("模型名格式无效")
    return value


def _validate_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ModelConfigError("模型地址必须是无参数的 https 基础地址")
    normalized = value.rstrip("/")
    if len(normalized) > 400:
        raise ModelConfigError("模型地址格式无效")
    return normalized
