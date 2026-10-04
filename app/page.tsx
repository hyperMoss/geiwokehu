"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Shell } from "./components/Shell";

type Job = {
  id: string; adapter: string; platform: string; keyword: string; state: string;
  error: string | null; items_count: number; comments_count: number;
  max_items: number; max_comments: number;
  created_at: string; updated_at: string;
};
type RecordItem = { platform: string; external_id: string; title: string; body: string; url: string; keyword: string; source: string; identity_kind: string };
type RecordComment = { platform: string; external_id: string; item_id: string; nickname: string; body: string; source: string; identity_kind: string };
type Results = { job: Job; items: RecordItem[]; comments: RecordComment[] };

const names: Record<string, string> = { queued: "排队中", running: "采集中", succeeded: "已完成", failed: "失败", interrupted: "已中断" };

export default function Home() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [results, setResults] = useState<Results | null>(null);
  const [platform, setPlatform] = useState("dy");
  const [keyword, setKeyword] = useState("");
  const [maxItems, setMaxItems] = useState(10);
  const [maxComments, setMaxComments] = useState(10);
  const [busy, setBusy] = useState(false);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const minimumItems = platform === "dy" ? 10 : 20;

  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/jobs", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "获取任务失败");
      setJobs(data.jobs || []);
      setNotice("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "获取任务失败");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!selected) return;
    const load = async () => {
      try {
        const response = await fetch(`/api/jobs/${selected}`, { cache: "no-store" });
        const data = await response.json();
        if (response.ok) setResults(data);
      } catch { /* The list refresh presents connection errors. */ }
    };
    void load();
    const timer = window.setInterval(() => void load(), 4000);
    return () => window.clearInterval(timer);
  }, [selected]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    try {
      const response = await fetch("/api/jobs", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ adapter: "mediacrawler", platform, keyword, max_items: maxItems, max_comments: maxComments }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "创建任务失败");
      setSelected(data.id);
      setResults(null);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "创建任务失败");
    } finally {
      setBusy(false);
    }
  }

  async function retry(job: Job) {
    setRetrying(job.id);
    setNotice("");
    try {
      const response = await fetch(`/api/jobs/${job.id}/retry`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "重试任务创建失败");
      setSelected(data.id);
      setResults(null);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "重试任务创建失败");
    } finally {
      setRetrying(null);
    }
  }

  const active = results?.job || jobs.find((job) => job.id === selected);
  const commentsByItem = results?.comments.reduce<Record<string, RecordComment[]>>((groups, comment) => {
    (groups[comment.item_id] ??= []).push(comment);
    return groups;
  }, {}) ?? {};
  const itemIds = new Set(results?.items.map((item) => item.external_id) ?? []);
  const unlinkedComments = results?.comments.filter((comment) => !itemIds.has(comment.item_id)) ?? [];

  return <Shell active="/" title="关键词获客">
        <div className="heading"><div><div className="eyebrow">DATA COLLECTION</div><h1>采集工作台</h1><p>项目内置 MediaCrawler 的抖音和小红书采集模块，在每条素材下查看关联评论。</p></div><button className="secondary" onClick={() => void refresh()}>刷新任务</button></div>
        <div className="banner">配置服务端 Cookie 与 Python 依赖后即可采集；页面不保存 Cookie。<Link href="/integrations">前往集成配置 →</Link></div>
        <div className="grid">
          <section className="panel"><h2>新建采集任务</h2><form onSubmit={submit}>
            <label>采集器<input value="MediaCrawler" readOnly /></label>
            <label>平台<select value={platform} onChange={(event) => { const value = event.target.value; setPlatform(value); setMaxItems(value === "dy" ? 10 : 20); }}><option value="dy">抖音</option><option value="xhs">小红书</option></select></label>
            <label>关键词<input value={keyword} onChange={(event) => setKeyword(event.target.value)} maxLength={80} required placeholder="例如：AI 转型" /></label>
            <div className="two-col"><label>最多素材<input type="number" min={minimumItems} max="20" value={maxItems} onChange={(event) => setMaxItems(Number(event.target.value))} /></label><label>每条素材附带评论<input type="number" min="0" max="30" value={maxComments} onChange={(event) => setMaxComments(Number(event.target.value))} /></label></div>
            <button className="primary" disabled={busy || retrying !== null}>{busy ? "提交中…" : "开始采集"}</button>
          </form></section>
          <section className="panel jobs"><div className="section-top"><h2>最近任务</h2><span>{jobs.length} 条</span></div>{jobs.length === 0 ? <p className="empty">暂无任务。配置本地采集服务后可在左侧创建。</p> : <div className="job-list">{jobs.map((job) => <button key={job.id} className={`job ${selected === job.id ? "selected" : ""}`} onClick={() => { setSelected(job.id); setResults(null); }}><span><strong>{job.keyword}</strong><small>{job.adapter} · {job.platform === "dy" ? "抖音" : "小红书"}</small></span><span className={`status status-${job.state}`}>{names[job.state] || job.state}</span></button>)}</div>}</section>
        </div>
        {notice && <div className="notice" role="alert">{notice}</div>}
        <section className="panel results"><div className="section-top"><div><h2>采集结果</h2><p>{active ? `任务 ${active.id.slice(0, 8)} · ${active.keyword}` : "选择一个任务查看素材和评论"}</p></div><div className="inline-actions">{active && (active.state === "failed" || active.state === "interrupted") && <button className="secondary" type="button" disabled={busy || retrying !== null} onClick={() => void retry(active)}>{retrying === active.id ? "重试提交中…" : "重试任务"}</button>}<Link className="secondary link-button" href="/leads">查看潜客 →</Link>{active && <span className={`status status-${active.state}`}>{names[active.state] || active.state}</span>}</div></div>
          {active?.error && <div className="notice" role="alert"><span>{active.error}</span>{active.error.includes("ACCOUNT_COOKIE") && <Link className="notice-link" href="/integrations">打开集成配置 →</Link>}</div>}
          {active && <div className="stats"><div><span>素材</span><strong>{active.items_count}</strong></div><div><span>评论</span><strong>{active.comments_count}</strong></div><div><span>更新时间</span><strong className="date">{new Date(active.updated_at).toLocaleString("zh-CN")}</strong></div></div>}
          {!results ? <p className="empty">{active ? "正在加载任务结果…" : "尚未选择任务"}</p> : results.items.length === 0 ? <p className="empty">该任务暂无素材</p> : <div className="records">{results.items.map((entry) => {
            const attachedComments = commentsByItem[entry.external_id] ?? [];
            return <article className="record" key={`${entry.platform}:${entry.external_id}`}><div className="record-title">{entry.title || "无标题"}</div><p>{entry.body || "暂无正文"}</p><div className="meta"><span>{entry.source}</span><span>{entry.keyword}</span><span>{entry.identity_kind === "anonymous_hash" ? "作者身份已匿名" : "平台身份"}</span><a href={entry.url} target="_blank" rel="noreferrer">打开来源 ↗</a></div><section className="record-comments" aria-label="关联评论"><div className="record-comments-head"><h3>关联评论</h3><span>{attachedComments.length} 条</span></div>{attachedComments.length === 0 ? <p className="comments-empty">这条素材未采到评论</p> : <details className="comment-fold"><summary>展开 {attachedComments.length} 条评论</summary><div className="comment-list">{attachedComments.map((comment) => <article className="record-comment" key={`${comment.platform}:${comment.external_id}`}><strong>{comment.nickname || "匿名用户"}</strong><p>{comment.body || "空评论"}</p><small>{comment.identity_kind === "anonymous_hash" ? "用户身份已匿名" : "平台身份"}</small></article>)}</div></details>}</section></article>;
          })}{unlinkedComments.length > 0 && <section className="unlinked-comments"><div className="record-comments-head"><h3>未关联素材的评论</h3><span>{unlinkedComments.length} 条</span></div><div className="comment-list">{unlinkedComments.map((comment) => <article className="record-comment" key={`${comment.platform}:${comment.external_id}`}><strong>{comment.nickname || "匿名用户"}</strong><p>{comment.body || "空评论"}</p><small>{comment.identity_kind === "anonymous_hash" ? "用户身份已匿名" : "平台身份"}</small></article>)}</div></section>}</div>}
        </section>
  </Shell>;
}
