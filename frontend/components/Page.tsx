"use client";
import type { ReactNode } from "react";
import type { Workspace } from "@/lib/types";
import { Shell } from "./Shell";

// Title + subtitle page frame on the shared Shell (replaces the old AppShell wrapper).
export default function Page({ workspace, title, subtitle, actions, children }: {
  workspace?: Workspace;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Shell workspace={workspace}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-end" }}>
        <div className="stack" style={{ gap: "var(--s-2)" }}>
          <h1>{title}</h1>
          {subtitle ? <p style={{ maxWidth: "62ch", color: "var(--ink-2)" }}>{subtitle}</p> : null}
        </div>
        {actions}
      </div>
      {children}
    </Shell>
  );
}
