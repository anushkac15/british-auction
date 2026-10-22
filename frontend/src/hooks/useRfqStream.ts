import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, authHeaders } from "../api/client";

const RETRY_MS = 5000;

/**
 * Optional live updates over server-sent events. Each `changed` event just triggers a
 * refetch of the role-shaped details; polling remains the fallback if SSE is unavailable.
 * Read with fetch rather than EventSource, which can't send the Authorization header.
 */
export function useRfqStream(rfqId: number, enabled: boolean): boolean {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!enabled) {
      setConnected(false);
      return;
    }
    const controller = new AbortController();
    let retry: ReturnType<typeof setTimeout> | undefined;

    const handle = (block: string) => {
      const event = block
        .split("\n")
        .find((line) => line.startsWith("event:"))
        ?.slice("event:".length)
        .trim();
      if (event === "ready") setConnected(true);
      if (event === "changed") {
        void queryClient.invalidateQueries({ queryKey: ["rfq", rfqId] });
        void queryClient.invalidateQueries({ queryKey: ["rfqs"] });
      }
    };

    async function connect() {
      let retryable = true;
      try {
        const res = await fetch(api.streamUrl(rfqId), {
          headers: { Accept: "text/event-stream", ...authHeaders() },
          signal: controller.signal,
        });
        if (!res.ok || !res.body) {
          // 401/404 won't fix themselves; REST polling handles logout and missing RFQs.
          retryable = res.status >= 500;
          return;
        }
        const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += value.replace(/\r\n/g, "\n");
          let end: number;
          while ((end = buffer.indexOf("\n\n")) >= 0) {
            handle(buffer.slice(0, end));
            buffer = buffer.slice(end + 2);
          }
        }
      } catch {
        // Network error or abort; handled below.
      } finally {
        setConnected(false);
        if (retryable && !controller.signal.aborted) retry = setTimeout(connect, RETRY_MS);
      }
    }

    void connect();
    return () => {
      controller.abort();
      clearTimeout(retry);
      setConnected(false);
    };
  }, [rfqId, enabled, queryClient]);

  return connected;
}
