"""Import an existing MediaCrawler JSONL export without calling a platform."""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from .adapters import DATA, import_mediacrawler_output
from .store import Store


def main() -> None:
    parser = argparse.ArgumentParser(description="导入 MediaCrawler 已导出的 JSONL")
    parser.add_argument("folder", type=Path, help="包含 douyin/jsonl 或 xhs/jsonl 的输出目录")
    parser.add_argument("--platform", choices=("dy", "xhs"), required=True)
    parser.add_argument("--keyword", default="历史导入")
    args = parser.parse_args()
    folder = args.folder.expanduser().resolve()
    expected = folder / ("douyin" if args.platform == "dy" else "xhs") / "jsonl"
    if not expected.is_dir() or not list(expected.glob("search_*.jsonl")):
        parser.error("目录中未找到对应平台的搜索 JSONL 文件")
    job_id = str(uuid.uuid4())
    store = Store(Path.cwd() / ".local-data" / "crawler.sqlite3")
    store.create_job(job_id, "mediacrawler_import", args.platform, args.keyword)
    try:
        items, comments = import_mediacrawler_output(store, job_id, args.platform, folder)
    except Exception as exc:
        store.update_job(job_id, "failed", error="导入失败，请检查源文件格式")
        raise SystemExit(f"导入失败：{type(exc).__name__}") from exc
    store.update_job(job_id, "succeeded", items_count=items, comments_count=comments)
    print(f"任务 {job_id}：素材 {items}，评论 {comments}")


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
