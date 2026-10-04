"""Execute the bundled Douyin/XHS MediaCrawler subset with isolated output."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


async def close_browser_context(crawler: object) -> None:
    """Close a live context without masking an earlier crawler failure."""
    browser_context = getattr(crawler, "browser_context", None)
    if browser_context is None:
        return
    try:
        await browser_context.close()
    except Exception as exc:
        # MediaCrawler may already close the Playwright context when startup or
        # a platform request fails. Playwright is only available in the child
        # environment, so match its narrowly named cleanup exception here.
        if type(exc).__name__ != "TargetClosedError":
            raise


async def execute_crawler(crawler: object) -> None:
    try:
        await crawler.start()
    finally:
        await close_browser_context(crawler)


def run() -> None:
    source = Path(os.environ["BRIDGE_SOURCE_PATH"]).resolve()
    output = Path(os.environ["BRIDGE_RUN_PATH"]).resolve()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source))
    import config  # type: ignore[import-not-found]

    config.PLATFORM = os.environ["BRIDGE_PLATFORM"]
    config.CRAWLER_TYPE = "search"
    config.KEYWORDS = os.environ["BRIDGE_KEYWORD"]
    config.LOGIN_TYPE = "cookie"
    config.SAVE_DATA_OPTION = "jsonl"
    config.SAVE_DATA_PATH = str(output)
    config.CRAWLER_MAX_NOTES_COUNT = int(os.environ["BRIDGE_MAX_ITEMS"])
    config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = int(os.environ["BRIDGE_MAX_COMMENTS"])
    config.MAX_CONCURRENCY_NUM = 1
    config.ENABLE_GET_COMMENTS = config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES > 0
    config.ENABLE_GET_SUB_COMMENTS = False
    config.ENABLE_CDP_MODE = False
    config.SAVE_LOGIN_STATE = False
    config.HEADLESS = True
    config.ENABLE_IP_PROXY = False
    config.ENABLE_GET_MEDIA = False
    config.USER_DATA_DIR = str(output / "browser_%s")
    config.COOKIES = os.environ["CRAWLER_ACCOUNT_COOKIE"]
    if config.PLATFORM == "dy":
        from media_platform.douyin import DouYinCrawler  # type: ignore[import-not-found]
        crawler = DouYinCrawler()
    elif config.PLATFORM == "xhs":
        from media_platform.xhs import XiaoHongShuCrawler  # type: ignore[import-not-found]
        crawler = XiaoHongShuCrawler()
    else:
        raise ValueError("unsupported platform")

    asyncio.run(execute_crawler(crawler))


if __name__ == "__main__":
    run()
