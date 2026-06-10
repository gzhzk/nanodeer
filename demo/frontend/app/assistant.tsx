"use client";

import {
  AssistantRuntimeProvider,
  SimpleImageAttachmentAdapter,
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

const imageAttachmentAdapter = new SimpleImageAttachmentAdapter();

function useNanoDeerRuntime() {
  // Capture current threadId during render so history.load() gets the active thread.
  const remoteId = useAuiState((s) => s.threadListItem?.remoteId ?? null);
  if (remoteId) setCurrentThreadId(remoteId);
  return useLocalRuntime(nanodeerAdapter, {
    adapters: {
      history: createHistoryAdapter(),
      attachments: imageAttachmentAdapter,
    },
  });
}

export const Assistant = () => {
  const runtime = useRemoteThreadListRuntime({
    runtimeHook: useNanoDeerRuntime,
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
        <div className="flex h-dvh w-full bg-[#f7f6f3] p-3 text-[#262421]">
          <ThreadListSidebar variant="floating" className="overflow-hidden" />
          <SidebarInset className="overflow-hidden rounded-[1.75rem] bg-transparent shadow-none">
            <header className="flex h-14 shrink-0 items-center justify-between px-4">
              <div className="flex items-center gap-2">
                <SidebarTrigger className="rounded-lg" />
                <Separator orientation="vertical" className="mx-1 h-5 bg-black/10" />
              </div>
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
