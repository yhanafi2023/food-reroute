"use client";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "./api";
import type { AuthResponse, Role, User, Workspace } from "./types";

export const WORKSPACE_FOR_ROLE: Record<Role, Workspace> = {
  restaurant_staff: "restaurant",
  restaurant_manager: "restaurant",
  volunteer: "volunteer",
  org_staff: "org",
  org_manager: "org",
  admin: "coordinator",
};

export const HOME: Record<Workspace, string> = {
  restaurant: "/restaurant",
  volunteer: "/volunteer",
  org: "/org",
  coordinator: "/coordinator",
};

interface AuthState {
  user: User | null;
  ready: boolean;
  requestCode: (email: string) => Promise<void>;
  verifyCode: (email: string, code: string) => Promise<User>;
  demoSignin: (persona: Workspace) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const restore = async () => {
      if (!getToken()) return null;
      try {
        return await api<User>("/auth/me");
      } catch {
        setToken(null);
        return null;
      }
    };
    restore().then((u) => {
      if (cancelled) return;
      setUser(u);
      setReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const accept = useCallback((res: AuthResponse) => {
    setToken(res.token);
    setUser(res.user);
    return res.user;
  }, []);

  const requestCode = useCallback(async (email: string) => {
    await api("/auth/request-code", { method: "POST", body: { email } });
  }, []);
  const verifyCode = useCallback(
    async (email: string, code: string) => accept(await api<AuthResponse>("/auth/verify", { method: "POST", body: { email, code } })),
    [accept],
  );
  const demoSignin = useCallback(
    async (persona: Workspace) => accept(await api<AuthResponse>("/demo/signin", { method: "POST", body: { persona } })),
    [accept],
  );
  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, ready, requestCode, verifyCode, demoSignin, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

// Guard a workspace: signed out visitors go to /login, other roles to their own workspace.
export function useWorkspace(ws: Workspace): User | null {
  const { user, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!ready) return;
    if (!user) router.replace(`/login?next=${HOME[ws]}`);
    else if (WORKSPACE_FOR_ROLE[user.role] !== ws) router.replace(HOME[WORKSPACE_FOR_ROLE[user.role]]);
  }, [ready, user, ws, router]);
  return user && WORKSPACE_FOR_ROLE[user.role] === ws ? user : null;
}
