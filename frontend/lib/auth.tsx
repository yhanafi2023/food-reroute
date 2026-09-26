"use client";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "./api";
import type { AuthResponse, Role, User } from "./types";

// Password of every demo account (DEMO_PASSWORD in backend/app/seed.py). The backend accepts
// demo accounts only while DEMO_MODE is on.
export const DEMO_PASSWORD = "demo1234";
// Mirrors PASSWORD_MIN_LENGTH in backend/app/auth.py, which enforces it.
export const PASSWORD_MIN_LENGTH = 8;

export const HOME_FOR_ROLE: Record<Role, string> = {
  restaurant_staff: "/restaurant/dashboard",
  restaurant_manager: "/restaurant/dashboard",
  volunteer: "/volunteer/dashboard",
  org_staff: "/organization/dashboard",
  org_manager: "/organization/dashboard",
  admin: "/admin/dashboard",
};

type RegisterPath = "/auth/register-organization" | "/auth/register-volunteer";

interface AuthState {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (path: RegisterPath, body: Record<string, unknown>) => Promise<User>;
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
  // Registering signs the new account in: the response carries a session, like /auth/login.
  const register = useCallback(
    async (path: RegisterPath, body: Record<string, unknown>) => accept(await api<AuthResponse>(path, { method: "POST", body })),
    [accept],
  );
  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, ready, login, register, logout }}>
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
