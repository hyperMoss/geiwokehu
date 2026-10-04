"""Small SQLite persistence for local crawler jobs and normalized evidence."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from .leads import hint_for_comment


def now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY, adapter TEXT NOT NULL, platform TEXT NOT NULL,
                  keyword TEXT NOT NULL, max_items INTEGER NOT NULL,
                  max_comments INTEGER NOT NULL, state TEXT NOT NULL, error TEXT,
                  items_count INTEGER NOT NULL DEFAULT 0,
                  comments_count INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS items (
                  platform TEXT NOT NULL, external_id TEXT NOT NULL,
                  title TEXT NOT NULL, body TEXT NOT NULL, author_id TEXT,
                  identity_kind TEXT NOT NULL,
                  url TEXT NOT NULL, published_at TEXT, keyword TEXT NOT NULL,
                  source TEXT NOT NULL, updated_at TEXT NOT NULL,
                  PRIMARY KEY (platform, external_id)
                );
                CREATE TABLE IF NOT EXISTS comments (
                  platform TEXT NOT NULL, external_id TEXT NOT NULL,
                  item_id TEXT NOT NULL, author_id TEXT, identity_kind TEXT NOT NULL,
                  nickname TEXT NOT NULL,
                  body TEXT NOT NULL, published_at TEXT, source TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  PRIMARY KEY (platform, external_id)
                );
                CREATE TABLE IF NOT EXISTS job_items (
                  job_id TEXT NOT NULL REFERENCES jobs(id), platform TEXT NOT NULL,
                  external_id TEXT NOT NULL, PRIMARY KEY(job_id,platform,external_id)
                );
                CREATE TABLE IF NOT EXISTS job_comments (
                  job_id TEXT NOT NULL REFERENCES jobs(id), platform TEXT NOT NULL,
                  external_id TEXT NOT NULL, PRIMARY KEY(job_id,platform,external_id)
                );
                CREATE INDEX IF NOT EXISTS ix_items_updated ON items(updated_at DESC);
                CREATE INDEX IF NOT EXISTS ix_comments_item ON comments(platform, item_id);
                CREATE INDEX IF NOT EXISTS ix_comments_author ON comments(platform, author_id);
                CREATE TABLE IF NOT EXISTS leads (
                  id TEXT PRIMARY KEY, platform TEXT NOT NULL, identity_key TEXT NOT NULL,
                  nickname TEXT NOT NULL, keyword TEXT NOT NULL DEFAULT '',
                  score INTEGER NOT NULL, level TEXT NOT NULL, reason TEXT NOT NULL,
                  evidence_count INTEGER NOT NULL, latest_comment_id TEXT NOT NULL,
                  latest_body TEXT NOT NULL, review_state TEXT NOT NULL DEFAULT 'new',
                  customer_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                  UNIQUE(platform, identity_key)
                );
                CREATE INDEX IF NOT EXISTS ix_leads_score ON leads(score DESC, updated_at DESC);
                CREATE TABLE IF NOT EXISTS lead_analyses (
                  lead_id TEXT PRIMARY KEY REFERENCES leads(id), model TEXT NOT NULL,
                  summary TEXT NOT NULL, intent_assessment TEXT NOT NULL,
                  confidence TEXT NOT NULL, recommended_action TEXT NOT NULL,
                  follow_up_message TEXT NOT NULL, skill_name TEXT NOT NULL,
                  skill_instructions TEXT NOT NULL, created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS customers (
                  id TEXT PRIMARY KEY, name TEXT NOT NULL, company TEXT NOT NULL DEFAULT '',
                  phone TEXT NOT NULL DEFAULT '', need TEXT NOT NULL DEFAULT '',
                  source_platform TEXT NOT NULL DEFAULT '', source_lead_id TEXT UNIQUE,
                  status TEXT NOT NULL DEFAULT 'new', follow_up_at TEXT,
                  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS customer_events (
                  id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
                  kind TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_customer_events ON customer_events(customer_id, created_at DESC);
            """)
            self._migrate_jobs(db)
            # Existing imports predate the leads table. Rebuild the derived candidates
            # without changing saved comments or any manually reviewed lead.
            rows = db.execute("SELECT * FROM comments ORDER BY updated_at").fetchall()
            keys = {(row["platform"], row["author_id"] or "comment:" + row["external_id"]) for row in rows}
            for platform, identity_key in keys:
                self._refresh_lead(db, platform, identity_key)

    @staticmethod
    def _migrate_jobs(db: sqlite3.Connection) -> None:
        """Add replay settings for databases created before task retry existed."""
        columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
        if "max_items" not in columns:
            db.execute("ALTER TABLE jobs ADD COLUMN max_items INTEGER")
        if "max_comments" not in columns:
            db.execute("ALTER TABLE jobs ADD COLUMN max_comments INTEGER")
        db.execute("UPDATE jobs SET max_items=CASE WHEN platform='xhs' THEN 20 ELSE 10 END WHERE max_items IS NULL")
        db.execute("UPDATE jobs SET max_comments=10 WHERE max_comments IS NULL")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _refresh_lead(self, db: sqlite3.Connection, platform: str, identity_key: str) -> None:
        if identity_key.startswith("comment:"):
            rows = db.execute("SELECT * FROM comments WHERE platform=? AND external_id=?",
                              (platform, identity_key.removeprefix("comment:"))).fetchall()
        else:
            rows = db.execute("SELECT * FROM comments WHERE platform=? AND author_id=?",
                              (platform, identity_key)).fetchall()
        qualified = [(row, hint_for_comment(row["body"])) for row in rows]
        qualified = [(row, hint) for row, hint in qualified if hint]
        existing = db.execute("SELECT id, customer_id FROM leads WHERE platform=? AND identity_key=?",
                              (platform, identity_key)).fetchone()
        if not qualified:
            if existing and not existing["customer_id"]:
                db.execute("DELETE FROM leads WHERE id=?", (existing["id"],))
            return
        best, hint = max(qualified, key=lambda pair: (pair[1].score, pair[0]["updated_at"]))
        assert hint is not None
        context = db.execute("SELECT keyword FROM items WHERE platform=? AND external_id=?",
                             (platform, best["item_id"])).fetchone()
        stamp = now()
        db.execute("""
            INSERT INTO leads(id,platform,identity_key,nickname,keyword,score,level,reason,
                              evidence_count,latest_comment_id,latest_body,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(platform,identity_key) DO UPDATE SET
              nickname=excluded.nickname, keyword=excluded.keyword, score=excluded.score,
              level=excluded.level, reason=excluded.reason, evidence_count=excluded.evidence_count,
              latest_comment_id=excluded.latest_comment_id, latest_body=excluded.latest_body,
              updated_at=excluded.updated_at
        """, (existing["id"] if existing else str(uuid.uuid4()), platform, identity_key,
              best["nickname"] or "匿名用户", context["keyword"] if context else "",
              hint.score, hint.level, hint.reason, len(qualified), best["external_id"],
              best["body"], stamp, stamp))

    def create_job(self, job_id: str, adapter: str, platform: str, keyword: str,
                   *, max_items: int | None = None, max_comments: int | None = None) -> None:
        if max_items is None:
            max_items = 20 if platform == "xhs" else 10
        if max_comments is None:
            max_comments = 10
        with self._conn() as db:
            db.execute("""INSERT INTO jobs(id,adapter,platform,keyword,max_items,max_comments,state,created_at,updated_at)
                          VALUES(?,?,?,?,?,?,?,?,?)""",
                       (job_id, adapter, platform, keyword, max_items, max_comments,
                        "queued", now(), now()))

    def update_job(self, job_id: str, state: str, *, error: str | None = None,
                   items_count: int | None = None, comments_count: int | None = None) -> None:
        fields = ["state=?", "updated_at=?", "error=?"]
        args: list[Any] = [state, now(), error]
        if items_count is not None:
            fields.append("items_count=?")
            args.append(items_count)
        if comments_count is not None:
            fields.append("comments_count=?")
            args.append(comments_count)
        args.append(job_id)
        with self._conn() as db:
            db.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id=?", args)

    def upsert(self, table: str, record: dict[str, Any], job_id: str | None = None) -> None:
        if table not in ("items", "comments"):
            raise ValueError("invalid record type")
        fields = [*record, "updated_at"]
        values = [*record.values(), now()]
        updates = ", ".join(f"{key}=excluded.{key}" for key in record if key not in ("platform", "external_id"))
        statement = (f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)}) "
                     f"ON CONFLICT(platform,external_id) DO UPDATE SET {updates}, updated_at=excluded.updated_at")
        with self._conn() as db:
            db.execute(statement, values)
            if table == "comments":
                self._refresh_lead(db, record["platform"], record.get("author_id") or "comment:" + record["external_id"])
            if job_id:
                membership = "job_items" if table == "items" else "job_comments"
                db.execute(f"INSERT OR IGNORE INTO {membership}(job_id,platform,external_id) VALUES(?,?,?)",
                           (job_id, record["platform"], record["external_id"]))

    def recover_interrupted(self) -> None:
        with self._conn() as db:
            db.execute("UPDATE jobs SET state='interrupted', updated_at=?, error='服务重启中断任务，请新建任务重试' WHERE state IN ('queued','running')", (now(),))

    def job(self, job_id: str) -> dict[str, Any] | None:
        with self._conn() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def jobs(self) -> list[dict[str, Any]]:
        with self._conn() as db:
            return [dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 50")]

    def results(self, job_id: str) -> dict[str, Any] | None:
        job = self.job(job_id)
        if job is None:
            return None
        with self._conn() as db:
            items = [dict(row) for row in db.execute(
                "SELECT i.* FROM items i JOIN job_items j ON i.platform=j.platform AND i.external_id=j.external_id WHERE j.job_id=? ORDER BY i.updated_at DESC LIMIT 100",
                (job_id,))]
            comments = [dict(row) for row in db.execute(
                "SELECT c.* FROM comments c JOIN job_comments j ON c.platform=j.platform AND c.external_id=j.external_id WHERE j.job_id=? ORDER BY c.updated_at DESC LIMIT 100",
                (job_id,))]
        return {"job": job, "items": items, "comments": comments}

    def leads(self, *, q: str = "", level: str = "", review_state: str = "") -> list[dict[str, Any]]:
        clauses = ["1=1"]
        args: list[Any] = []
        if q:
            clauses.append("(nickname LIKE ? OR latest_body LIKE ? OR keyword LIKE ?)")
            args.extend([f"%{q}%"] * 3)
        if level:
            clauses.append("level=?")
            args.append(level)
        if review_state:
            clauses.append("review_state=?")
            args.append(review_state)
        with self._conn() as db:
            rows = db.execute(
                f"SELECT * FROM leads WHERE {' AND '.join(clauses)} ORDER BY score DESC, updated_at DESC LIMIT 200", args)
            return [self._lead_with_analysis(db, row) for row in rows]

    def lead(self, lead_id: str) -> dict[str, Any] | None:
        with self._conn() as db:
            row = db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
            return self._lead_with_analysis(db, row) if row else None

    @staticmethod
    def _lead_with_analysis(db: sqlite3.Connection, lead: sqlite3.Row) -> dict[str, Any]:
        result = dict(lead)
        analysis = db.execute("SELECT * FROM lead_analyses WHERE lead_id=?", (lead["id"],)).fetchone()
        result["ai_analysis"] = dict(analysis) if analysis else None
        return result

    def lead_evidence(self, lead_id: str, *, limit: int = 12) -> list[dict[str, Any]]:
        with self._conn() as db:
            lead = db.execute("SELECT platform, identity_key FROM leads WHERE id=?", (lead_id,)).fetchone()
            if lead is None:
                raise LookupError("潜客不存在")
            if lead["identity_key"].startswith("comment:"):
                rows = db.execute("""SELECT body, source FROM comments WHERE platform=? AND external_id=?
                                   ORDER BY updated_at DESC LIMIT ?""",
                                  (lead["platform"], lead["identity_key"].removeprefix("comment:"), limit))
            else:
                rows = db.execute("""SELECT body, source FROM comments WHERE platform=? AND author_id=?
                                   ORDER BY updated_at DESC LIMIT ?""",
                                  (lead["platform"], lead["identity_key"], limit))
            return [dict(row) for row in rows]

    def save_lead_analysis(self, lead_id: str, model: str, analysis: dict[str, str]) -> dict[str, Any]:
        stamp = now()
        fields = ("summary", "intent_assessment", "confidence", "recommended_action",
                  "follow_up_message", "skill_name", "skill_instructions")
        values = [analysis[field] for field in fields]
        with self._conn() as db:
            if not db.execute("SELECT 1 FROM leads WHERE id=?", (lead_id,)).fetchone():
                raise LookupError("潜客不存在")
            db.execute("""INSERT INTO lead_analyses(
                        lead_id,model,summary,intent_assessment,confidence,recommended_action,
                        follow_up_message,skill_name,skill_instructions,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(lead_id) DO UPDATE SET
                        model=excluded.model, summary=excluded.summary,
                        intent_assessment=excluded.intent_assessment, confidence=excluded.confidence,
                        recommended_action=excluded.recommended_action,
                        follow_up_message=excluded.follow_up_message, skill_name=excluded.skill_name,
                        skill_instructions=excluded.skill_instructions, updated_at=excluded.updated_at""",
                       (lead_id, model, *values, stamp, stamp))
            lead = db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
            assert lead is not None
            return self._lead_with_analysis(db, lead)

    def review_lead(self, lead_id: str, state: str) -> dict[str, Any] | None:
        if state not in ("new", "reviewed", "dismissed"):
            raise ValueError("无效复核状态")
        with self._conn() as db:
            current = db.execute("SELECT customer_id FROM leads WHERE id=?", (lead_id,)).fetchone()
            if current and current["customer_id"] and state == "dismissed":
                raise ValueError("已转入客户的潜客不能排除")
            db.execute("UPDATE leads SET review_state=?,updated_at=? WHERE id=?", (state, now(), lead_id))
        return self.lead(lead_id)

    def create_customer(self, fields: dict[str, Any], lead_id: str | None = None) -> dict[str, Any]:
        customer_id = str(uuid.uuid4())
        stamp = now()
        with self._conn() as db:
            if lead_id:
                lead = db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
                if not lead:
                    raise LookupError("潜客不存在")
                if lead["customer_id"]:
                    row = db.execute("SELECT * FROM customers WHERE id=?", (lead["customer_id"],)).fetchone()
                    if row:
                        return dict(row)
            db.execute("""INSERT INTO customers(id,name,company,phone,need,source_platform,source_lead_id,
                         status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                       (customer_id, fields["name"], fields.get("company", ""), fields.get("phone", ""),
                        fields.get("need", ""), lead["platform"] if lead_id else fields.get("source_platform", ""),
                        lead_id, "new", stamp, stamp))
            if lead_id:
                db.execute("UPDATE leads SET customer_id=?,review_state='reviewed',updated_at=? WHERE id=?",
                           (customer_id, stamp, lead_id))
            db.execute("INSERT INTO customer_events VALUES(?,?,?,?,?)",
                       (str(uuid.uuid4()), customer_id, "created", "从潜客转入" if lead_id else "手动创建", stamp))
            row = db.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
            return dict(row)

    def customers(self, *, q: str = "", status: str = "") -> list[dict[str, Any]]:
        clauses = ["1=1"]
        args: list[Any] = []
        if q:
            clauses.append("(name LIKE ? OR company LIKE ? OR need LIKE ?)")
            args.extend([f"%{q}%"] * 3)
        if status:
            clauses.append("status=?")
            args.append(status)
        with self._conn() as db:
            return [dict(row) for row in db.execute(
                f"SELECT * FROM customers WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT 200", args)]

    def customer(self, customer_id: str) -> dict[str, Any] | None:
        with self._conn() as db:
            row = db.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["events"] = [dict(event) for event in db.execute(
                "SELECT * FROM customer_events WHERE customer_id=? ORDER BY created_at DESC LIMIT 100", (customer_id,))]
            return result

    def update_customer(self, customer_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        allowed = ("name", "company", "phone", "need", "status", "follow_up_at")
        changed = {key: fields[key] for key in allowed if key in fields}
        if not changed:
            raise ValueError("没有可更新字段")
        with self._conn() as db:
            current = db.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
            if not current:
                return None
            stamp = now()
            db.execute(f"UPDATE customers SET {', '.join(key + '=?' for key in changed)},updated_at=? WHERE id=?",
                       [*changed.values(), stamp, customer_id])
            details = ", ".join(f"{key}: {current[key]} → {value}" for key, value in changed.items() if key != "phone")
            db.execute("INSERT INTO customer_events VALUES(?,?,?,?,?)",
                       (str(uuid.uuid4()), customer_id, "updated", details or "联系方式已更新", stamp))
        return self.customer(customer_id)

    def analytics(self, days: int) -> dict[str, Any]:
        tz = ZoneInfo("Asia/Shanghai")
        today = datetime.now(tz).date()
        start = today.toordinal() - days + 1
        labels = [(today.fromordinal(start + index)).isoformat() for index in range(days)]
        daily = {label: {"date": label, "leads": 0, "customers": 0} for label in labels}
        with self._conn() as db:
            jobs = [dict(row) for row in db.execute("SELECT * FROM jobs")]
            leads = [dict(row) for row in db.execute("SELECT * FROM leads WHERE review_state!='dismissed'")]
            customers = [dict(row) for row in db.execute("SELECT * FROM customers")]
            comments = [dict(row) for row in db.execute("SELECT * FROM comments")]
            items = [dict(row) for row in db.execute("SELECT * FROM items")]
        def local_date(value: str) -> str:
            return datetime.fromisoformat(value).astimezone(tz).date().isoformat()
        jobs = [row for row in jobs if local_date(row["created_at"]) in daily]
        leads = [row for row in leads if local_date(row["created_at"]) in daily]
        customers = [row for row in customers if local_date(row["created_at"]) in daily]
        comments = [row for row in comments if local_date(row["updated_at"]) in daily]
        items = [row for row in items if local_date(row["updated_at"]) in daily]
        for row in leads:
            daily[local_date(row["created_at"])]["leads"] += 1
        for row in customers:
            daily[local_date(row["created_at"])]["customers"] += 1
        converted_ids = {row["customer_id"] for row in leads if row["customer_id"]}
        return {"days": days, "jobs": len(jobs), "completed_jobs": sum(row["state"] == "succeeded" for row in jobs),
                "items": len(items), "comments": len(comments), "leads": len(leads),
                "high_intent": sum(row["score"] >= 70 for row in leads),
                "customers": len(customers), "converted": len(converted_ids),
                "won": sum(row["status"] == "won" for row in customers),
                "won_from_leads": sum(row["status"] == "won" and row["id"] in converted_ids for row in customers),
                "daily": list(daily.values()),
                "by_platform": {platform: sum(row["platform"] == platform for row in leads) for platform in ("dy", "xhs")}}
