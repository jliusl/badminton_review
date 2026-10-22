import type { Project, RallyEvent } from "../types";

export function formatTime(seconds: number, withMillis = false): string {
  if (!Number.isFinite(seconds)) return "00:00";
  const safe = Math.max(0, seconds);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = Math.floor(safe % 60);
  const base = hours
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  if (!withMillis) return base;
  return `${base}.${String(Math.floor((safe % 1) * 10))}`;
}

export function formatBytes(bytes: number): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index >= 3 ? 1 : 0)} ${units[index]}`;
}

export function activeRallyAt(project: Project, time: number): RallyEvent | null {
  // Use a half-open interval [start, end) so two adjacent rallies that share a
  // boundary do not both appear active at the same playback time.
  const active = project.timeline.find(
    (rally) => time >= rally.start_time && time < rally.end_time,
  );
  if (active) return active;
  const last = project.timeline[project.timeline.length - 1];
  return last && Math.abs(time - last.end_time) < 0.0001 ? last : null;
}

export function scoreAtTime(project: Project, time: number) {
  let score = { A: project.initial_a_score, B: project.initial_b_score };
  let server = project.first_server;
  let serveCourt = project.first_server_court ?? (score[project.first_server] % 2 === 0 ? "right" : "left");
  for (const rally of project.timeline) {
    if (time >= rally.score_update_time) {
      score = rally.score_after;
      server = rally.server_after;
      serveCourt = rally.serve_court_after;
      continue;
    }
    if (time >= rally.start_time) {
      score = rally.score_before;
      server = rally.server_before;
      serveCourt = rally.serve_court_before;
    }
    break;
  }
  return { score, server, serveCourt };
}

export function pointDelta(rally: RallyEvent): string {
  if (!rally.is_valid || rally.is_let) return "无效";
  if (!rally.winner) return "待定";
  return `${rally.winner} 得分`;
}