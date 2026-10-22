import type {
  CourtSide,
  CreateProjectInput,
  ExportRecord,
  PlayerKey,
  Project,
  ProjectSummary,
} from "../types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
    ...init,
  });
  if (!response.ok) {
    let message = `请求失败 (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep the status-based message.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  listProjects: () => request<ProjectSummary[]>("/api/projects"),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  importPath: (path: string, input: CreateProjectInput) =>
    request<Project>("/api/projects/import-path", {
      method: "POST",
      body: JSON.stringify({ ...input, path, first_server_court: input.first_server_court || null }),
    }),
  upload: (file: File, input: CreateProjectInput) => {
    const form = new FormData();
    form.append("video", file);
    Object.entries(input).forEach(([key, value]) => form.append(key, String(value)));
    return request<Project>("/api/projects/upload", { method: "POST", body: form });
  },
  deleteProject: (id: string) =>
    request<void>(`/api/projects/${id}`, { method: "DELETE" }),
  updateProject: (id: string, changes: Record<string, unknown>) =>
    request<Project>(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
  reanalyze: (id: string) =>
    request<{ ok: boolean }>(`/api/projects/${id}/reanalyze`, { method: "POST" }),
  updateRally: (id: string, changes: Record<string, unknown>) =>
    request<Project>(`/api/rallies/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
  setWinner: (id: string, winner: PlayerKey) => api.updateRally(id, { winner }),
  toggleLet: (id: string, isLet: boolean) => api.updateRally(id, { is_let: isLet }),
  setValidity: (id: string, isValid: boolean) => api.updateRally(id, { is_valid: isValid }),
  addRally: (projectId: string, start: number, end: number, winner: PlayerKey | null) =>
    request<Project>(`/api/projects/${projectId}/rallies`, {
      method: "POST",
      body: JSON.stringify({
        start_time: start,
        end_time: end,
        winner,
        is_let: false,
      }),
    }),
  deleteRally: (id: string) => request<Project>(`/api/rallies/${id}`, { method: "DELETE" }),
  splitRally: (id: string, time: number) =>
    request<Project>(`/api/rallies/${id}/split`, {
      method: "POST",
      body: JSON.stringify({ time }),
    }),
  mergeRallies: (firstId: string, secondId: string) =>
    request<Project>("/api/rallies/merge", {
      method: "POST",
      body: JSON.stringify({ first_id: firstId, second_id: secondId }),
    }),
  addSideSwap: (projectId: string, time: number) =>
    request<Project>(`/api/projects/${projectId}/side-swaps`, {
      method: "POST",
      body: JSON.stringify({ time }),
    }),
  deleteSideSwap: (id: string) =>
    request<Project>(`/api/side-swaps/${id}`, { method: "DELETE" }),
  listExports: (projectId: string) =>
    request<ExportRecord[]>(`/api/projects/${projectId}/exports`),
  startExport: (projectId: string, kind: "full" | "highlights", rallyIds?: string[]) =>
    request<ExportRecord>(`/api/projects/${projectId}/exports`, {
      method: "POST",
      body: JSON.stringify({ kind, rally_ids: rallyIds }),
    }),
  getExport: (id: string) => request<ExportRecord>(`/api/exports/${id}`),
  courtSideLabel: (side: CourtSide) => (side === "right" ? "右区" : "左区"),
};

export type { CourtSide };