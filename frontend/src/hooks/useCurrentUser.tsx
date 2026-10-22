import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, api, setApiToken, setUnauthorizedHandler } from "../api/client";
import type { Account, AuthResponse, LoginInput, RegisterInput } from "../api/types";

const TOKEN_KEY = "british-auction:token";

interface CurrentUserValue {
  user: Account | null;
  loading: boolean;
  error: Error | null;
  login: (input: LoginInput) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => void;
}

const CurrentUserContext = createContext<CurrentUserValue | null>(null);

export function CurrentUserProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));

  // Set synchronously so the first queries of a render already carry the token.
  setApiToken(token);

  const meQuery = useQuery({
    queryKey: ["me", token],
    queryFn: api.me,
    enabled: token !== null,
    staleTime: Infinity,
    retry: (count, err) => !(err instanceof ApiError && err.status === 401) && count < 1,
  });

  const startSession = useCallback(
    (session: AuthResponse | null) => {
      queryClient.clear();
      const next = session?.access_token ?? null;
      if (session) {
        localStorage.setItem(TOKEN_KEY, session.access_token);
        queryClient.setQueryData(["me", next], { server_now: session.server_now, user: session.user });
      } else {
        localStorage.removeItem(TOKEN_KEY);
      }
      setApiToken(next);
      setToken(next);
    },
    [queryClient],
  );

  const logout = useCallback(() => startSession(null), [startSession]);
  const login = useCallback(async (input: LoginInput) => startSession(await api.login(input)), [startSession]);
  const register = useCallback(
    async (input: RegisterInput) => startSession(await api.register(input)),
    [startSession],
  );

  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  const user = token ? (meQuery.data?.user ?? null) : null;
  const value = useMemo(
    () => ({
      user,
      loading: token !== null && meQuery.isLoading,
      error: token !== null ? meQuery.error : null,
      login,
      register,
      logout,
    }),
    [user, token, meQuery.isLoading, meQuery.error, login, register, logout],
  );
  return <CurrentUserContext.Provider value={value}>{children}</CurrentUserContext.Provider>;
}

export function useCurrentUser(): CurrentUserValue {
  const value = useContext(CurrentUserContext);
  if (!value) throw new Error("useCurrentUser must be used inside CurrentUserProvider");
  return value;
}
