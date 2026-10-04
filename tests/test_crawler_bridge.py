from __future__ import annotations

import json
import os
import sqlite3
import stat
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from crawler_bridge.adapters import account_capabilities, import_mediacrawler_output, source_dir
from crawler_bridge.ai import LeadAnalysisError, analyze_lead
from crawler_bridge.leads import hint_for_comment
from crawler_bridge.model_config import ModelConfigError, update_model_config
from crawler_bridge.normalize import comment
from crawler_bridge.store import Store


_SERVER_TEST_DATA = tempfile.TemporaryDirectory()
with mock.patch.dict(os.environ, {"CRAWLER_DB_PATH": str(Path(_SERVER_TEST_DATA.name) / "crawler.sqlite3")}):
    from crawler_bridge import server
    from crawler_bridge.server import Handler


class CrawlerBridgeTests(unittest.TestCase):
    def test_account_capabilities_endpoint_redacts_cookies(self) -> None:
        dy_cookie = "dy-cookie-value-should-never-be-returned"
        xhs_cookie = "xhs-cookie-value-should-never-be-returned"
        deepseek_key = "deepseek-key-value-should-never-be-returned"
        with mock.patch.dict(os.environ, {
            "DOUYIN_ACCOUNT_COOKIE": dy_cookie,
            "XHS_ACCOUNT_COOKIE": xhs_cookie,
            "DEEPSEEK_API_KEY": deepseek_key,
            "DEEPSEEK_MODEL": "deepseek-flash",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        }, clear=True):
            expected = {
                "accounts": {"dy": True, "xhs": True},
                "providers": {"deepseek": {"configured": True, "model": "deepseek-flash", "base_url": "https://api.deepseek.com"}},
            }
            capabilities = account_capabilities()
            self.assertEqual(capabilities, expected)
            self.assertTrue(all(type(value) is bool for value in capabilities["accounts"].values()))

            sent: list[tuple[int, dict | list]] = []
            handler = object.__new__(Handler)
            handler.path = "/api/integrations/capabilities"
            handler._send = lambda status, payload: sent.append((status, payload))
            handler.do_GET()

            self.assertEqual(sent, [(200, expected)])
            serialized = json.dumps(sent[0][1], ensure_ascii=False)
            self.assertNotIn(dy_cookie, serialized)
            self.assertNotIn(xhs_cookie, serialized)
            self.assertNotIn("DOUYIN_ACCOUNT_COOKIE", serialized)
            self.assertNotIn("XHS_ACCOUNT_COOKIE", serialized)
            self.assertNotIn(deepseek_key, serialized)
            self.assertNotIn("DEEPSEEK_API_KEY", serialized)

    def test_account_capabilities_reports_missing_cookie_as_false(self) -> None:
        with mock.patch.dict(os.environ, {
            "DOUYIN_ACCOUNT_COOKIE": "configured-for-test",
            "XHS_ACCOUNT_COOKIE": "",
            "DEEPSEEK_API_KEY": "",
            "DEEPSEEK_MODEL": "deepseek-flash",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        }, clear=True):
            self.assertEqual(account_capabilities(), {
                "accounts": {"dy": True, "xhs": False},
                "providers": {"deepseek": {"configured": False, "model": "deepseek-flash", "base_url": "https://api.deepseek.com"}},
            })

    def test_model_configuration_persists_only_locally_and_never_returns_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env.local"
            env_path.write_text("XHS_ACCOUNT_COOKIE='keep-this-cookie'\nOTHER_SETTING=preserved\n", encoding="utf-8")
            secret = "sk-test-key-that-must-not-be-returned"
            with mock.patch.dict(os.environ, {
                "CRAWLER_ENV_PATH": str(env_path), "DEEPSEEK_API_KEY": "",
                "DEEPSEEK_MODEL": "", "DEEPSEEK_BASE_URL": "",
            }, clear=False):
                saved = update_model_config({
                    "api_key": secret, "model": "deepseek-chat", "base_url": "https://api.deepseek.com/v1",
                    "clear_api_key": False,
                })
                self.assertEqual(saved, {"configured": True, "model": "deepseek-chat", "base_url": "https://api.deepseek.com/v1"})
                self.assertNotIn(secret, json.dumps(saved))
                contents = env_path.read_text(encoding="utf-8")
                self.assertIn("XHS_ACCOUNT_COOKIE='keep-this-cookie'", contents)
                self.assertIn("OTHER_SETTING=preserved", contents)
                self.assertIn("DEEPSEEK_API_KEY=sk-test-key-that-must-not-be-returned", contents)
                self.assertEqual(stat.S_IMODE(env_path.stat().st_mode), 0o600)

                cleared = update_model_config({
                    "model": "deepseek-chat", "base_url": "https://api.deepseek.com/v1", "clear_api_key": True,
                })
                self.assertFalse(cleared["configured"])
                self.assertIn("DEEPSEEK_API_KEY=''", env_path.read_text(encoding="utf-8"))

            with self.assertRaises(ModelConfigError):
                update_model_config({"model": "deepseek chat", "base_url": "http://localhost:8000"})

    def test_model_configuration_endpoint_does_not_echo_key(self) -> None:
        secret = "sk-never-echo-this"
        sent: list[tuple[int, dict | list]] = []
        handler = object.__new__(Handler)
        handler.path = "/api/integrations/model"
        handler._body = lambda: {"api_key": secret, "model": "deepseek-chat", "base_url": "https://api.deepseek.com"}
        handler._send = lambda status, payload: sent.append((status, payload))
        expected = {"configured": True, "model": "deepseek-chat", "base_url": "https://api.deepseek.com"}
        with mock.patch("crawler_bridge.server.update_model_config", return_value=expected) as update:
            handler.do_PUT()
        self.assertEqual(sent, [(200, expected)])
        self.assertEqual(update.call_args.args[0]["api_key"], secret)
        self.assertNotIn(secret, json.dumps(sent[0][1]))

    def test_deepseek_analysis_uses_server_key_and_validates_json(self) -> None:
        response_json = json.dumps({"choices": [{"message": {"content": json.dumps({
            "summary": "对价格与方案有明确咨询。", "intent_assessment": "有采购评估信号。",
            "confidence": "high", "recommended_action": "人工核实需求范围。",
            "follow_up_message": "如已核实联系方式，可进一步确认预算和时间安排。",
            "skill_name": "预算与需求核实", "skill_instructions": "先确认场景、预算和决策时间，再提供匹配方案。",
        }, ensure_ascii=False)}}]}).encode("utf-8")

        class Response:
            def read(self) -> bytes:
                return response_json

            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key", "DEEPSEEK_MODEL": "deepseek-flash"}), \
             mock.patch("crawler_bridge.ai.urlopen", return_value=Response()) as request_call:
            model, analysis = analyze_lead(
                {"platform": "xhs", "keyword": "AI", "level": "A", "score": 85, "reason": "询价"},
                [{"body": "多少钱，怎么报名？"}],
            )
        request = request_call.call_args.args[0]
        self.assertEqual(model, "deepseek-flash")
        self.assertEqual(analysis["confidence"], "high")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertNotIn("test-key", request.data.decode("utf-8"))

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            with self.assertRaises(LeadAnalysisError):
                analyze_lead({"platform": "xhs", "keyword": "AI", "level": "A", "score": 85, "reason": "询价"}, [])

    def test_retry_keeps_the_original_collection_settings(self) -> None:
        original_id = str(uuid.uuid4())
        server.STORE.create_job(original_id, "mediacrawler", "xhs", "fde", max_items=20, max_comments=6)
        server.STORE.update_job(original_id, "failed", error="采集失败")
        with mock.patch.object(server.threading, "Thread") as thread:
            retried = server.retry_job(original_id)
        new_job = server.STORE.job(retried["id"])
        self.assertEqual(retried["retried_from"], original_id)
        self.assertEqual((new_job["platform"], new_job["keyword"], new_job["max_items"], new_job["max_comments"]),
                         ("xhs", "fde", 20, 6))
        thread.return_value.start.assert_called_once_with()

    def test_legacy_xhs_job_gets_a_retryable_default_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.sqlite3"
            with sqlite3.connect(path) as db:
                db.execute("""CREATE TABLE jobs (
                    id TEXT PRIMARY KEY, adapter TEXT NOT NULL, platform TEXT NOT NULL,
                    keyword TEXT NOT NULL, state TEXT NOT NULL, error TEXT,
                    items_count INTEGER NOT NULL DEFAULT 0, comments_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )""")
                db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
                           ("legacy", "mediacrawler", "xhs", "AI", "failed", None, 0, 0, "now", "now"))
            store = Store(path)
            self.assertEqual((store.job("legacy")["max_items"], store.job("legacy")["max_comments"]), (20, 10))

    def test_media_export_is_normalized_and_idempotent_per_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = root / "douyin" / "jsonl"
            files.mkdir(parents=True)
            (files / "search_contents_2026.jsonl").write_text(
                json.dumps({"aweme_id": "video-1", "title": "AI转型", "desc": "简介", "source_keyword": "AI", "time": 1750000000000}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (files / "search_comments_2026.jsonl").write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in [
                    {"comment_id": "comment-1", "aweme_id": "video-1", "content": "求机构", "nickname": "甲"},
                    {"comment_id": "comment-1", "aweme_id": "video-1", "content": "求机构", "nickname": "甲"},
                    {"comment_id": "", "aweme_id": "video-1", "content": "无稳定ID"},
                ]) + "\n", encoding="utf-8")
            store = Store(root / "test.sqlite3")
            first = str(uuid.uuid4())
            second = str(uuid.uuid4())
            store.create_job(first, "mediacrawler_import", "dy", "AI")
            store.create_job(second, "mediacrawler_import", "dy", "AI")
            self.assertEqual(import_mediacrawler_output(store, first, "dy", root), (1, 1))
            self.assertEqual(import_mediacrawler_output(store, second, "dy", root), (1, 1))
            self.assertEqual(len(store.results(first)["items"]), 1)
            self.assertEqual(len(store.results(second)["comments"]), 1)
            self.assertEqual(store.results(first)["comments"][0]["body"], "求机构")
            self.assertEqual(store.results(first)["comments"][0]["identity_kind"], "anonymous_hash")

    def test_xhs_media_export_and_bundled_source(self) -> None:
        self.assertTrue((source_dir() / "media_platform" / "douyin" / "core.py").is_file())
        self.assertTrue((source_dir() / "LICENSE").is_file())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = root / "xhs" / "jsonl"
            files.mkdir(parents=True)
            (files / "search_contents_2026.jsonl").write_text(json.dumps({"note_id": "note-1", "title": "标题", "desc": "正文", "creator_hash": "hash-1", "note_url": "https://www.xiaohongshu.com/explore/note-1?xsec_token=secret"}, ensure_ascii=False) + "\n", encoding="utf-8")
            (files / "search_comments_2026.jsonl").write_text(json.dumps({"comment_id": "comment-1", "note_id": "note-1", "creator_hash": "hash-2", "content": "价格多少"}, ensure_ascii=False) + "\n", encoding="utf-8")
            store = Store(root / "test.sqlite3")
            job = str(uuid.uuid4())
            store.create_job(job, "mediacrawler_import", "xhs", "AI")
            self.assertEqual(import_mediacrawler_output(store, job, "xhs", root), (1, 1))
            result = store.results(job)
            self.assertEqual(result["items"][0]["identity_kind"], "anonymous_hash")
            self.assertEqual(result["items"][0]["url"], "https://www.xiaohongshu.com/explore/note-1")
            self.assertEqual(result["comments"][0]["author_id"], "hash-2")
        self.assertIsNone(comment("xhs", {"content": "无ID"}, "MediaCrawler", "note-1"))

    def test_recover_marks_nonterminal_jobs_interrupted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "test.sqlite3")
            job = str(uuid.uuid4())
            store.create_job(job, "mediacrawler", "xhs", "AI")
            store.update_job(job, "running")
            store.recover_interrupted()
            self.assertEqual(store.job(job)["state"], "interrupted")

    def test_comment_to_lead_to_customer_is_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "test.sqlite3")
            job = str(uuid.uuid4())
            store.create_job(job, "mediacrawler_import", "xhs", "AI转型")
            store.upsert("items", {"platform": "xhs", "external_id": "note-1", "title": "标题", "body": "正文", "author_id": None,
                                   "identity_kind": "anonymous_hash", "url": "https://www.xiaohongshu.com/explore/note-1", "published_at": None,
                                   "keyword": "AI转型", "source": "MediaCrawler"}, job)
            first = {"platform": "xhs", "external_id": "c1", "item_id": "note-1", "author_id": "hash-1",
                     "identity_kind": "anonymous_hash", "nickname": "张*", "body": "请问多少钱", "published_at": None, "source": "MediaCrawler"}
            second = {**first, "external_id": "c2", "body": "想了解一下"}
            store.upsert("comments", first, job)
            store.upsert("comments", second, job)
            store.upsert("comments", first, job)
            leads = store.leads()
            self.assertEqual(len(leads), 1)
            self.assertEqual((leads[0]["score"], leads[0]["evidence_count"], leads[0]["keyword"]), (85, 2, "AI转型"))
            lead_id = leads[0]["id"]
            saved = store.save_lead_analysis(lead_id, "deepseek-flash", {
                "summary": "有明确咨询信号。", "intent_assessment": "需要进一步核实。", "confidence": "medium",
                "recommended_action": "人工确认需求。", "follow_up_message": "如已核实联系方式，可确认需求。",
                "skill_name": "需求核实", "skill_instructions": "确认场景与时间。",
            })
            self.assertEqual(saved["ai_analysis"]["model"], "deepseek-flash")
            self.assertEqual(len(store.lead_evidence(lead_id)), 2)
            self.assertEqual(store.review_lead(lead_id, "reviewed")["review_state"], "reviewed")
            customer = store.create_customer({"name": "已核实客户", "need": "咨询价格"}, lead_id)
            again = store.create_customer({"name": "重复点击"}, lead_id)
            self.assertEqual(customer["id"], again["id"])
            self.assertEqual(len(store.customers()), 1)
            updated = store.update_customer(customer["id"], {"status": "following", "phone": "13800000000"})
            self.assertEqual(updated["status"], "following")
            self.assertEqual(len(updated["events"]), 2)
            self.assertNotIn("13800000000", updated["events"][0]["detail"])
            analytics = store.analytics(7)
            self.assertEqual((analytics["leads"], analytics["high_intent"], analytics["customers"]), (1, 1, 1))

    def test_rules_do_not_promote_ads_or_negation(self) -> None:
        self.assertIsNone(hint_for_comment("不需要，多少钱也不买"))
        self.assertIsNone(hint_for_comment("私信我，招代理"))
        self.assertEqual(hint_for_comment("有没有适合小公司的方案").level, "B")


if __name__ == "__main__":
    unittest.main()
