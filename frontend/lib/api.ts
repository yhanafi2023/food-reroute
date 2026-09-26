// Typed fetch wrapper: attaches the JWT, throws readable errors, and serves mocks
// when NEXT_PUBLIC_USE_MOCKS=true so frontend work never waits on the backend.
import { mockRequest } from "./mock";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "true";
const TOKEN_KEY = "foodflow_token";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export function getToken(): string | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // storage blocked: the session lasts until the tab closes
  }
}

function readableDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // pydantic validation errors: [{loc: [..., "field"], msg}]
    return detail
      .map((d: { loc?: (string | number)[]; msg?: string }) => {
        const field = d.loc?.[d.loc.length - 1];
        const msg = (d.msg ?? "is invalid").replace(/^Value error, /, "");
        return field ? `${String(field).replace(/_/g, " ")}: ${msg}` : msg;
      })
      .join(". ");
  }
  return "Something went wrong";
}

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const method = options.method ?? "GET";
  if (USE_MOCKS) return mockRequest<T>(method, path, options.body);

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError(`Cannot reach the FoodFlow server at ${API_URL}. Is the backend running?`, 0);
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail;
    } catch {
      // not JSON
    }
    throw new ApiError(readableDetail(detail), res.status);
  }
  return (await res.json()) as T;
}
