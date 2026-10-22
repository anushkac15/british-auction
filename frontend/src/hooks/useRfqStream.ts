import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../api/client";

/**
 * Optional live updates over server-sent events. Each `changed` event just triggers a
 * refetch of the role-shaped details; polling remains the fallback if SSE is unavailable.
 */
export function useRfqStream(rfqId: number, enabled: boolean): boolean {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") {
      setConnected(false);
      return;
    }
    const source = new EventSource(api.streamUrl(rfqId));
    source.addEventListener("ready", () => setConnected(true));
    source.addEventListener("changed", () => {
      void queryClient.invalidateQueries({ queryKey: ["rfq", rfqId] });
      void queryClient.invalidateQueries({ queryKey: ["rfqs"] });
    });
    source.onerror = () => setConnected(false);
    return () => {
      source.close();
      setConnected(false);
    };
  }, [rfqId, enabled, queryClient]);

  return connected;
}
