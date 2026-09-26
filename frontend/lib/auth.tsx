"use client";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "./api";
import type { AuthResponse, Role, User } from "./types";

export const HOME_FOR_ROLE: Record<Role, string> = {
  RESTAURANT: "/restaurant/dashboard",
  DRIVER: "/driver/dashboard",
  ORGANIZATION: "/organization/dashboard",
  ADMIN: "/admin/dashboard",
};

interface AuthState {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<User>;
  signup: (body: Record<string, unknown>) => Promise<User>;
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

  const login = useCallback(
    async (email: string, password: string) => accept(await api<AuthResponse>("/auth/login", { method: "POST", body: { email, password } })),
    [accept],
  );
  const signup = useCallback(
    async (body: Record<string, unknown>) => accept(await api<AuthResponse>("/auth/signup", { method: "POST", body })),
    [accept],
  );
  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return <AuthContext.Provider value={{ user, ready, login, signup, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

// Guard a page by role: sends logged out visitors to /login and other roles to their own dashboard.
export function useRequireRole(role: Role): User | null {
  const { user, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!ready) return;
    if (!user) router.replace("/login");
    else if (user.role !== role) router.replace(HOME_FOR_ROLE[user.role]);
  }, [ready, user, role, router]);
  return user && user.role === role ? user : null;
}
