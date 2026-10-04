"""Transparent first-pass intent hints; these are not AI scores."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hint:
    score: int
    level: str
    reason: str


EXCLUDE = ("不需要", "没兴趣", "不用了", "别买", "私信我", "加我微信", "招代理")
DIRECT = ("求机构", "找机构", "求推荐", "多少钱", "什么价格", "报价", "怎么报名", "我要报名", "想购买", "怎么买", "求合作")
CONSULT = ("有没有", "能不能", "可以吗", "怎么做", "如何做", "什么方案", "适合吗", "怎么收费", "想咨询")
INTEREST = ("想了解", "求资料", "了解一下", "感兴趣", "学习一下")


def hint_for_comment(body: str) -> Hint | None:
    text = body.strip().lower()[:2000]
    if not text or any(word in text for word in EXCLUDE):
        return None
    for words, score, level, reason in (
        (DIRECT, 85, "A", "包含明确购买、报名、询价或寻找服务的表达"),
        (CONSULT, 65, "B", "包含方案或适用性咨询表达"),
        (INTEREST, 30, "C", "包含泛兴趣或资料诉求表达"),
    ):
        if any(word in text for word in words):
            return Hint(score, level, reason)
    return None
