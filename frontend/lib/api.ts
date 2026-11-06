export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem("token", token);
  else localStorage.removeItem("token");
}

type Options = Omit<RequestInit, "body"> & { json?: unknown; body?: BodyInit };

async function request(path: string, opts: Options = {}): Promise<Response> {
  const headers = new Headers(opts.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = opts.body;
  if (opts.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(opts.json);
  }
  const res = await fetch(`${API_URL}/api${path}`, { ...opts, headers, body });
  if (res.status === 401 && !path.startsWith("/auth/login")) {
    setToken(null);
    if (window.location.pathname !== "/login") window.location.href = "/login";
  }
  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail))
        message = data.detail.map((d: { loc?: string[]; msg: string }) => `${d.loc?.slice(1).join(".")}: ${d.msg}`).join("; ");
    } catch {
      /* not JSON */
    }
    throw new ApiError(message, res.status);
  }
  return res;
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const res = await request(path, opts);
  return (await res.json()) as T;
}

export async function downloadFile(path: string, fallbackName: string) {
  const res = await request(path);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="([^"]+)"/);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = match?.[1] ?? fallbackName;
  a.click();
  URL.revokeObjectURL(url);
}

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
