"""Loopback-only JSON API for the Next.js local development frontend."""

from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .adapters import DATA, BridgeError, account_capabilities, run_mediacrawler
from .ai import LeadAnalysisError, analyze_lead
from .model_config import ModelConfigError, public_model_config, update_model_config
from .store import Store


sys.dont_write_bytecode = True
DB_PATH = Path(os.environ.get("CRAWLER_DB_PATH", str(DATA / "crawler.sqlite3"))).resolve()
STORE = Store(DB_PATH)
STORE.recover_interrupted()
RUN_LOCK = threading.Lock()
ANALYSIS_LOCK = threading.Lock()


def _job(job_id: str, adapter: str, platform: str, keyword: str, max_items: int, max_comments: int) -> None:
    with RUN_LOCK:
        STORE.update_job(job_id, "running")
        try:
            items_count, comments_count = run_mediacrawler(
                STORE, job_id, platform, keyword, max_items, max_comments)
            STORE.update_job(job_id, "succeeded", items_count=items_count,
                             comments_count=comments_count)
        except BridgeError as exc:
            STORE.update_job(job_id, "failed", error=str(exc))
        except Exception as exc:
            STORE.update_job(job_id, "failed", error=f"采集器运行失败：{type(exc).__name__}；请检查依赖与本地日志")


def queue_job(adapter: str, platform: str, keyword: str, max_items: int, max_comments: int,
              *, retried_from: str | None = None) -> dict:
    job_id = str(uuid.uuid4())
    STORE.create_job(job_id, adapter, platform, keyword, max_items=max_items,
                     max_comments=max_comments)
    threading.Thread(target=_job, args=(job_id, adapter, platform, keyword, max_items, max_comments), daemon=True).start()
    result = {"id": job_id, "state": "queued"}
    if retried_from:
        result["retried_from"] = retried_from
    return result


def retry_job(job_id: str) -> dict:
    original = STORE.job(job_id)
    if original is None:
        raise LookupError("任务不存在")
    if original["adapter"] != "mediacrawler":
        raise ValueError("当前任务不支持重试")
    if original["state"] not in ("failed", "interrupted"):
        raise ValueError("仅失败或已中断的任务可重试")
    return queue_job(original["adapter"], original["platform"], original["keyword"],
                     original["max_items"], original["max_comments"], retried_from=job_id)


def analyze_saved_lead(lead_id: str) -> dict:
    """Run a user-triggered provider request and persist only the returned analysis."""
    with ANALYSIS_LOCK:
        lead = STORE.lead(lead_id)
        if lead is None:
            raise LookupError("潜客不存在")
        evidence = STORE.lead_evidence(lead_id)
        if not evidence:
            raise ValueError("该潜客没有可分析的评论证据")
        model, analysis = analyze_lead(lead, evidence)
        return STORE.save_lead_analysis(lead_id, model, analysis)


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict | list) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/health":
            self._send(200, {"ok": True, "adapters": ["mediacrawler"], "platforms": ["dy", "xhs"]})
        elif path == "/api/integrations/capabilities":
            self._send(200, account_capabilities())
        elif path == "/api/integrations/model":
            self._send(200, public_model_config())
        elif path == "/api/jobs":
            self._send(200, {"jobs": STORE.jobs()})
        elif path.startswith("/api/jobs/"):
            job_id = path.removeprefix("/api/jobs/")
            if not _valid_uuid(job_id):
                self._send(400, {"error": "无效任务 ID"})
                return
            result = STORE.results(job_id)
            self._send(200 if result else 404, result or {"error": "任务不存在"})
        elif path == "/api/leads":
            self._send(200, {"leads": STORE.leads(q=query.get("q", [""])[0][:100],
                                                   level=query.get("level", [""])[0],
                                                   review_state=query.get("state", [""])[0])})
        elif path == "/api/customers":
            self._send(200, {"customers": STORE.customers(q=query.get("q", [""])[0][:100],
                                                           status=query.get("status", [""])[0])})
        elif path.startswith("/api/customers/"):
            customer_id = path.removeprefix("/api/customers/")
            result = STORE.customer(customer_id) if _valid_uuid(customer_id) else None
            self._send(200 if result else 404, result or {"error": "客户不存在"})
        elif path == "/api/analytics/lead":
            try:
                days = int(query.get("days", ["30"])[0])
                if days not in (7, 30, 90):
                    raise ValueError
            except ValueError:
                self._send(400, {"error": "统计周期仅支持 7、30 或 90 天"})
                return
            self._send(200, STORE.analytics(days))
        else:
            self._send(404, {"error": "接口不存在"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/leads/") and path.endswith("/analysis"):
            lead_id = path.removeprefix("/api/leads/").removesuffix("/analysis")
            if not _valid_uuid(lead_id):
                self._send(400, {"error": "无效潜客 ID"})
                return
            try:
                self._send(200, {"lead": analyze_saved_lead(lead_id)})
            except LookupError as exc:
                self._send(404, {"error": str(exc)})
            except (LeadAnalysisError, ValueError) as exc:
                self._send(400, {"error": str(exc)})
            return
        if path == "/api/customers" or path.startswith("/api/leads/") and path.endswith("/convert"):
            try:
                payload = self._body()
                fields = _customer_fields(payload)
                lead_id = path.removeprefix("/api/leads/").removesuffix("/convert") if path != "/api/customers" else None
                if lead_id and not _valid_uuid(lead_id):
                    raise ValueError("无效潜客 ID")
                customer = STORE.create_customer(fields, lead_id)
                self._send(201, customer)
            except LookupError as exc:
                self._send(404, {"error": str(exc)})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._send(400, {"error": str(exc)})
            return
        if path.startswith("/api/jobs/") and path.endswith("/retry"):
            job_id = path.removeprefix("/api/jobs/").removesuffix("/retry")
            if not _valid_uuid(job_id):
                self._send(400, {"error": "无效任务 ID"})
                return
            try:
                self._send(202, retry_job(job_id))
            except LookupError as exc:
                self._send(404, {"error": str(exc)})
            except ValueError as exc:
                self._send(409, {"error": str(exc)})
            return
        if path != "/api/jobs":
            self._send(404, {"error": "接口不存在"})
            return
        try:
            payload = self._body()
            adapter = payload.get("adapter")
            platform = payload.get("platform")
            keyword = payload.get("keyword")
            if adapter != "mediacrawler":
                raise ValueError("不支持的采集器")
            if platform not in ("dy", "xhs"):
                raise ValueError("不支持的平台组合")
            if not isinstance(keyword, str) or not 1 <= len(keyword.strip()) <= 80:
                raise ValueError("关键词长度须为 1–80 个字符")
            if any(c in keyword for c in "\x00\r\n"):
                raise ValueError("关键词包含非法字符")
            max_items = int(payload.get("max_items", 10))
            max_comments = int(payload.get("max_comments", 10))
            minimum = 10 if platform == "dy" else 20
            if not minimum <= max_items <= 20 or not 0 <= max_comments <= 30:
                raise ValueError(f"该采集器素材上限须为 {minimum}–20；每条评论上限为 0–30")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})
            return
        self._send(202, queue_job(adapter, platform, keyword.strip(), max_items, max_comments))

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._body()
            if path.startswith("/api/leads/"):
                lead_id = path.removeprefix("/api/leads/")
                if not _valid_uuid(lead_id):
                    raise ValueError("无效潜客 ID")
                result = STORE.review_lead(lead_id, payload.get("state", ""))
                self._send(200 if result else 404, result or {"error": "潜客不存在"})
            elif path.startswith("/api/customers/"):
                customer_id = path.removeprefix("/api/customers/")
                if not _valid_uuid(customer_id):
                    raise ValueError("无效客户 ID")
                fields = _customer_fields(payload, partial=True)
                result = STORE.update_customer(customer_id, fields)
                self._send(200 if result else 404, result or {"error": "客户不存在"})
            else:
                self._send(404, {"error": "接口不存在"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/integrations/model":
            self._send(404, {"error": "接口不存在"})
            return
        try:
            self._send(200, update_model_config(self._body()))
        except (ModelConfigError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 2 or length > 8192:
            raise ValueError("请求体过大或为空")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("请求格式错误")
        return payload

    def log_message(self, format: str, *args) -> None:
        # Avoid logging request content or account credentials.
        return


def _valid_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _customer_fields(payload: dict, *, partial: bool = False) -> dict:
    fields = {}
    limits = {"name": 100, "company": 100, "phone": 40, "need": 1000,
              "source_platform": 20, "status": 20, "follow_up_at": 40}
    for key, limit in limits.items():
        if key not in payload:
            continue
        value = payload[key]
        if value is None and key == "follow_up_at":
            fields[key] = None
            continue
        if not isinstance(value, str) or len(value.strip()) > limit or any(c in value for c in "\x00\r"):
            raise ValueError(f"{key} 格式无效")
        fields[key] = value.strip()
    if not partial and not fields.get("name"):
        raise ValueError("客户名称不能为空")
    if partial and "name" in fields and not fields["name"]:
        raise ValueError("客户名称不能为空")
    if "status" in fields and fields["status"] not in ("new", "following", "nurturing", "won", "lost"):
        raise ValueError("无效客户状态")
    if "source_platform" in fields and fields["source_platform"] not in ("", "dy", "xhs", "manual"):
        raise ValueError("无效客户来源")
    if "follow_up_at" in fields and fields["follow_up_at"]:
        try:
            datetime.fromisoformat(fields["follow_up_at"])
        except ValueError as exc:
            raise ValueError("跟进时间格式无效") from exc
    return fields


def main() -> None:
    host = os.environ.get("CRAWLER_HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit("采集服务仅允许绑定回环地址")
    port = int(os.environ.get("CRAWLER_PORT", "8765"))
    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError as exc:
        if exc.errno in (48, 98):  # 端口已占用（macOS 48 / Linux 98）
            raise SystemExit(
                f"端口 {port} 已被占用：可能已有一个采集服务在运行。\n"
                f"先检查是否可用：curl --noproxy '*' http://{host}:{port}/health\n"
                f"若需重启，先结束旧进程：lsof -ti tcp:{port} | xargs kill"
            ) from exc
        raise
    print(f"Crawler bridge listening on http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
