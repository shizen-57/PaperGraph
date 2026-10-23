"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [["/space", "Space"], ["/ask", "Ask"], ["/docs", "Documents"], ["/compare", "Compare"], ["/graph", "Graph"], ["/eval", "Evaluation"]];

export default function Nav() {
  const path = usePathname();
  if (path === "/") return null;
  return (
    <header className="tb">
      <Link className="tb-brand" href="/" aria-label="DocLens home">
        <svg className="tb-mark" viewBox="0 0 34 34" aria-hidden="true">
          <circle cx="17" cy="17" r="17" fill="#9C86CE" />
          <circle cx="17" cy="17" r="8.6" fill="#FFFFFF" />
          <circle cx="17" cy="17" r="3.7" fill="#151519" />
        </svg>
        <span className="tb-word">DocLens</span>
      </Link>
      <nav className="tb-links" aria-label="Main">
        {LINKS.map(([href, label]) => (
          <Link key={href} href={href} aria-current={path.startsWith(href) ? "page" : undefined}>{label}</Link>
        ))}
      </nav>
      <Link className="tb-cta" href="/ask">Ask a question</Link>
    </header>
  );
}
