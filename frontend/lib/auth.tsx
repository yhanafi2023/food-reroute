"use client";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "./api";
import type { AuthResponse, Role, User } from "./types";

// Demo accounts (backend/app/seed.py) may sign in with this fixed code while DEMO_MODE is on,
// without requesting a real one-time code first. Never works for a non-demo account.
export const DEMO_CODE = "246810";

export const HOME_FOR_ROLE: Record<Role, string> = {
  restaurant_staff: "/restaurant/dashboard",
  restaurant_manager: "/restaurant/dashboard",
  volunteer: "/volunteer/dashboard",
  org_staff: "/organization/dashboard",
  org_manager: "/organization/dashboard",
  admin: "/admin/dashboard",
};

interface AuthState {
  user: User | null;
  ready: boolean;
  requestCode: (email: string) => Promise<void>;
  verifyCode: (email: string, code: string) => Promise<User>;
  verifyToken: (token: string) => Promise<User>;
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

  const requestCode = useCallback(
    async (email: string) => { await api<{ ok: boolean }>("/auth/request-code", { method: "POST", body: { email } }); },
    [],
  );
  const verifyCode = useCallback(
    async (email: string, code: string) => accept(await api<AuthResponse>("/auth/verify", { method: "POST", body: { email, code } })),
    [accept],
  );
  const verifyToken = useCallback(
    async (token: string) => accept(await api<AuthResponse>("/auth/verify", { method: "POST", body: { token } })),
    [accept],
  );
  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, ready, requestCode, verifyCode, verifyToken, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

// Guard a page by role (one role, or any of several): sends logged out visitors to /login
// and users of a different role to their own dashboard.
export function useRequireRole(role: Role | Role[]): User | null {
  const allowed = Array.isArray(role) ? role : [role];
  const { user, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!ready) return;
    if (!user) router.replace("/login");
    else if (!allowed.includes(user.role)) router.replace(HOME_FOR_ROLE[user.role]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, user, router, allowed.join(",")]);
  return user && allowed.includes(user.role) ? user : null;
}
