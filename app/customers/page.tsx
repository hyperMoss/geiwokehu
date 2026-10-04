"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Shell } from "../components/Shell";

type Customer = { id: string; name: string; company: string; phone: string; need: string; source_platform: string; source_lead_id: string | null; status: string; follow_up_at: string | null; created_at: string; updated_at: string; events?: { id: string; kind: string; detail: string; created_at: string }[] };
type FormData = { name: string; company: string; phone: string; need: string; status: string; follow_up_at: string };
const emptyForm: FormData = { name: "", company: "", phone: "", need: "", status: "new", follow_up_at: "" };
const statuses: Record<string, string> = { new: "待分配", following: "跟进中", nurturing: "培育中", won: "已成交", lost: "已流失" };

function localInput(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<Customer | null>(null);
  const [form, setForm] = useState<FormData>(emptyForm);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    try {
      const params = new URLSearchParams({ q: query, status });
      const response = await fetch(`/api/customers?${params}`, { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "获取客户失败");
      setCustomers(data.customers);
      setNotice("");
    } catch (error) { setNotice(error instanceof Error ? error.message : "获取客户失败"); }
  }, [query, status]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("customer");
    if (id) void openCustomer(id);
  }, []);

  async function openCustomer(id: string) {
    try {
      const response = await fetch(`/api/customers/${id}`, { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "获取客户失败");
      setSelected(data);
      setCreating(false);
      setForm({ name: data.name, company: data.company, phone: data.phone, need: data.need, status: data.status, follow_up_at: localInput(data.follow_up_at) });
    } catch (error) { setNotice(error instanceof Error ? error.message : "获取客户失败"); }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const payload = { ...form, follow_up_at: form.follow_up_at ? new Date(form.follow_up_at).toISOString() : null };
      const url = creating ? "/api/customers" : `/api/customers/${selected?.id}`;
      const response = await fetch(url, { method: creating ? "POST" : "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "保存失败");
      await refresh();
      await openCustomer(data.id);
      setNotice("客户已保存");
    } catch (error) { setNotice(error instanceof Error ? error.message : "保存失败"); }
    finally { setBusy(false); }
  }

  return <Shell active="/customers" title="客户管理">
    <div className="heading"><div><div className="eyebrow">CUSTOMER RELATIONSHIP</div><h1>客户管理</h1><p>整理转入的潜客、补全资料并记录跟进状态。</p></div><button className="primary" onClick={() => { setCreating(true); setSelected(null); setForm(emptyForm); }}>+ 新建客户</button></div>
    <div className="filters"><input aria-label="搜索客户" placeholder="搜索名称、公司或需求" value={query} onChange={(event) => setQuery(event.target.value)} /><select aria-label="客户状态" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">全部状态</option>{Object.entries(statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
    {notice && <div className="notice" role="alert">{notice}</div>}
    <div className="customer-grid"><section className="panel"><div className="section-top"><h2>客户列表</h2><span>{customers.length} 条</span></div>{customers.length === 0 ? <p className="empty">暂无客户。可以手动创建或从潜客筛选页转入。</p> : <div className="customer-list">{customers.map((customer) => <button key={customer.id} className={`customer-row ${selected?.id === customer.id ? "selected" : ""}`} onClick={() => void openCustomer(customer.id)}><span><strong>{customer.name}</strong><small>{customer.company || "公司待补充"} · {customer.source_platform === "dy" ? "抖音" : customer.source_platform === "xhs" ? "小红书" : "手动录入"}</small></span><span className="status">{statuses[customer.status]}</span></button>)}</div>}</section>
      <section className="panel"><h2>{creating ? "新建客户" : selected ? selected.name : "客户详情"}</h2>{creating || selected ? <><form className="form-stack" onSubmit={save}><div className="two-col"><label>客户名称 *<input required maxLength={100} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label><label>公司<input maxLength={100} value={form.company} onChange={(event) => setForm({ ...form, company: event.target.value })} /></label></div><div className="two-col"><label>手机号<input maxLength={40} value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} /></label><label>生命周期<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>{Object.entries(statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div><label>需求摘要<textarea maxLength={1000} value={form.need} onChange={(event) => setForm({ ...form, need: event.target.value })} /></label><label>下次跟进时间<input type="datetime-local" value={form.follow_up_at} onChange={(event) => setForm({ ...form, follow_up_at: event.target.value })} /></label><div className="card-actions">{creating && <button type="button" className="secondary" onClick={() => setCreating(false)}>取消</button>}<button className="primary" disabled={busy}>{busy ? "保存中…" : "保存客户"}</button></div></form>{selected && <div className="history"><h3>操作记录</h3>{selected.events?.length ? selected.events.map((event) => <div className="history-item" key={event.id}><span>{new Date(event.created_at).toLocaleString("zh-CN")}</span><p>{event.detail}</p></div>) : <p className="muted">暂无记录</p>}</div>}</> : <p className="empty">从左侧选择客户查看和编辑。</p>}</section></div>
  </Shell>;
}
