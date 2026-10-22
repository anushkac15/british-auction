import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { useCurrentUser } from "./useCurrentUser";

export function useRfqList() {
  const { user } = useCurrentUser();
  return useQuery({
    queryKey: ["rfqs", user?.id],
    queryFn: api.listRfqs,
    enabled: !!user,
    refetchInterval: 5000,
  });
}
