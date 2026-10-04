import type {
  Example,
  ReactionInfo,
  SimulationInputs,
  Task,
  User,
  TaskHistory,
  SelectionPreview,
} from "./types";

let csrfToken = "";
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 20_000);
  try {
    const response = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 && path !== "/login" && path !== "/session")
        window.dispatchEvent(new Event("session-expired"));
      throw new ApiError(
        response.status,
        typeof data.detail === "string"
          ? data.detail
          : "请求未成功，请稍后重试",
      );
    }
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new Error("暂时无法连接服务，请确认服务已启动后重试。");
  } finally {
    window.clearTimeout(timer);
  }
}
async function session(path: string, body?: unknown) {
  const data = await request<{ user: User; csrf: string }>(
    path,
    body ? "POST" : "GET",
    body,
  );
  csrfToken = data.csrf;
  return data.user;
}
export const api = {
  session: () => session("/session"),
  login: (username: string, password: string) =>
    session("/login", { username, password }),
  logout: async () => {
    await request("/logout", "POST");
    csrfToken = "";
  },
  examples: () => request<Example[]>("/examples"),
  tasks: () => request<Task[]>("/tasks"),
  history: (q: string, page: number) =>
    request<TaskHistory>(
      `/task-history?${new URLSearchParams({ q, page: String(page), page_size: "20" })}`,
    ),
  preview: (info: ReactionInfo) =>
    request<SelectionPreview>("/selection-preview", "POST", info),
  task: (id: string) => request<Task>(`/tasks/${encodeURIComponent(id)}`),
  analyze: (query: string, key: string, example?: Example) =>
    request<Task>("/tasks", "POST", {
      query,
      idempotency_key: key,
      ...(example
        ? {
            reaction_info: example.reaction_info,
            simulation_inputs: example.simulation_inputs,
          }
        : {}),
    }),
  run: (
    id: string,
    reaction_info: ReactionInfo,
    simulation_inputs: SimulationInputs,
    key: string,
  ) =>
    request<Task>(`/tasks/${encodeURIComponent(id)}/run`, "POST", {
      reaction_info,
      simulation_inputs,
      idempotency_key: key,
    }),
  resume: (id: string) =>
    request<Task>(`/tasks/${encodeURIComponent(id)}/resume`, "POST"),
  explain: (id: string) =>
    request<Task>(`/tasks/${encodeURIComponent(id)}/explain`, "POST"),
};
