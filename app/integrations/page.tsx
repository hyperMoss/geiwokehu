"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Shell } from "../components/Shell";

type Accounts = { dy: boolean; xhs: boolean };
type ModelSettings = { configured: boolean; model: string; base_url: string };
type Providers = { deepseek: ModelSettings };
type Capabilities = { accounts: Accounts; providers: Providers };

const platforms: Array<{ id: keyof Accounts; name: string; variable: string; description: string }> = [
  { id: "xhs", name: "小红书", variable: "XHS_ACCOUNT_COOKIE", description: "用于小红书关键词采集" },
  { id: "dy", name: "抖音", variable: "DOUYIN_ACCOUNT_COOKIE", description: "用于抖音关键词采集" },
];

function isCapabilities(value: unknown): value is Capabilities {
  if (!value || typeof value !== "object") return false;
  const accounts = (value as { accounts?: unknown }).accounts;
  const providers = (value as { providers?: unknown }).providers;
  const deepseek = providers && typeof providers === "object" ? (providers as { deepseek?: unknown }).deepseek : null;
  return Boolean(accounts) && typeof accounts === "object"
    && typeof (accounts as Accounts).dy === "boolean"
    && typeof (accounts as Accounts).xhs === "boolean"
    && Boolean(deepseek) && typeof deepseek === "object"
    && typeof (deepseek as ModelSettings).configured === "boolean"
    && typeof (deepseek as ModelSettings).model === "string"
    && typeof (deepseek as ModelSettings).base_url === "string";
}

function responseError(value: unknown): string {
  if (value && typeof value === "object" && typeof (value as { error?: unknown }).error === "string") {
    const error = (value as { error: string }).error;
    if (error === "接口不存在") return "本机采集服务尚未更新，请停止后重新启动 Python 服务";
    return error;
  }
  return "无法读取本机采集服务状态";
}

export default function IntegrationsPage() {
  const [accounts, setAccounts] = useState<Accounts | null>(null);
  const [providers, setProviders] = useState<Providers | null>(null);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [model, setModel] = useState("deepseek-flash");
  const [baseUrl, setBaseUrl] = useState("https://api.deepseek.com");
  const [clearApiKey, setClearApiKey] = useState(false);
  const apiKeyRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setNotice("");
    try {
      const response = await fetch("/api/integrations/capabilities", { cache: "no-store" });
      const data: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(responseError(data));
      if (!isCapabilities(data)) throw new Error("本机采集服务返回了无效的配置状态");
      setAccounts(data.accounts);
      setProviders(data.providers);
      setModel(data.providers.deepseek.model);
      setBaseUrl(data.providers.deepseek.base_url);
    } catch (error) {
      setAccounts(null);
      setProviders(null);
      setNotice(error instanceof Error ? error.message : "无法读取本机采集服务状态");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function saveModelConfig(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setNotice("");
    try {
      const apiKey = apiKeyRef.current?.value ?? "";
      const payload = { model, base_url: baseUrl, ...(apiKey ? { api_key: apiKey } : {}), clear_api_key: clearApiKey };
      const response = await fetch("/api/integrations/model", {
        method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(payload),
      });
      const data: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(responseError(data));
      if (apiKeyRef.current) apiKeyRef.current.value = "";
      setClearApiKey(false);
      await refresh();
      setNotice("模型配置已保存；后续手动 AI 分析会使用这套配置。");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "保存模型配置失败");
    } finally {
      setSaving(false);
    }
  }

  return <Shell active="/integrations" title="集成配置">
    <div className="heading">
      <div><div className="eyebrow">LOCAL INTEGRATIONS</div><h1>本机集成配置</h1><p>查看采集账号与 AI 分析服务的准备状态，并按步骤手动配置。</p></div>
      <button className="secondary" onClick={() => void refresh()} disabled={loading || saving}>{loading ? "检查中…" : "重新检查"}</button>
    </div>

    <div className="config-safety"><strong>隐私边界</strong><span>采集 Cookie 仅显示“已配置 / 未配置”。模型密钥只在你提交此表单时传给本机服务，保存后不会回显、写入页面或发送到其他业务接口；不会读取浏览器资料、密码或已有登录会话。</span></div>

    {notice && <div className="notice" role="alert">{notice}</div>}

    <section className="integration-grid" aria-label="平台账号状态">
      {platforms.map((platform) => {
        const configured = accounts?.[platform.id];
        const status = configured === undefined ? "暂未检查" : configured ? "已配置" : "未配置";
        return <article className="panel integration-card" key={platform.id}>
          <div className="section-top"><div><h2>{platform.name}</h2><p>{platform.description}</p></div><span className={`config-status ${configured === undefined ? "config-status-unknown" : configured ? "config-status-ready" : "config-status-missing"}`}>{status}</span></div>
          <dl className="config-meta"><div><dt>所需变量</dt><dd><code>{platform.variable}</code></dd></div><div><dt>使用方式</dt><dd>仅传给本机采集子进程</dd></div></dl>
        </article>;
      })}
      <article className="panel integration-card">
        <div className="section-top"><div><h2>AI 模型</h2><p>用于手动触发的潜客 AI 分析。</p></div><span className={`config-status ${providers?.deepseek === undefined ? "config-status-unknown" : providers.deepseek.configured ? "config-status-ready" : "config-status-missing"}`}>{providers?.deepseek === undefined ? "暂未检查" : providers.deepseek.configured ? "已配置" : "未配置"}</span></div>
        <dl className="config-meta"><div><dt>当前模型</dt><dd><code>{providers?.deepseek.model ?? "—"}</code></dd></div><div><dt>调用方式</dt><dd>仅在手动点击分析时由本机服务调用</dd></div></dl>
      </article>
    </section>

    <section className="panel setup-panel">
      <div className="section-top"><div><h2>AI 模型配置</h2><p>支持 DeepSeek 与兼容 Chat Completions 的 HTTPS 服务。保存后立即用于后续手动分析，不会自动发起模型请求。</p></div></div>
      <form className="model-config-form" onSubmit={saveModelConfig}>
        <label>API 基础地址<input aria-label="模型 API 基础地址" required maxLength={400} inputMode="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.deepseek.com" /></label>
        <label>模型名<input aria-label="模型名" required maxLength={100} value={model} onChange={(event) => setModel(event.target.value)} placeholder="deepseek-flash" /></label>
        <label className="model-key-field">API Key <span>留空将保留已保存的 Key</span><input ref={apiKeyRef} aria-label="模型 API Key" type="password" autoComplete="off" maxLength={2048} disabled={clearApiKey} placeholder={providers?.deepseek.configured ? "已配置，输入新 Key 才会替换" : "输入你的 DeepSeek API Key"} /></label>
        <label className="model-clear-key"><input type="checkbox" checked={clearApiKey} onChange={(event) => setClearApiKey(event.target.checked)} /> 清除已保存的 API Key</label>
        <div className="model-config-actions"><button className="primary" disabled={saving || loading}>{saving ? "保存中…" : "保存模型配置"}</button><span>Key 只写入本机 <code>.env.local</code>，响应不会回传。</span></div>
      </form>
    </section>

    <section className="panel setup-panel">
      <div className="section-top"><div><h2>手动配置小红书 Cookie</h2><p>配置完成后，重新检查状态即可继续创建小红书采集任务。</p></div></div>
      <ol className="setup-list">
        <li>在你自己的浏览器中正常访问小红书，并自行决定是否使用该账号的 Cookie。工作台不会读取浏览器 Cookie、密码、会话或个人资料。</li>
        <li>在项目根目录创建或编辑 <code>.env.local</code>。首次使用时，可从 <code>.env.example</code> 复制一份；把你手动取得的完整 Cookie 填在 <code>XHS_ACCOUNT_COOKIE</code> 后面。不要将该文件提交到版本库，也不要把 Cookie 粘贴到本页面。</li>
        <li>停止并重新启动本机采集服务，让它重新读取环境变量：<pre className="config-code"><code>set -a; source .env.local; set +a{`\n`}python3 -m crawler_bridge.server</code></pre></li>
        <li>回到这里点击“重新检查”。显示“已配置”只表示本机服务检测到变量，不会验证账号是否可用或触发任何平台登录。</li>
      </ol>
    </section>

    <section className="panel privacy-panel">
      <h2>采集时的账号边界</h2>
      <p>采集器只使用你手动设置在本机服务环境中的 Cookie，并以临时、非持久化的浏览器上下文运行。不会获取二维码、短信或密码，也不会读取系统浏览器的个人资料目录。</p>
    </section>
  </Shell>;
}
