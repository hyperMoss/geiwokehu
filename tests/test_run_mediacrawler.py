from __future__ import annotations

import asyncio
import unittest

from scripts.run_mediacrawler import execute_crawler


class TargetClosedError(Exception):
    pass


class ClosedContext:
    async def close(self) -> None:
        raise TargetClosedError("already closed")


class FailedCrawler:
    browser_context = ClosedContext()

    async def start(self) -> None:
        raise RuntimeError("original platform failure")


class BrokenContext:
    async def close(self) -> None:
        raise RuntimeError("unexpected cleanup failure")


class SuccessfulCrawler:
    browser_context = BrokenContext()

    async def start(self) -> None:
        return None


class RunMediaCrawlerTests(unittest.TestCase):
    def test_closed_context_does_not_mask_original_platform_failure(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "original platform failure"):
            asyncio.run(execute_crawler(FailedCrawler()))

    def test_unrelated_cleanup_failure_is_not_hidden(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unexpected cleanup failure"):
            asyncio.run(execute_crawler(SuccessfulCrawler()))


if __name__ == "__main__":
    unittest.main()
