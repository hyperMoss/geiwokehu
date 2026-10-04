"use client";

import { useEffect, useState } from "react";
import { Shell } from "../../components/Shell";

type Analytics = { days: number; jobs: number; completed_jobs: number; items: number; comments: number; leads: number; high_intent: number; customers: number; converted: number; won: number; won_from_leads: number; daily: { date: string; leads: number; customers: number }[]; by_platform: Record<string, number> };

export default function LeadAnalyticsPage() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/analytics/lead?days=${days}`, { cache: "no-store" }).then(async (response) => {
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "统计加载失败");
      if (!cancelled) { setData(body); setError(""); }
    }).catch((cause) => { if (!cancelled) setError(cause instanceof Error ? cause.message : "统计加载失败"); });
    return () => { cancelled = true; };
  }, [days]);

  const max = Math.max(1, ...(data?.daily.map((day) => Math.max(day.leads, day.customers)) ?? [1]));
  const stages = data ? [
    { label: "规则识别潜客", count: data.leads, color: "#008e88" },
    { label: "高意向候选", count: data.high_intent, color: "#079abe" },
    { label: "转入客户", count: data.converted, color: "#813af2" },
    { label: "已成交", count: data.won_from_leads, color: "#ef8708" },
  ] : [];

  return <Shell active="/analytics/lead" title="获客分析">
    <div className="heading"><div><div className="eyebrow">LEAD ANALYTICS</div><h1>获客分析</h1><p>查看采集产出、潜客质量和转客户进度。</p></div><div className="period-switch">{[7, 30, 90].map((value) => <button key={value} className={days === value ? "on" : ""} onClick={() => setDays(value)}>{value} 天</button>)}</div></div>
    <div className="banner">按 Asia/Shanghai 自然日统计，今天的数据仍在变化。潜客和高意向使用可解释规则初筛，尚未经过 AI 质量验收；不同阶段是当前状态快照。</div>
    {error && <div className="notice" role="alert">{error}</div>}
    {!data ? <div className="panel empty">正在加载分析数据…</div> : <>
      <div className="kpi-grid">{[
        ["获客任务", data.jobs, `${data.completed_jobs} 已完成`],
        ["素材", data.items, "去重记录"],
        ["评论", data.comments, "去重记录"],
        ["潜客", data.leads, "已排除不计"],
        ["高意向", data.high_intent, "规则分 ≥70"],
        ["转入客户", data.converted, data.leads ? `约 ${Math.round(data.converted / data.leads * 100)}% / 潜客` : "暂无转化"],
      ].map(([label, value, hint]) => <div className="panel kpi" key={label}><span>{label}</span><strong>{value}</strong><small>{hint}</small></div>)}</div>
      <div className="analytics-grid"><section className="panel"><h2>转化漏斗</h2><p className="muted">规则潜客 → 高意向 → 转客户 → 成交</p><div className="funnel">{stages.map((stage, index) => <div className="funnel-row" key={stage.label}><span>{stage.label}</span><div className="funnel-track"><div style={{ width: `${Math.max(stage.count ? 5 : 0, data.leads ? stage.count / data.leads * 100 : 0)}%`, background: stage.color }}>{stage.count}</div></div><small>{index === 0 ? "100%" : stages[index - 1].count ? `${Math.round(stage.count / stages[index - 1].count * 100)}%` : "—"}</small></div>)}</div></section>
      <section className="panel"><h2>每日新增</h2><p className="muted">潜客与转入客户</p><div className="chart" role="img" aria-label="每日新增潜客与客户柱状图">{data.daily.map((day) => <div className="chart-day" key={day.date} title={`${day.date}：潜客 ${day.leads}，客户 ${day.customers}`}><div className="chart-bars"><span className="bar-lead" style={{ height: `${Math.max(day.leads ? 4 : 0, day.leads / max * 100)}%` }} /><span className="bar-customer" style={{ height: `${Math.max(day.customers ? 4 : 0, day.customers / max * 100)}%` }} /></div></div>)}</div><div className="chart-legend"><span>■ 潜客</span><span>■ 转入客户</span></div><p className="muted">{data.daily[0]?.date} — {data.daily.at(-1)?.date}</p></section></div>
      <section className="panel platform-summary"><h2>来源平台</h2><div><span>抖音 <strong>{data.by_platform.dy ?? 0}</strong></span><span>小红书 <strong>{data.by_platform.xhs ?? 0}</strong></span><span>成交 <strong>{data.won}</strong></span></div></section>
    </>}
  </Shell>;
}
