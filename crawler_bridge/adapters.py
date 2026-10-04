"""Run the bundled MediaCrawler subset and import its JSONL output."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .model_config import public_model_config
from .normalize import comment, item
from .store import Store


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / ".local-data"


class BridgeError(Exception):
    """A message written by this project that is safe to show in the UI."""


def account_capabilities() -> dict[str, object]:
    """Report local configuration status without exposing credentials."""
    return {
        "accounts": {
            "dy": bool(os.environ.get("DOUYIN_ACCOUNT_COOKIE", "")),
            "xhs": bool(os.environ.get("XHS_ACCOUNT_COOKIE", "")),
        },
        "providers": {"deepseek": public_model_config()},
    }


def account_cookie(platform: str) -> str:
    name = "DOUYIN_ACCOUNT_COOKIE" if platform == "dy" else "XHS_ACCOUNT_COOKIE"
    value = os.environ.get(name, "")
    if not value:
        raise BridgeError(f"未配置 {name}；不自动登录或读取浏览器凭据")
    return value


def source_dir() -> Path:
    path = ROOT / "vendor" / "mediacrawler"
    if not (path / "media_platform" / "xhs" / "core.py").is_file() or not (path / "media_platform" / "douyin" / "core.py").is_file():
        raise BridgeError("项目内 MediaCrawler 组件不完整")
    return path


def _read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BridgeError(f"{path.name}:{line_number} JSONL 格式错误") from exc
            if isinstance(value, dict):
                yield value


def import_mediacrawler_output(store: Store, job_id: str, platform: str, folder: Path) -> tuple[int, int]:
    """Normalize just the job's JSONL artifacts; repeated IDs are idempotent."""
    items_seen: set[str] = set()
    comments_seen: set[str] = set()
    platform_folder = folder / ("douyin" if platform == "dy" else "xhs") / "jsonl"
    for file in sorted(platform_folder.glob("search_contents_*.jsonl")):
        for raw in _read_jsonl(file):
            record = item(platform, raw, "MediaCrawler")
            if record:
                store.upsert("items", record, job_id)
                items_seen.add(record["external_id"])
    for file in sorted(platform_folder.glob("search_comments_*.jsonl")):
        for raw in _read_jsonl(file):
            record = comment(platform, raw, "MediaCrawler")
            if record:
                store.upsert("comments", record, job_id)
                comments_seen.add(record["external_id"])
    return len(items_seen), len(comments_seen)


def run_mediacrawler(store: Store, job_id: str, platform: str, keyword: str,
                     max_items: int, max_comments: int) -> tuple[int, int]:
    source = source_dir()
    cookie = account_cookie(platform)
    folder = DATA / "runs" / job_id
    folder.mkdir(parents=True, exist_ok=True)
    log_file = folder / "source.log"
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "BRIDGE_SOURCE_PATH": str(source),
           "BRIDGE_RUN_PATH": str(folder), "BRIDGE_PLATFORM": platform,
           "BRIDGE_KEYWORD": keyword, "BRIDGE_MAX_ITEMS": str(max_items),
           "BRIDGE_MAX_COMMENTS": str(max_comments), "CRAWLER_ACCOUNT_COOKIE": cookie}
    interpreter = os.environ.get("MEDIACRAWLER_PYTHON", sys.executable)
    if not Path(interpreter).is_file():
        raise BridgeError("MEDIACRAWLER_PYTHON 不是有效 Python 路径")
    with log_file.open("w", encoding="utf-8") as log:
        try:
            result = subprocess.run(
                [interpreter, str(ROOT / "scripts" / "run_mediacrawler.py")],
                cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT,
                timeout=600, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise BridgeError("MediaCrawler 运行超过 10 分钟，已停止；检查本地日志") from exc
    counts = import_mediacrawler_output(store, job_id, platform, folder)
    if result.returncode != 0:
        raise BridgeError("MediaCrawler 执行失败；已保留可用数据，请检查本地运行日志")
    return counts
