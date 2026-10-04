#!/usr/bin/env bash
# 启动本机采集服务（crawler_bridge.server）
#
# 用法：
#   ./scripts/start_crawler.sh              前台启动，Ctrl-C 停止
#   ./scripts/start_crawler.sh --check      只检查状态，不启动
#
# 注意：本机 shell 常设置 HTTP_PROXY，Node/curl 请求回环地址会走代理导致
# 连接失败，因此这里显式设置 NO_PROXY。

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export NO_PROXY="127.0.0.1,localhost,::1"
export no_proxy="$NO_PROXY"

HOST="${CRAWLER_HOST:-127.0.0.1}"
PORT="${CRAWLER_PORT:-8765}"

check() {
  if curl -sf --noproxy '*' --max-time 3 "http://$HOST:$PORT/health" >/dev/null 2>&1; then
    echo "✅ 采集服务已在运行：http://$HOST:$PORT"
    curl -s --noproxy '*' --max-time 3 "http://$HOST:$PORT/health"; echo
    return 0
  fi
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "⚠️  端口 $PORT 被其他进程占用，但不是健康的采集服务。"
    echo "   查看占用进程：lsof -nP -iTCP:$PORT -sTCP:LISTEN"
    return 2
  fi
  echo "ℹ️  采集服务未运行（端口 $PORT 空闲）"
  return 1
}

if [[ "${1:-}" == "--check" ]]; then
  check || true
  exit 0
fi

if check; then
  echo "无需重复启动。若要重启，先执行：lsof -ti tcp:$PORT | xargs kill"
  exit 0
fi

# 载入本地环境变量（.env.local 可能被 gitignore，不存在时用默认值）
if [[ -f .env.local ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.local
  set +a
  echo "已载入 .env.local"
else
  echo "⚠️  未找到 .env.local，使用默认端口配置。可执行 cp .env.example .env.local 创建。"
fi

echo "启动采集服务：http://$HOST:$PORT"
exec python3 -m crawler_bridge.server
