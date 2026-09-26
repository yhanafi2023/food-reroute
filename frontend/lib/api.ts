// Typed fetch wrapper: attaches the JWT and throws readable errors. Talks to the real
// FastAPI backend; DEMO_MODE there seeds deterministic demo accounts and history
// (backend/app/seed.py) so there is no separate frontend mock layer to keep in sync.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
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

export const REQUEST_TIMEOUT_MS = 15000;

export function isAbort(e: unknown): boolean {
  return e instanceof DOMException && e.name === "AbortError";
}

// `signal` cancels the request (navigation, a newer search, the user pressing Cancel).
// Every request also times out after REQUEST_TIMEOUT_MS so a dead connection never hangs the UI.
export async function api<T>(path: string, options: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), REQUEST_TIMEOUT_MS);
  const signal = options.signal ? AbortSignal.any([options.signal, timeout.signal]) : timeout.signal;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal,
    });
  } catch (e) {
    clearTimeout(timer);
    if (options.signal?.aborted) throw e; // cancelled by the caller: not an error to show
    if (timeout.signal.aborted) throw new ApiError("The server took too long to answer. Check your connection and try again.", 0);
    throw new ApiError(`Cannot reach the FoodFlow server at ${API_URL}. Check your connection; FoodFlow will keep retrying.`, 0);
  }
  clearTimeout(timer);
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
