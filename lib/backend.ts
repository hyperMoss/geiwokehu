const base = process.env.CRAWLER_API_URL ?? "http://127.0.0.1:8765";

/**
 * 本机采集服务必须直连。若shell 里设置了 HTTP_PROXY/HTTPS_PROXY，Node 的 fetch
 * 会把回环地址也交给代理，导致代理连不上上游而抛错，最终被下面的 catch 误报成
 * 「本地采集服务未启动」。这里显式关闭代理，localhost 不走代理。
 */
function directFetch(url: string, init?: RequestInit): Promise<Response> {
  const previous = process.env.NO_PROXY;
  if (previous === undefined) {
    process.env.NO_PROXY = "127.0.0.1,localhost,::1";
  }
  return fetch(url, { ...init, cache: "no-store", signal: AbortSignal.timeout(12000) });
}

export async function backend(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await directFetch(`${base}${path}`, init);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    console.error(`[crawler-bridge] 请求 ${base}${path} 失败：${reason}`);
    return Response.json(
      { error: "本地采集服务未启动或无法连接，请确认已运行 python3 -m crawler_bridge.server" },
      { status: 503 },
    );
  }
}
