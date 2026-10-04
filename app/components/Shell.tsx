import Link from "next/link";
import type { ReactNode } from "react";

type IconName = "search" | "radar" | "users" | "chart" | "plug" | "file" | "menu" | "moon" | "bell" | "chevron";

function Icon({ name }: { name: IconName }) {
  const common = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  const paths: Record<IconName, ReactNode> = {
    search: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4 4" /></>,
    radar: <><circle cx="12" cy="12" r="8" /><path d="M12 4v8l5 3" /><path d="M4 12h2M18 12h2" /></>,
    users: <><path d="M16 20v-1.5a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4V20" /><circle cx="9.5" cy="7" r="3.5" /><path d="M17 4.5a3.5 3.5 0 0 1 0 6.8M21 20v-1.5a4 4 0 0 0-2.6-3.75" /></>,
    chart: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></>,
    plug: <><path d="M8 8V4M12 8V4M7 8h6v3a3 3 0 0 1-3 3v6" /><path d="M17 15h3v4a2 2 0 0 1-2 2h-1v-6Z" /></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 13h8M8 17h6" /></>,
    menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
    moon: <path d="M20.5 15.4A8 8 0 0 1 8.6 3.5 8.1 8.1 0 1 0 20.5 15.4Z" />,
    bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 22h4" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
  };
  return <svg {...common}>{paths[name]}</svg>;
}

const navigation = [
  { href: "/", label: "关键词获客", icon: "radar" as const },
  { href: "/leads", label: "潜客筛选", icon: "users" as const },
  { href: "/customers", label: "客户管理", icon: "users" as const },
  { href: "/analytics/lead", label: "获客分析", icon: "chart" as const },
  { href: "/integrations", label: "集成配置", icon: "plug" as const },
];

function Navigation({ active }: { active: string }) {
  return <>
    {navigation.map((entry) => (
      <Link key={entry.href} href={entry.href} className={active === entry.href ? "nav-active" : "nav-muted"}>
        <Icon name={entry.icon} />
        <span>{entry.label}</span>
      </Link>
    ))}
    <span className="nav-muted nav-disabled" aria-disabled="true">
      <Icon name="file" />
      <span>内容运营</span>
      <small>即将接入</small>
    </span>
  </>;
}

export function Shell({ active, title, children }: { active: string; title: string; children: ReactNode }) {
  return <div className="shell">
    <aside className="sidebar">
      <Link className="brand" href="/">
        <span className="brand-icon">AI</span>
        <span className="brand-copy"><strong>AI Growth Ops</strong><small>GROWTH WORKSPACE</small></span>
      </Link>
      <nav className="sidebar-nav" aria-label="主导航">
        <span className="nav-label">业务工作台</span>
        <Navigation active={active} />
      </nav>
      <div className="sidebar-foot">
        <span className="workspace-state"><i />本地服务已连接</span>
        <span>MediaCrawler · 抖音 / 小红书</span>
        <span className="collapse-hint">收起侧栏 <Icon name="chevron" /></span>
      </div>
    </aside>
    <main className="main">
      <header className="topbar">
        <details className="mobile-nav">
          <summary aria-label="打开导航"><Icon name="menu" /></summary>
          <nav><Navigation active={active} /></nav>
        </details>
        <label className="global-search">
          <Icon name="search" />
          <input aria-label="全局搜索" placeholder="搜索任务、潜客或客户…" />
          <kbd>⌘ K</kbd>
        </label>
        <div className="topbar-actions">
          <span className="route-name">{title}</span>
          <span className="live-status"><i />Live</span>
          <span className="topbar-icon"><Icon name="moon" /></span>
          <span className="topbar-icon"><Icon name="bell" /></span>
          <span className="user-avatar">GO</span>
        </div>
      </header>
      <div className="content">{children}</div>
    </main>
  </div>;
}
