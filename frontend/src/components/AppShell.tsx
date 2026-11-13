import { Bot, BookOpen, Gauge, Wrench } from "lucide-react";
import { Link, NavLink, Outlet } from "react-router";

import { useHealth } from "../lib/queries";
import { cx } from "./ui";

const NAV = [
  { to: "/", label: "Overview", icon: Gauge, end: true },
  { to: "/agents", label: "Agents", icon: Bot, end: false },
  { to: "/skills", label: "Skills", icon: BookOpen, end: false },
  { to: "/tools", label: "Tools", icon: Wrench, end: false },
];

/** The Agent Lab mark: a hexagon (the lab) holding an agent connected to three tools. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={className} role="img" aria-label="Agent Lab">
      <path
        d="M20 2.5 35.2 11.25v17.5L20 37.5 4.8 28.75v-17.5Z"
        fill="#22314f"
        stroke="#e3a008"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <g stroke="#c9d2e3" strokeWidth="1.6" strokeLinecap="round">
        <path d="M20 21 20 12.2" />
        <path d="M20 21 12.4 25.6" />
        <path d="M20 21 27.6 25.6" />
      </g>
      <circle cx="20" cy="11.6" r="3" fill="#e3a008" />
      <circle cx="11.9" cy="25.9" r="2.6" fill="#8a9ab8" />
      <circle cx="28.1" cy="25.9" r="2.6" fill="#ffffff" />
      <circle cx="20" cy="21" r="3.4" fill="#ffffff" stroke="#22314f" strokeWidth="1.2" />
    </svg>
  );
}

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5 rounded-md">
      <LogoMark className="size-9 shrink-0" />
      <div className="leading-tight">
        <p className="text-[15px] font-semibold tracking-[-0.01em] text-white">Agent Lab</p>
        <p className="text-[11px] text-ink-400">Test intelligence</p>
      </div>
    </Link>
  );
}

function BackendStatus() {
  const health = useHealth();
  const apiUp = health.isSuccess;
  const dbUp = health.data?.database === "ok";
  const label = health.isPending ? "Checking backend…" : !apiUp ? "Backend offline" : dbUp ? "Backend and database up" : "Database unreachable";
  return (
    <div className="flex items-center gap-2 text-xs text-ink-400" title="Checked every 15 seconds via /api/health">
      <span
        aria-hidden
        className={cx("size-2 rounded-full", health.isPending ? "bg-ink-500" : apiUp && dbUp ? "bg-ok-600" : apiUp ? "bg-signal-500" : "bg-bad-600")}
      />
      {label}
    </div>
  );
}

export function AppShell() {
  return (
    <div className="min-h-screen md:flex">
      <aside className="flex shrink-0 flex-col gap-4 bg-ink-900 px-4 py-4 md:sticky md:top-0 md:h-screen md:w-56 md:gap-8 md:px-5 md:py-6">
        <Logo />
        <nav aria-label="Main" className="-mx-1 flex gap-1 overflow-x-auto md:mx-0 md:flex-col">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cx(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-[14px] whitespace-nowrap transition-colors",
                  isActive ? "bg-ink-800 font-medium text-white shadow-[inset_3px_0_0_var(--color-signal-500)]" : "text-ink-200 hover:bg-ink-800/60 hover:text-white",
                )
              }
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="hidden md:mt-auto md:block">
          <BackendStatus />
          <a href="/docs" target="_blank" rel="noreferrer" className="mt-3 block text-xs text-ink-400 underline-offset-2 hover:text-white hover:underline">
            API reference
          </a>
        </div>
      </aside>
      <main className="min-w-0 flex-1">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 md:px-8 md:py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
