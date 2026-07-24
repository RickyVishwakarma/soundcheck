"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";

interface AuthState {
  email: string | null;
  ready: boolean; // false until the initial token check resolves
  signup: (email: string, password: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [email, setEmail] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  // Validate any stored token on load — it may have expired since last visit.
  useEffect(() => {
    if (!getToken()) {
      setReady(true);
      return;
    }
    api
      .me()
      .then((r) => setEmail(r.authenticated ? r.email : null))
      .catch(() => setEmail(null))
      .finally(() => setReady(true));
  }, []);

  const signup = useCallback(async (e: string, p: string) => {
    const r = await api.signup(e, p);
    setToken(r.token);
    setEmail(r.email);
  }, []);

  const login = useCallback(async (e: string, p: string) => {
    const r = await api.login(e, p);
    setToken(r.token);
    setEmail(r.email);
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setEmail(null);
  }, []);

  return (
    <Ctx.Provider value={{ email, ready, signup, login, logout }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used within AuthProvider");
  return v;
}
