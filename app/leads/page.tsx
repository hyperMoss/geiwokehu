"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Shell } from "../components/Shell";

type AiAnalysis = { model: string; summary: string; intent_assessment: string; confidence: "low" | "medium" | "high"; recommended_action: string; follow_up_message: string; skill_name: string; skill_instructions: string; updated_at: string };
type Lead = { id: string; platform: string; nickname: string; keyword: string; score: number; level: string; reason: string; evidence_count: number; latest_body: string; review_state: string; customer_id: string | null; created_at: string; ai_analysis: AiAnalysis | null };

const confidenceLabels = { low: "低置信度", medium: "中置信度", high: "高置信度" };

export default function LeadsPage() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState("");
  const [state, setState] = useState("");
  const [selected, setSelected] = useState<Lead | null>(null);
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [phone, setPhone] = useState("");
  const [need, setNeed] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [analyzingId, setAnalyzingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const params = new URLSearchParams({ q: query, level, state });
      const response = await fetch(`/api/leads?${params}`, { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "获取潜客失败");
      setLeads(data.leads);
      setNotice("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "获取潜客失败");
    }
  }, [query, level, state]);

  useEffect(() => { void refresh(); }, [refresh]);

  async function review(lead: Lead, reviewState: string) {
    setBusy(true);
    try {
      const response = await fetch(`/api/leads/${lead.id}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ state: reviewState }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "更新失败");
      await refresh();
    } catch (error) { setNotice(error instanceof Error ? error.message : "更新失败"); }
    finally { setBusy(false); }
  }

  async function analyze(lead: Lead) {
    setAnalyzingId(lead.id);
    setNotice("");
    try {
      const response = await fetch(`/api/leads/${lead.id}/analysis`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "AI 分析失败");
      await refresh();
      setNotice("AI 分析已更新；请人工核实后再联系或转入客户。");
    } catch (error) { setNotice(error instanceof Error ? error.message : "AI 分析失败"); }
    finally { setAnalyzingId(null); }
  }

  function openConvert(lead: Lead) {
    setSelected(lead);
    setName(lead.nickname === "匿名用户" ? "" : lead.nickname);
    setCompany(""); setPhone(""); setNeed(lead.latest_body);
    setNotice("");
  }

  async function convert(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/leads/${selected.id}/convert`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name, company, phone, need }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "转客户失败");
      setSelected(null);
      await refresh();
      setNotice(`已转入客户：${data.name}`);
    } catch (error) { setNotice(error instanceof Error ? error.message : "转客户失败"); }
    finally { setBusy(false); }
  }

  return <Shell active="/leads" title="潜客筛选">
    <div className="heading"><div><div className="eyebrow">LEAD REVIEW</div><h1>潜客筛选</h1><p>依据评论中的明确意向词做规则初筛，人工确认后转入客户。</p></div><button className="secondary" onClick={() => void refresh()}>刷新</button></div>
    <div className="banner">规则分由本地规则生成。点击“AI 分析”后，所选潜客的匿名评论证据会发送至你配置的 DeepSeek；结果仅作辅助判断，不会自动联系、转客户或改变规则分。</div>
    <div className="filters">
      <input aria-label="搜索潜客" placeholder="搜索昵称、评论或关键词" value={query} onChange={(event) => setQuery(event.target.value)} />
      <select aria-label="意向等级" value={level} onChange={(event) => setLevel(event.target.value)}><option value="">全部意向</option><option value="A">A 明确需求</option><option value="B">B 咨询方案</option><option value="C">C 泛兴趣</option></select>
      <select aria-label="复核状态" value={state} onChange={(event) => setState(event.target.value)}><option value="">全部状态</option><option value="new">待复核</option><option value="reviewed">已复核</option><option value="dismissed">已排除</option></select>
    </div>
    {notice && <div className="notice" role="alert">{notice}</div>}
    <div className="lead-list">{leads.length === 0 ? <div className="panel empty">暂无符合条件的潜客。先运行采集任务或导入 JSONL。</div> : leads.map((lead) => <article className="panel lead-card" key={lead.id}>
      <div className="lead-head"><div><strong>{lead.nickname}</strong><span className="muted">{lead.platform === "dy" ? "抖音" : "小红书"} · {lead.keyword || "未标记关键词"} · {lead.evidence_count} 条证据</span></div><div className="inline-actions"><span className={`intent intent-${lead.level}`}>{lead.level} · {lead.score} 规则分</span><span className="status">{lead.customer_id ? "已转客户" : lead.review_state === "dismissed" ? "已排除" : lead.review_state === "reviewed" ? "已复核" : "待复核"}</span></div></div>
      <p className="quote">“{lead.latest_body}”</p><p className="muted">初筛依据：{lead.reason}</p>
      {lead.ai_analysis && <section className="lead-ai-analysis" aria-label="AI 潜客分析"><div className="analysis-head"><h3>AI 分析</h3><span>{lead.ai_analysis.model} · {confidenceLabels[lead.ai_analysis.confidence]} · {new Date(lead.ai_analysis.updated_at).toLocaleString("zh-CN")}</span></div><p>{lead.ai_analysis.summary}</p><dl className="analysis-grid"><div><dt>意向判断</dt><dd>{lead.ai_analysis.intent_assessment}</dd></div><div><dt>建议动作</dt><dd>{lead.ai_analysis.recommended_action}</dd></div><div><dt>沟通草稿</dt><dd>{lead.ai_analysis.follow_up_message}</dd></div></dl><details className="analysis-skill"><summary>建议跟进 Skill：{lead.ai_analysis.skill_name}</summary><p>{lead.ai_analysis.skill_instructions}</p></details></section>}
      <div className="card-actions">{!lead.customer_id && <button className="secondary" disabled={busy || analyzingId !== null} onClick={() => void analyze(lead)}>{analyzingId === lead.id ? "AI 分析中…" : lead.ai_analysis ? "重新 AI 分析" : "AI 分析"}</button>}{lead.customer_id ? <Link href={`/customers?customer=${lead.customer_id}`}>查看客户 →</Link> : <><button className="secondary" disabled={busy || analyzingId !== null} onClick={() => void review(lead, "reviewed")}>标记已复核</button><button className="secondary" disabled={busy || analyzingId !== null} onClick={() => void review(lead, lead.review_state === "dismissed" ? "new" : "dismissed")}>{lead.review_state === "dismissed" ? "恢复" : "排除"}</button><button className="primary" disabled={busy || analyzingId !== null} onClick={() => openConvert(lead)}>转客户</button></>}</div>
    </article>)}</div>
    {selected && <div className="modal-backdrop" onClick={() => setSelected(null)}><div className="modal panel" onClick={(event) => event.stopPropagation()}><h2>转入客户</h2><p className="muted">来源证据会保留。昵称已脱敏，请填写已核实的客户名称；联系方式可稍后补充。</p><form onSubmit={convert} className="form-stack"><label>客户名称 *<input required maxLength={100} value={name} onChange={(event) => setName(event.target.value)} /></label><label>公司<input maxLength={100} value={company} onChange={(event) => setCompany(event.target.value)} /></label><label>手机号（已核实才填写）<input maxLength={40} value={phone} onChange={(event) => setPhone(event.target.value)} /></label><label>需求摘要<textarea maxLength={1000} value={need} onChange={(event) => setNeed(event.target.value)} /></label><div className="card-actions"><button type="button" className="secondary" onClick={() => setSelected(null)}>取消</button><button className="primary" disabled={busy}>确认转入</button></div></form></div></div>}
  </Shell>;
}
