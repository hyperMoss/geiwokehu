import type { Metadata } from "next";
import "./styles.css";
import "./feature.css";

export const metadata: Metadata = {
  title: "AI Growth Ops · 获客工作台",
  description: "采集、潜客复核、客户管理与获客分析",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
