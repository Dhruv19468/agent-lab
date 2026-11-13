// One small fetch wrapper for every backend call. All URLs are relative (/api/...):
// Vite (dev) and nginx (Docker) forward them to FastAPI.

export const BASE = `${import.meta.env.VITE_API_BASE_URL ?? ""}/api`;

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

interface ValidationIssue {
  loc?: unknown[];
  msg?: string;
}

async function readError(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json();
    const detail = (data as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      // FastAPI 422: [{loc: ["body", "name"], msg: "..."}]
      return (detail as ValidationIssue[])
        .map((issue) => {
          const field = (issue.loc ?? []).slice(1).join(".");
          return field ? `${field}: ${issue.msg ?? "invalid"}` : (issue.msg ?? "invalid");
        })
        .join("; ");
    }
  } catch {
    // body wasn't JSON
  }
  return `Request failed with status ${response.status}.`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Can't reach the backend. Check that it is running on port 8080.");
  }
  if (!response.ok) throw new ApiError(response.status, await readError(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  /** Some DELETEs answer 204 (no body), others return the updated object (detach skill/tool). */
  delete: <T = void>(path: string) => request<T>("DELETE", path),
};

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}
