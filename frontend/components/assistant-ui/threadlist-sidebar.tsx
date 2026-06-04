"use client";

import type * as React from "react";
import {
  FolderIcon,
  ListChecksIcon,
  MemoryStickIcon,
  PanelsTopLeftIcon,
} from "lucide-react";
import { GitHubIcon } from "@/components/icons/github";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import { ThreadList } from "@/components/assistant-ui/thread-list";
import { fetchWorkspaceSummary } from "@/lib/api";
import type { WorkspaceSummary } from "@/lib/types";
import { useEffect, useState } from "react";

type WorkspaceSection = "projects" | "plans" | "memory" | "wiki";

function workspaceItems(summary: WorkspaceSummary | null): Array<{
  id: WorkspaceSection;
  label: string;
  icon: typeof FolderIcon;
  value: string;
}> {
  return [
    {
      id: "projects",
      label: "Projects",
      icon: FolderIcon,
      value: summary ? String(summary.projects.count) : "—",
    },
    {
      id: "plans",
      label: "Plans",
      icon: ListChecksIcon,
      value: summary ? `${summary.plans.active}/${summary.plans.count}` : "—",
    },
    {
      id: "memory",
      label: "Memory",
      icon: MemoryStickIcon,
      value: summary ? String(summary.memory.count) : "—",
    },
    {
      id: "wiki",
      label: "Wiki",
      icon: PanelsTopLeftIcon,
      value: summary ? String(summary.wiki.count) : "—",
    },
  ];
}

export function ThreadListSidebar({
  ...props
}: React.ComponentProps<typeof Sidebar>) {
  const [summary, setSummary] = useState<WorkspaceSummary | null>(null);
  const [activeSection, setActiveSection] = useState<WorkspaceSection | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchWorkspaceSummary().then((data) => {
      if (!cancelled) setSummary(data);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Sidebar {...props}>
      <SidebarHeader className="aui-sidebar-header gap-4 p-4 pt-5">
        <div className="space-y-1">
          {workspaceItems(summary).map((item) => (
            <button
              type="button"
              key={item.label}
              onClick={() => setActiveSection((current) => current === item.id ? null : item.id)}
              className="flex h-9 w-full items-center gap-3 rounded-xl px-3 text-left text-[#3c3935] text-sm transition hover:bg-black/5 data-[active=true]:bg-white data-[active=true]:shadow-sm"
              data-active={activeSection === item.id}
            >
              <item.icon className="size-4 text-[#4a4742]" />
              <span className="min-w-0 flex-1 truncate">{item.label}</span>
              <span className="rounded-full bg-black/5 px-2 py-0.5 text-muted-foreground text-xs">
                {item.value}
              </span>
            </button>
          ))}
        </div>
      </SidebarHeader>
      <SidebarContent className="aui-sidebar-content px-4">
        {activeSection ? (
          <WorkspacePanel section={activeSection} summary={summary} />
        ) : (
          <ThreadList />
        )}
      </SidebarContent>
      <SidebarRail />
      <SidebarFooter className="aui-sidebar-footer p-4">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <a
                href="https://github.com/gzhzk/nanodeer"
                target="_blank"
                rel="noopener noreferrer"
              >
                <div className="aui-sidebar-footer-icon-wrapper flex aspect-square size-8 items-center justify-center rounded-xl bg-[#4f7466]/15 text-[#4f7466]">
                  <GitHubIcon className="aui-sidebar-footer-icon size-4" />
                </div>
                <div className="aui-sidebar-footer-heading flex flex-col gap-0.5 leading-none">
                  <span className="aui-sidebar-footer-title font-semibold">
                    Repository
                  </span>
                  <span>gzhzk/nanodeer</span>
                </div>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}

function WorkspacePanel({
  section,
  summary,
}: {
  section: WorkspaceSection;
  summary: WorkspaceSummary | null;
}) {
  if (!summary) {
    return (
      <div className="rounded-2xl border border-black/10 bg-white/70 p-3 text-muted-foreground text-sm">
        Loading workspace…
      </div>
    );
  }

  if (section === "projects") {
    return (
      <PanelShell title="Projects">
        {summary.projects.items.length === 0 ? (
          <EmptyPanel text="No project entries yet." />
        ) : (
          summary.projects.items.map((item) => (
            <PanelItem key={item.path} title={item.title} subtitle={item.summary || item.path} />
          ))
        )}
      </PanelShell>
    );
  }

  if (section === "plans") {
    return (
      <PanelShell title="Plans">
        {summary.plans.items.length === 0 ? (
          <EmptyPanel text="No plans yet." />
        ) : (
          summary.plans.items.map((plan) => (
            <PanelItem
              key={plan.plan_id}
              title={plan.title || plan.goal || plan.plan_id}
              subtitle={`${plan.status} · ${plan.steps.length} steps`}
            />
          ))
        )}
      </PanelShell>
    );
  }

  if (section === "memory") {
    return (
      <PanelShell title="Memory">
        <PanelItem
          title="User memory"
          subtitle={summary.memory.has_user ? "Available" : "Empty"}
        />
        <PanelItem
          title="Flat memory"
          subtitle={summary.memory.has_memory ? "Available" : "Empty"}
        />
        <PanelItem
          title="Episodic days"
          subtitle={`${summary.memory.episodic_days} files`}
        />
      </PanelShell>
    );
  }

  return (
    <PanelShell title="Wiki">
      {summary.wiki.items.length === 0 ? (
        <EmptyPanel text="No wiki entries yet." />
      ) : (
        summary.wiki.items.map((item) => (
          <PanelItem key={item.path} title={item.title} subtitle={item.summary || item.path} />
        ))
      )}
    </PanelShell>
  );
}

function PanelShell({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between px-3 pb-1">
        <h2 className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
          {title}
        </h2>
      </div>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function PanelItem({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="rounded-2xl border border-black/10 bg-white/75 p-3 shadow-sm">
      <div className="truncate font-medium text-[#262421] text-sm">{title}</div>
      <div className="mt-1 line-clamp-2 text-muted-foreground text-xs">{subtitle}</div>
    </div>
  );
}

function EmptyPanel({ text }: { text: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-black/15 bg-white/45 p-3 text-muted-foreground text-sm">
      {text}
    </div>
  );
}
