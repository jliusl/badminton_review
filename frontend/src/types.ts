export type PlayerKey = "A" | "B";
export type CourtSide = "left" | "right";
export type VideoSide = "top" | "bottom";

export interface ProjectSummary {
  id: string;
  title: string;
  thumbnail_path: string | null;
  duration: number;
  width: number;
  height: number;
  player_a_name: string;
  player_b_name: string;
  status: string;
  stage: string;
  progress: number;
  error: string | null;
  rally_count: number;
  let_count: number;
  invalid_count: number;
  updated_at: string;
}

export interface RallyEvent {
  id: string;
  order_index: number;
  start_time: number;
  end_time: number;
  score_update_time: number;
  winner: PlayerKey | null;
  is_valid: boolean;
  is_let: boolean;
  let_confirmed: boolean;
  let_candidate: boolean;
  confidence: number;
  verified: boolean;
  unresolved: boolean;
  source: string;
  note: string | null;
  score_before: Record<PlayerKey, number>;
  score_after: Record<PlayerKey, number>;
  server_before: PlayerKey;
  server_after: PlayerKey;
  serve_court_before: CourtSide;
  serve_court_after: CourtSide;
}

export interface SideSwap {
  id: string;
  project_id: string;
  time: number;
  created_at: string;
}

export interface Project {
  id: string;
  title: string;
  source_path: string;
  preview_path: string | null;
  thumbnail_path: string | null;
  source_size: number;
  duration: number;
  width: number;
  height: number;
  fps: number;
  video_codec: string;
  audio_codec: string;
  player_a_name: string;
  player_b_name: string;
  initial_a_score: number;
  initial_b_score: number;
  first_server: PlayerKey;
  first_server_court: CourtSide | null;
  initial_a_side: VideoSide;
  court_points: number[][] | null;
  status: string;
  stage: string;
  progress: number;
  error: string | null;
  timeline: RallyEvent[];
  final_score: Record<PlayerKey, number>;
  unresolved_count: number;
  let_count: number;
  invalid_count: number;
  side_swaps: SideSwap[];
  created_at: string;
  updated_at: string;
}

export interface ExportRecord {
  id: string;
  project_id: string;
  kind: "full" | "highlights";
  status: string;
  progress: number;
  output_path: string | null;
  error: string | null;
  created_at: string;
}

export interface CreateProjectInput {
  title: string;
  player_a_name: string;
  player_b_name: string;
  initial_a_score: number;
  initial_b_score: number;
  first_server: PlayerKey;
  first_server_court: CourtSide | "";
  initial_a_side: VideoSide;
}