"""CLI config handling for DueCheck."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

DEFAULT_TOKEN_ENV = "CANVAS_TOKEN"
DEFAULT_GRADE_THRESHOLD = 80.0


@dataclass(frozen=True)
class DuecheckConfig:
    canvas_url: str = ""
    canvas_token: str = ""
    out_dir: str = ""
    course_filter: list[str] = field(default_factory=list)
    grade_threshold: float | None = None
    token_env: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.canvas_url:
            payload["canvas_url"] = self.canvas_url
        if self.canvas_token:
            payload["canvas_token"] = self.canvas_token
        if self.out_dir:
            payload["out_dir"] = self.out_dir
        if self.course_filter:
            payload["course_filter"] = list(self.course_filter)
        if self.grade_threshold is not None:
            payload["grade_threshold"] = self.grade_threshold
        if self.token_env:
            payload["token_env"] = self.token_env
        return payload


@dataclass(frozen=True)
class ConfigSaveResult:
    path: Path
    warnings: list[str]


@dataclass(frozen=True)
class RuntimeSettings:
    canvas_url: str
    token: str
    token_source: str
    token_env_name: str
    out_dir: str
    course_filter: list[str] | None
    grade_threshold: float
    config_path: Path
    config_present: bool
    config: DuecheckConfig | None


def config_path(env: Mapping[str, str] | None = None) -> Path:
    env_map = os.environ if env is None else env
    xdg_home = env_map.get("XDG_CONFIG_HOME")
    if xdg_home:
        base = Path(xdg_home).expanduser()
    else:
        home = env_map.get("HOME")
        base = Path(home).expanduser() / ".config" if home else Path.home() / ".config"
    return base / "duecheck" / "config.json"


def _config_from_mapping(data: Mapping[str, object]) -> DuecheckConfig:
    course_filter = data.get("course_filter", [])
    if course_filter in (None, ""):
        parsed_course_filter: list[str] = []
    elif isinstance(course_filter, list) and all(isinstance(item, str) for item in course_filter):
        parsed_course_filter = [item for item in course_filter if item.strip()]
    else:
        raise RuntimeError("Invalid config: course_filter must be a list of strings")

    raw_grade_threshold = data.get("grade_threshold")
    if raw_grade_threshold in (None, ""):
        grade_threshold = None
    elif isinstance(raw_grade_threshold, (int, float)):
        grade_threshold = float(raw_grade_threshold)
    else:
        raise RuntimeError("Invalid config: grade_threshold must be numeric")

    for key in ("canvas_url", "canvas_token", "out_dir", "token_env"):
        value = data.get(key, "")
        if value in (None, ""):
            continue
        if not isinstance(value, str):
            raise RuntimeError(f"Invalid config: {key} must be a string")

    return DuecheckConfig(
        canvas_url=str(data.get("canvas_url") or ""),
        canvas_token=str(data.get("canvas_token") or ""),
        out_dir=str(data.get("out_dir") or ""),
        course_filter=parsed_course_filter,
        grade_threshold=grade_threshold,
        token_env=str(data.get("token_env") or ""),
    )


def load_config(
    path: Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> DuecheckConfig | None:
    resolved_path = path or config_path(env)
    if not resolved_path.exists():
        return None

    try:
        payload = json.loads(resolved_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to parse config at {resolved_path}") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"Invalid config at {resolved_path}: expected object")
    return _config_from_mapping(payload)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            temp_name = handle.name
        Path(temp_name).replace(path)
    finally:
        if temp_name is not None:
            temp_path = Path(temp_name)
            if temp_path.exists():
                temp_path.unlink()


def _harden_permissions(path: Path, *, platform_name: str | None = None) -> list[str]:
    warnings: list[str] = []
    target_platform = platform_name or os.name
    if target_platform != "posix":
        warnings.append("Config permissions not hardened: POSIX chmod unavailable on this platform.")
        return warnings
    try:
        os.chmod(path, 0o600)
    except OSError as exc:
        warnings.append(f"Config permissions not hardened: {exc}")
    return warnings


def save_config(
    config: DuecheckConfig,
    path: Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    platform_name: str | None = None,
) -> ConfigSaveResult:
    resolved_path = path or config_path(env)
    _atomic_write_text(resolved_path, json.dumps(config.to_dict(), indent=2) + "\n")
    return ConfigSaveResult(
        path=resolved_path,
        warnings=_harden_permissions(resolved_path, platform_name=platform_name),
    )


def _resolve_text(explicit: str | None, env_value: str | None, config_value: str, default: str) -> str:
    if explicit is not None:
        return explicit
    if env_value:
        return env_value
    if config_value:
        return config_value
    return default


def resolve_runtime_settings(
    *,
    canvas_url: str | None,
    canvas_token: str | None,
    token_env: str | None,
    out_dir: str | None,
    course_filter: list[str] | None,
    grade_threshold: float | None,
    env: Mapping[str, str] | None = None,
    path: Path | None = None,
) -> RuntimeSettings:
    env_map = os.environ if env is None else env
    resolved_path = path or config_path(env_map)
    config = load_config(resolved_path, env=env_map)

    resolved_canvas_url = _resolve_text(
        canvas_url,
        env_map.get("CANVAS_URL"),
        config.canvas_url if config is not None else "",
        "",
    )
    resolved_out_dir = _resolve_text(
        out_dir,
        None,
        config.out_dir if config is not None else "",
        ".",
    )
    if course_filter is not None:
        resolved_course_filter = list(course_filter)
    elif config is not None and config.course_filter:
        resolved_course_filter = list(config.course_filter)
    else:
        resolved_course_filter = None
    if grade_threshold is not None:
        resolved_grade_threshold = grade_threshold
    elif config is not None and config.grade_threshold is not None:
        resolved_grade_threshold = config.grade_threshold
    else:
        resolved_grade_threshold = DEFAULT_GRADE_THRESHOLD

    if canvas_token is not None:
        resolved_token_env_name = token_env or (config.token_env if config is not None else "") or DEFAULT_TOKEN_ENV
        resolved_token = canvas_token
        token_source = "explicit.canvas_token" if resolved_token else ""
    elif token_env is not None:
        resolved_token_env_name = token_env
        resolved_token = env_map.get(token_env, "")
        token_source = f"explicit.token_env:{token_env}" if resolved_token else ""
        if not resolved_token and config is not None and config.canvas_token:
            resolved_token = config.canvas_token
            token_source = "config.canvas_token"
    elif env_map.get(DEFAULT_TOKEN_ENV):
        resolved_token_env_name = DEFAULT_TOKEN_ENV
        resolved_token = env_map.get(DEFAULT_TOKEN_ENV, "")
        token_source = f"env:{DEFAULT_TOKEN_ENV}"
    elif config is not None and config.token_env and env_map.get(config.token_env):
        resolved_token_env_name = config.token_env
        resolved_token = env_map.get(config.token_env, "")
        token_source = f"config.token_env:{config.token_env}"
    elif config is not None and config.canvas_token:
        resolved_token_env_name = config.token_env or DEFAULT_TOKEN_ENV
        resolved_token = config.canvas_token
        token_source = "config.canvas_token"
    else:
        resolved_token_env_name = token_env or (config.token_env if config is not None else "") or DEFAULT_TOKEN_ENV
        resolved_token = ""
        token_source = ""

    return RuntimeSettings(
        canvas_url=resolved_canvas_url,
        token=resolved_token,
        token_source=token_source,
        token_env_name=resolved_token_env_name,
        out_dir=resolved_out_dir,
        course_filter=resolved_course_filter,
        grade_threshold=float(resolved_grade_threshold),
        config_path=resolved_path,
        config_present=config is not None,
        config=config,
    )
