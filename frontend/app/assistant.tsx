"use client";

import {
  AssistantRuntimeProvider,
  useRemoteThreadListRuntime,
  useLocalRuntime,
  useAuiState,
} from "@assistant-ui/react";
import { Thread } from "@/components/assistant-ui/thread";
import { ThreadListSidebar } from "@/components/assistant-ui/threadlist-sidebar";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { nanodeerAdapter, getSavedThreadId, saveThreadId, setCurrentThreadId } from "@/components/nanodeer-adapter";
import { nanodeerThreadListAdapter } from "@/lib/thread-list-adapter";
import { createHistoryAdapter } from "@/lib/history-adapter";
import { useEffect } from "react";

export const Assistant = () => {
  const runtime = useRemoteThreadListRuntime({
    runtimeHook: () => {
      // Capture current threadId during RENDER phase — before effects run
      // This ensures history.load() gets the correct threadId
      const remoteId = useAuiState((s) => s.threadListItem?.remoteId ?? null);
      if (remoteId) setCurrentThreadId(remoteId);
      return useLocalRuntime(nanodeerAdapter, {
        adapters: { history: createHistoryAdapter() },
      });
    },
    adapter: nanodeerThreadListAdapter,
    threadId: getSavedThreadId() ?? undefined,
  });

  // Sync active thread changes to localStorage
  useEffect(() => {
    const unsub = runtime.threads.subscribe(() => {
      const state = runtime.threads.getState();
      if (state.mainThreadId) {
        saveThreadId(state.mainThreadId);
      }
    });
    return unsub;
  }, [runtime]);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <SidebarProvider>
        <div className="flex h-dvh w-full pr-0.5">
          <ThreadListSidebar className="overflow-hidden rounded-r-xl" />
          <SidebarInset>
            <header className="flex h-16 shrink-0 items-center gap-2 border-b px-4">
              <SidebarTrigger className="rounded-md" />
              <Separator orientation="vertical" className="mr-2 h-4" />
              <span className="font-semibold">NanoDeer</span>
            </header>
            <div className="flex-1 overflow-hidden">
              <Thread />
            </div>
          </SidebarInset>
        </div>
      </SidebarProvider>
    </AssistantRuntimeProvider>
  );
};
