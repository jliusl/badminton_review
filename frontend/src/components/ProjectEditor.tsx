import {
  AlertTriangle,
  ArrowLeft,
  ArrowLeftRight,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Crosshair,
  Download,
  Film,
  Flag,
  LoaderCircle,
  MapPin,
  Play,
  Plus,
  RotateCcw,
  Save,
  Scissors,
  Settings,
  Sparkles,
  Trash2,
  Trophy,
  X,
} from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { activeRallyAt, formatTime, scoreAtTime } from "../lib/score";
import type { ExportRecord, PlayerKey, Project, RallyEvent } from "../types";

interface Props {
  projectId: string;
}

const defaultCourt = [
  [0.08, 0.2],
  [0.92, 0.2],
  [0.95, 0.95],
  [0.05, 0.95],
];

function statusText(status: string) {
  if (status === "ready") return "分析完成";
  if (status === "failed") return "分析失败";
  if (status === "analyzing") return "正在分析";
  return "等待分析";
}

function confidenceLabel(value: number) {
  if (value >= 0.72) return "较高";
  if (value >= 0.55) return "中等";
  return "较低";
}

function parseTimecode(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (!trimmed.includes(":")) {
    const seconds = Number(trimmed);
    return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
  }
  const parts = trimmed.split(":");
  if (parts.length < 2 || parts.length > 3) return null;
  const numbers = parts.map(Number);
  if (numbers.some((part) => !Number.isFinite(part) || part < 0)) return null;
  if (parts.length === 2) return numbers[0] * 60 + numbers[1];
  return numbers[0] * 3600 + numbers[1] * 60 + numbers[2];
}

function TimecodeInput({
  value,
  onCommit,
  onSeek,
}: {
  value: number;
  onCommit: (value: number) => void;
  onSeek: () => void;
}) {
  const [draft, setDraft] = useState(formatTime(value, true));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) setDraft(formatTime(value, true));
  }, [focused, value]);

  const commit = () => {
    const parsed = parseTimecode(draft);
    if (parsed === null) {
      setDraft(formatTime(value, true));
      return;
    }
    setDraft(formatTime(parsed, true));
    onCommit(parsed);
  };

  return (
    <div className="inline-input timecode-input">
      <input
        type="text"
        value={draft}
        onFocus={(event) => {
          setFocused(true);
          event.currentTarget.select();
        }}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          setFocused(false);
          commit();
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
          if (event.key === "Escape") {
            setDraft(formatTime(value, true));
            event.currentTarget.blur();
          }
        }}
        placeholder="MM:SS.s"
      />
      <button onClick={onSeek} title="跳到该时间"><Play size={14} /></button>
    </div>
  );
}

export default function ProjectEditor({ projectId }: Props) {
  const [project, setProject] = useState<Project | null>(null);
  const [exports, setExports] = useState<ExportRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedForExport, setSelectedForExport] = useState<Set<string>>(new Set());
  const [currentTime, setCurrentTime] = useState(0);
  const [filter, setFilter] = useState<"all" | "unresolved" | "invalid">("all");
  const [calibrating, setCalibrating] = useState(false);
  const [courtPoints, setCourtPoints] = useState<number[][]>(defaultCourt);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [rallyLogHeight, setRallyLogHeight] = useState<number | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const initializedProject = useRef<string | null>(null);
  const draggingPoint = useRef<number | null>(null);
  const rallyListRef = useRef<HTMLDivElement>(null);
  const rallyRowRefs = useRef<Map<string, HTMLElement>>(new Map());
  const pendingDownloadsRef = useRef<Set<string>>(new Set());
  const inspectorRef = useRef<HTMLDivElement>(null);
  const rallyLogRef = useRef<HTMLElement>(null);

  const refreshProject = useCallback(async () => {
    const data = await api.getProject(projectId);
    setProject(data);
    if (data.court_points?.length === 4) setCourtPoints(data.court_points);
    if (initializedProject.current !== data.id) {
      initializedProject.current = data.id;
      const first = data.timeline.find((item) => item.unresolved) ?? data.timeline[0];
      setSelectedId(first?.id ?? null);
      setSelectedForExport(new Set(data.timeline.filter((item) => item.is_valid && !item.is_let).map((item) => item.id)));
    }
    return data;
  }, [projectId]);

  const refreshExports = useCallback(async () => {
    const data = await api.listExports(projectId);
    setExports(data);
    return data;
  }, [projectId]);

  useEffect(() => {
    setProject(null);
    setError("");
    initializedProject.current = null;
    Promise.all([refreshProject(), refreshExports()]).catch((err) =>
      setError(err instanceof Error ? err.message : "无法加载项目"),
    );
  }, [refreshProject, refreshExports]);

  const hasActiveExport = exports.some((item) => ["queued", "exporting"].includes(item.status));
  const shouldPoll = project?.status === "queued" || project?.status === "analyzing" || hasActiveExport;

  useEffect(() => {
    if (!shouldPoll) return;
    const timer = window.setInterval(() => {
      void refreshProject().catch(() => undefined);
      void refreshExports().catch(() => undefined);
    }, 1200);
    return () => window.clearInterval(timer);
  }, [shouldPoll, refreshProject, refreshExports]);

  useEffect(() => {
    if (!project || !selectedId) return;
    if (!project.timeline.some((item) => item.id === selectedId)) {
      setSelectedId(project.timeline[0]?.id ?? null);
    }
    setSelectedForExport((current) => {
      const valid = new Set(project.timeline.map((item) => item.id));
      return new Set([...current].filter((id) => valid.has(id)));
    });
  }, [project?.timeline, selectedId]);


  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 2200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    const pending = pendingDownloadsRef.current;
    if (pending.size === 0) return;

    for (const item of exports) {
      if (!pending.has(item.id)) continue;
      if (item.status === "failed") {
        pending.delete(item.id);
        continue;
      }
      if (item.status !== "ready") continue;

      pending.delete(item.id);
      const link = document.createElement("a");
      link.href = `/api/exports/${item.id}/file`;
      link.download = item.kind === "full" ? "完整比赛.mp4" : "精彩集锦.mp4";
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setNotice(item.kind === "full" ? "完整比赛导出完成，已开始下载" : "精彩集锦导出完成，已开始下载");
    }
  }, [exports]);

  const runMutation = async (operation: () => Promise<Project>, success?: string) => {
    setBusy(true);
    setError("");
    try {
      const data = await operation();
      setProject(data);
      if (success) setNotice(success);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
      return null;
    } finally {
      setBusy(false);
    }
  };

  const selected = project?.timeline.find((item) => item.id === selectedId) ?? null;
  const active = project ? activeRallyAt(project, currentTime) : null;
  const selectedIsInvalid = selected ? !selected.is_valid || selected.is_let : false;
  const currentScore = project ? scoreAtTime(project, currentTime) : null;
  const nextRally = selected && project
    ? project.timeline[project.timeline.findIndex((item) => item.id === selected.id) + 1]
    : null;
  const validRallyCount = project
    ? project.timeline.filter((item) => item.is_valid && !item.is_let).length
    : 0;
  const invalidRallyCount = project
    ? project.timeline.filter((item) => !item.is_valid || item.is_let).length
    : 0;

  const latestExports = useMemo(() => {
    const seenKinds = new Set<ExportRecord["kind"]>();
    return exports.filter((item) => {
      if (seenKinds.has(item.kind)) return false;
      seenKinds.add(item.kind);
      return true;
    });
  }, [exports]);

  useLayoutEffect(() => {
    const inspector = inspectorRef.current;
    const card = rallyLogRef.current;
    const video = videoRef.current;
    const sidebar = card?.closest(".review-sidebar") as HTMLElement | null;
    if (!inspector || !card || !sidebar || window.innerWidth <= 980) {
      setRallyLogHeight(null);
      return;
    }

    let frame = 0;
    const update = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        const availableHeight =
          inspector.getBoundingClientRect().bottom - card.getBoundingClientRect().top;
        const next = Math.max(180, Math.round(availableHeight));
        setRallyLogHeight((previous) =>
          previous !== null && Math.abs(previous - next) < 1 ? previous : next,
        );
      });
    };

    update();
    const observer = new ResizeObserver(update);
    observer.observe(inspector);
    observer.observe(card);
    observer.observe(sidebar);
    if (video) observer.observe(video);
    window.addEventListener("resize", update);
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [selectedId, project?.timeline.length, project?.duration]);

  useEffect(() => {
    if (!active?.id) return;
    let frame = 0;
    const keepActiveRallyVisible = () => {
      const list = rallyListRef.current;
      const row = rallyRowRefs.current.get(active.id);
      if (!list || !row) return;
      const listRect = list.getBoundingClientRect();
      const rowRect = row.getBoundingClientRect();
      const outside = rowRect.top < listRect.top + 8 || rowRect.bottom > listRect.bottom - 8;
      if (outside) {
        const maxScroll = Math.max(0, list.scrollHeight - list.clientHeight);
        const target =
          list.scrollTop +
          (rowRect.top - listRect.top) -
          list.clientHeight / 2 +
          rowRect.height / 2;
        list.scrollTo({ top: Math.min(maxScroll, Math.max(0, target)), behavior: "smooth" });
      }
    };
    // The card height is updated in a following animation frame. Waiting one
    // frame prevents the last row from being clipped against the old height.
    frame = window.requestAnimationFrame(keepActiveRallyVisible);
    return () => window.cancelAnimationFrame(frame);
  }, [active?.id, rallyLogHeight]);

  const filteredRallies = useMemo(() => {
    if (!project) return [];
    if (filter === "unresolved") return project.timeline.filter((item) => item.unresolved);

    if (filter === "invalid") return project.timeline.filter((item) => !item.is_valid || item.is_let);
    return project.timeline;
  }, [filter, project]);

  const seek = (time: number, play = false) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = Math.max(0, Math.min(time, project?.duration ?? time));
    setCurrentTime(video.currentTime);
    if (play) void video.play();
  };

  const selectRally = (rally: RallyEvent, play = false) => {
    setSelectedId(rally.id);
    seek(rally.start_time, play);
  };

  const setWinner = (rally: RallyEvent, winner: PlayerKey) =>
    void runMutation(() => api.setWinner(rally.id, winner), "得分方已更新");

  const markInvalid = (rally: RallyEvent) =>
    void runMutation(() => api.setValidity(rally.id, false), "已标记为无效回合，本回合不计分");

  const saveSettings = () => {
    if (!project) return;
    void runMutation(
      () =>
        api.updateProject(project.id, {
          title: project.title,
          player_a_name: project.player_a_name,
          player_b_name: project.player_b_name,
          initial_a_score: project.initial_a_score,
          initial_b_score: project.initial_b_score,
          first_server: project.first_server,
          initial_a_side: project.initial_a_side,
        }),
      "项目设置已保存",
    );
  };

  const addManualRally = () => {
    if (!project) return;
    const selectedIndex = selected
      ? project.timeline.findIndex((item) => item.id === selected.id)
      : -1;
    const anchor =
      selected?.end_time ??
      project.timeline[project.timeline.length - 1]?.end_time ??
      currentTime;
    const nextStart =
      selectedIndex >= 0 && selectedIndex + 1 < project.timeline.length
        ? project.timeline[selectedIndex + 1].start_time
        : project.duration;
    const maxEnd = Math.min(project.duration, Math.max(anchor, nextStart));
    if (maxEnd - anchor < 0.2) {
      setError("当前回合之后没有足够空间添加手工回合");
      return;
    }
    const start = anchor;
    const end = Math.min(maxEnd, start + 5);
    void runMutation(
      () => api.addRally(project.id, start, end, null),
      `已添加手工回合：${formatTime(start, true)} 开始，请选择得分方`,
    ).then((updated) => {
      if (updated) {
        const added = updated.timeline
          .filter((item) => item.source === "manual")
          .reduce((latest, item) =>
            Math.abs(item.start_time - start) < Math.abs(latest.start_time - start)
              ? item
              : latest,
          );
        setSelectedId(added.id);
        seek(start);
      }
    });
  };

  const saveCalibration = () => {
    if (!project) return;
    void runMutation(
      () => api.updateProject(project.id, { court_points: courtPoints }),
      "场地标定已保存",
    ).then(() => setCalibrating(false));
  };

  const startExport = (kind: "full" | "highlights") => {
    if (!project) return;
    if (project.unresolved_count > 0) {
      setError(`还有 ${project.unresolved_count} 个待确认回合，请先处理后再导出`);
      return;
    }
    if (kind === "highlights" && selectedForExport.size === 0) {
      setError("请至少选择一个精彩回合");
      return;
    }
    setBusy(true);
    api
      .startExport(
        project.id,
        kind,
        kind === "highlights" ? [...selectedForExport] : undefined,
      )
      .then(async (record) => {
        pendingDownloadsRef.current.add(record.id);
        setNotice(kind === "full" ? "完整视频已进入导出队列" : "集锦已进入导出队列");
        await refreshExports();
      })
      .catch((err) => setError(err instanceof Error ? err.message : "创建导出任务失败"))
      .finally(() => setBusy(false));
  };

  const onCalibrationMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (draggingPoint.current === null) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
    setCourtPoints((points) =>
      points.map((point, index) => (index === draggingPoint.current ? [x, y] : point)),
    );
  };

  if (!project) {
    return (
      <div className="center-screen">
        {error ? <AlertTriangle /> : <LoaderCircle className="spin" />}
        <span>{error || "正在打开复盘项目…"}</span>
        {error && (
          <button className="secondary-button" onClick={() => (window.location.hash = "")}>
            返回项目列表
          </button>
        )}
      </div>
    );
  }

  const isProcessing = project.status === "queued" || project.status === "analyzing";
  return (
    <div className="editor-shell">
      <header className="editor-topbar">
        <button className="icon-button" onClick={() => (window.location.hash = "")} title="返回项目列表">
          <ArrowLeft size={19} />
        </button>
        <div className="editor-title">
          <span className="section-kicker">MATCH REVIEW</span>
          <h1>{project.title}</h1>
        </div>
        <div className="editor-topbar-center">
          <div className="match-mini-score">
            <span>{project.player_a_name}</span>
            <strong>{project.final_score.A}</strong>
            <em>:</em>
            <strong>{project.final_score.B}</strong>
            <span>{project.player_b_name}</span>
          </div>
          <span className={`status-chip ${project.status}`}>{statusText(project.status)}</span>
        </div>
        <div className="toolbar-actions">
          <button className="secondary-button" onClick={() => setSettingsOpen((value) => !value)}>
            <Settings size={16} /> 比赛设置
          </button>
          <button
            className="secondary-button"
            onClick={() => {
              setCalibrating((value) => !value);
              videoRef.current?.pause();
            }}
          >
            <Crosshair size={16} /> {calibrating ? "退出标定" : "标定场地"}
          </button>
        </div>
      </header>

      {error && (
        <div className="toast error">
          <AlertTriangle size={17} />
          <span>{error}</span>
          <button onClick={() => setError("")}>
            <X size={15} />
          </button>
        </div>
      )}
      {notice && (
        <div className="toast success">
          <CheckCircle2 size={17} />
          <span>{notice}</span>
        </div>
      )}

      {isProcessing ? (
        <main className="processing-main">
          <div className="processing-card">
            <div className="processing-orb">
              <Sparkles size={30} />
            </div>
            <span className="section-kicker">ANALYSIS IN PROGRESS</span>
            <h2>{project.stage}</h2>
            <p>正在本地识别击球、回合边界和得分方。你可以离开此页面，任务会在后台继续。</p>
            <div className="large-progress">
              <span style={{ width: `${Math.max(2, project.progress * 100)}%` }} />
            </div>
            <strong>{Math.round(project.progress * 100)}%</strong>
          </div>
        </main>
      ) : project.status === "failed" ? (
        <main className="processing-main">
          <div className="processing-card failed">
            <AlertTriangle size={34} />
            <h2>自动分析未完成</h2>
            <p>{project.error || "请检查视频和音频后重试。"}</p>
            <button
              className="primary-button"
              onClick={() => {
                void api.reanalyze(project.id).then(() => refreshProject());
              }}
            >
              <RotateCcw size={17} /> 重新分析
            </button>
          </div>
        </main>
      ) : (
        <main className="editor-main">
          <section className="video-column">
            <div className={`video-stage ${calibrating ? "calibrating" : ""}`}>
              <video
                ref={videoRef}
                src={`/api/projects/${project.id}/video`}
                controls={!calibrating}
                preload="metadata"
                onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
                onLoadedMetadata={(event) => {
                  event.currentTarget.currentTime = 0;
                  setCurrentTime(0);
                }}
              />
              {currentScore && (
                <div className="video-scoreboard" aria-label="实时比分">
                  <div className={currentScore.server === "A" ? "score-row serving" : "score-row"}>
                    <span className="serve-dot" />
                    <span className="score-name">{project.player_a_name}</span>
                    <strong>{currentScore.score.A}</strong>
                  </div>
                  <div className={currentScore.server === "B" ? "score-row serving" : "score-row"}>
                    <span className="serve-dot" />
                    <span className="score-name">{project.player_b_name}</span>
                    <strong>{currentScore.score.B}</strong>
                  </div>
                </div>
              )}

              {calibrating && (
                <svg
                  className="court-calibration"
                  viewBox="0 0 1000 1000"
                  preserveAspectRatio="none"
                  onPointerMove={onCalibrationMove}
                  onPointerUp={() => (draggingPoint.current = null)}
                  onPointerLeave={() => {
                    if (draggingPoint.current !== null) draggingPoint.current = null;
                  }}
                >
                  <polygon
                    points={courtPoints.map(([x, y]) => `${x * 1000},${y * 1000}`).join(" ")}
                    className="court-polygon"
                  />
                  {courtPoints.map(([x, y], index) => (
                    <g key={index}>
                      <circle
                        cx={x * 1000}
                        cy={y * 1000}
                        r={22}
                        className="court-handle-hit"
                        onPointerDown={(event) => {
                          event.currentTarget.setPointerCapture(event.pointerId);
                          draggingPoint.current = index;
                        }}
                      />
                      <circle cx={x * 1000} cy={y * 1000} r={11} className="court-handle" />
                    </g>
                  ))}
                </svg>
              )}
              {calibrating && (
                <div className="calibration-bar">
                  <span>
                    <MapPin size={16} /> 拖动四个角点对齐球场边线
                  </span>
                  <div>
                    <button className="ghost-button" onClick={() => setCourtPoints(defaultCourt)}>
                      恢复默认
                    </button>
                    <button className="primary-button compact" onClick={saveCalibration}>
                      <Save size={15} /> 保存标定
                    </button>
                  </div>
                </div>
              )}
            </div>

            <div className="overview-card">
              <div className="overview-head">
                <div>
                  <span className="section-kicker">MATCH OVERVIEW</span>
                  <h3>比赛时间线</h3>
                </div>
                <div className="overview-legend">
                  <span><i className="legend-dot point" /> 得分</span>
                  <span><i className="legend-dot invalid" /> 无效</span>
                  <span><i className="legend-dot pending" /> 待确认</span>
                </div>
              </div>
              <div
                className="overview-track"
                onClick={(event) => {
                  const rect = event.currentTarget.getBoundingClientRect();
                  seek(((event.clientX - rect.left) / rect.width) * project.duration);
                }}
              >
                {project.timeline.map((rally) => (
                  <span
                    key={rally.id}
                    className={`overview-rally ${!rally.is_valid || rally.is_let ? "is-invalid" : ""} ${rally.unresolved ? "is-pending" : ""} ${rally.id === selectedId ? "is-selected" : ""}`}
                    style={{
                      left: `${(rally.start_time / project.duration) * 100}%`,
                      width: `${Math.max(0.22, ((rally.end_time - rally.start_time) / project.duration) * 100)}%`,
                    }}
                    title={`${formatTime(rally.start_time)} · ${!rally.is_valid || rally.is_let ? "无效回合" : `${rally.winner ?? "?"} 得分`}`}
                  />
                ))}
                <span
                  className="overview-playhead"
                  style={{ left: `${(currentTime / project.duration) * 100}%` }}
                />
              </div>
              <div className="overview-times">
                <span>{formatTime(0)}</span>
                <span>{formatTime(project.duration / 2)}</span>
                <span>{formatTime(project.duration)}</span>
              </div>
            </div>
            {selected && (
              <div className="rally-inspector" ref={inspectorRef}>
                <div className="inspector-head">
                  <div>
                    <span className="section-kicker">RALLY #{selected.order_index + 1}</span>
                    <h3>
                      {formatTime(selected.start_time, true)} – {formatTime(selected.end_time, true)}
                    </h3>
                  </div>
                  <div className={`confidence-badge ${selectedIsInvalid ? "invalid" : selected.unresolved ? "pending" : "ok"}`}>
                    {selectedIsInvalid
                      ? "无效回合（含重发） · 不计分"
                      : `AI 置信度 ${Math.round(selected.confidence * 100)}% · ${selected.verified ? "已确认" : confidenceLabel(selected.confidence)}`}
                  </div>
                </div>
                {selected.note && (
                  <div className="inspector-note">
                    <Sparkles size={14} />
                    <span>{selected.note}</span>
                  </div>
                )}

                <div className="inspector-grid">
                                    <label className="field">
                    <span>起点</span>
                    <TimecodeInput
                      value={selected.start_time}
                      onSeek={() => seek(selected.start_time)}
                      onCommit={(value) => {
                        if (value >= selected.end_time) {
                          setError("回合起点必须早于终点");
                          return;
                        }
                        void runMutation(() =>
                          api.updateRally(selected.id, { start_time: value }),
                        );
                      }}
                    />
                  </label>
                  <label className="field">
                    <span>终点</span>
                    <TimecodeInput
                      value={selected.end_time}
                      onSeek={() => seek(selected.end_time)}
                      onCommit={(value) => {
                        if (value <= selected.start_time) {
                          setError("回合终点必须晚于起点");
                          return;
                        }
                        void runMutation(() =>
                          api.updateRally(selected.id, { end_time: value }),
                        );
                      }}
                    />
                  </label><div className="field">
                    <span>当前播放位置</span>
                    <div className="time-setting-row">
                      <strong>{formatTime(currentTime, true)}</strong>
                      <button
                        className="ghost-button"
                        disabled={currentTime >= selected.end_time}
                        onClick={() => void runMutation(() => api.updateRally(selected.id, { start_time: currentTime }))}
                      >
                        设为起点
                      </button>
                      <button
                        className="ghost-button"
                        disabled={currentTime <= selected.start_time}
                        onClick={() => void runMutation(() => api.updateRally(selected.id, { end_time: currentTime }))}
                      >
                        设为终点
                      </button>
                    </div>
                  </div>
                  <div className="field">
                    <span>回合状态</span>
                    <div className="status-actions">
                      <button
                        className={selected.is_valid && !selected.is_let && selected.winner === "A" ? "winner-button active" : "winner-button"}
                        onClick={() => setWinner(selected, "A")}
                      >
                        A · {project.player_a_name} 得分
                      </button>
                      <button
                        className={selected.is_valid && !selected.is_let && selected.winner === "B" ? "winner-button active" : "winner-button"}
                        onClick={() => setWinner(selected, "B")}
                      >
                        B · {project.player_b_name} 得分
                      </button>
                      <button
                        className={selectedIsInvalid ? "validity-button invalid active" : "validity-button invalid"}
                        onClick={() => markInvalid(selected)}
                        disabled={selectedIsInvalid}
                      >
                        <X size={14} /> 标记无效
                      </button>
                      <small className="status-hint">选择得分方即自动确认为有效并恢复计分；重发请标记为无效。</small>
                    </div>
                  </div>
                </div>

                <div className="inspector-footer">
                  <div className="score-transition">
                    <span>本回合前</span>
                    <strong>{selected.score_before.A} : {selected.score_before.B}</strong>
                    <ChevronRight size={15} />
                    <span>本回合后</span>
                    <strong>{selected.score_after.A} : {selected.score_after.B}</strong>
                    <em>{selectedIsInvalid ? "无效回合，不计分（含重发）" : selected.winner ? `${selected.winner} 方 +1` : "尚未计分"}</em>
                  </div>
                  <div className="inspector-actions">
                    <button
                      className="ghost-button"
                      onClick={() => {
                        if (currentTime > selected.start_time && currentTime < selected.end_time) {
                          void runMutation(() => api.splitRally(selected.id, currentTime), "回合已拆分，请确认前半段得分");
                        } else {
                          setError("请先把播放位置移到该回合内部，再执行拆分");
                        }
                      }}
                    >
                      <Scissors size={15} /> 在当前位置拆分
                    </button>
                    {nextRally && (
                      <button
                        className="ghost-button"
                        onClick={() => void runMutation(() => api.mergeRallies(selected.id, nextRally.id), "回合已合并")}
                      >
                        合并下一回合
                      </button>
                    )}
                    <button
                      className="ghost-button danger"
                      onClick={() => void runMutation(() => api.deleteRally(selected.id), "回合已删除")}
                    >
                      <Trash2 size={15} /> 删除
                    </button>
                  </div>
                </div>
              </div>
            )}
          </section>
          <aside className="review-sidebar">
            <section className="side-card score-card">
              <div className="side-card-head">
                <span className="section-kicker">LIVE SCORE</span>
                <Flag size={17} />
              </div>
              <div className="side-score">
                <div>
                  <div className="side-player-label">
                    <span className="player-side-badge a">A</span>
                    <span>{project.player_a_name}</span>
                  </div>
                  <strong>{currentScore?.score.A ?? project.initial_a_score}</strong>
                </div>
                <em>:</em>
                <div>
                  <div className="side-player-label">
                    <span className="player-side-badge b">B</span>
                    <span>{project.player_b_name}</span>
                  </div>
                  <strong>{currentScore?.score.B ?? project.initial_b_score}</strong>
                </div>
              </div>
              <div className="serve-state">
                <span className={`serve-indicator ${currentScore?.server === "A" ? "a" : "b"}`} />
                当前发球：{currentScore?.server === "A" ? "A 方" : "B 方"} · {currentScore?.server === "A" ? project.player_a_name : project.player_b_name}
                <small>{currentScore?.serveCourt === "right" ? "右发球区" : "左发球区"}</small>
              </div>
              <div className="final-score-row">
                <Trophy size={16} />
                最终比分 <strong>{project.final_score.A} : {project.final_score.B}</strong>
              </div>
            </section>

            <section className="side-card match-stats-card">
              <div className="match-stats-grid">
                <div className="match-stat">
                  <span>有效回合</span>
                  <strong>{validRallyCount}</strong>
                </div>
                <div className="match-stat danger">
                  <span>无效（含重发）</span>
                  <strong>{invalidRallyCount}</strong>
                </div>
                <div className="match-stat warning">
                  <span>待确认</span>
                  <strong>{project.unresolved_count}</strong>
                </div>
              </div>
            </section>

            <div className="side-tools-grid">
              <div className="side-tool-mini-grid">
            <section className="side-card side-events-card">
              <div className="side-card-head">
                <div>
                  <span className="section-kicker">COURT</span>
                  <h2>场地与换边</h2>
                </div>
                <ArrowLeftRight size={17} />
              </div>
              <button
                className="connection-button"
                onClick={() =>
                  void runMutation(
                    () => api.addSideSwap(project.id, currentTime),
                    `已在 ${formatTime(currentTime)} 标记换边`,
                  )
                }
              >
                <ArrowLeftRight size={16} /> 在 {formatTime(currentTime)} 标记换边
              </button>
              {project.side_swaps.length > 0 && (
                <div className="event-chips">
                  {project.side_swaps.map((swap) => (
                    <span className="event-chip" key={swap.id}>
                      <Clock3 size={13} /> {formatTime(swap.time)}
                      <button onClick={() => void runMutation(() => api.deleteSideSwap(swap.id))}>
                        <X size={12} />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </section>

            <section className="side-card danger-card">
              <div className="side-card-head">
                <div>
                  <span className="section-kicker">MAINTENANCE</span>
                  <h2>重新识别</h2>
                </div>
                <RotateCcw size={17} />
              </div>

              <button
                className="secondary-button full"
                onClick={() => {
                  if (!window.confirm("重新分析会覆盖现有回合编辑，确定继续吗？")) return;
                  api
                    .reanalyze(project.id)
                    .then(() => refreshProject())
                    .catch((err) => setError(err instanceof Error ? err.message : "无法重新分析"));
                }}
              >
                <RotateCcw size={15} /> 重新分析视频
              </button>
            </section>
              </div>
            <section className="side-card export-card">
              <div className="side-card-head">
                <div>
                  <span className="section-kicker">EXPORT</span>
                  <h2>导出视频</h2>
                </div>
                <Film size={18} />
              </div>
              {project.unresolved_count > 0 ? (
                <div className="export-warning">
                  <AlertTriangle size={17} />
                  <span>还有 {project.unresolved_count} 个回合待确认。处理完成后即可导出。</span>
                </div>
              ) : (
                <div className="export-ready">
                  <CheckCircle2 size={16} /> 所有回合已确认，可以导出
                </div>
              )}
              <div className="export-selection-actions">
                <span>已选 {selectedForExport.size} 个精彩回合</span>
                <button
                  onClick={() =>
                    setSelectedForExport(
                      new Set(project.timeline.filter((item) => item.is_valid && !item.is_let).map((item) => item.id)),
                    )
                  }
                >
                  全选
                </button>
                <button onClick={() => setSelectedForExport(new Set())}>清空</button>
              </div>
              <div className="export-buttons">
                <button
                  className="export-action-button"
                  disabled={busy || project.unresolved_count > 0 || selectedForExport.size === 0}
                  onClick={() => startExport("highlights")}
                >
                  <Download size={16} /> 导出精彩集锦
                </button>
                <button
                  className="export-action-button"
                  disabled={busy || project.unresolved_count > 0}
                  onClick={() => startExport("full")}
                >
                  <Download size={16} /> 导出完整比赛
                </button>
              </div>
              <div className="export-jobs">
                {latestExports.length === 0 ? (
                  <div className="export-empty">尚无导出任务</div>
                ) : (
                  latestExports.map((item) => {
                    const failureReason = item.error || "导出任务失败";
                    const retryLabel =
                      item.kind === "full" ? "重新导出完整比赛" : "重新导出精彩集锦";
                    const tooltipId = `export-error-${item.id}`;
                    return (
                      <div className="export-job" key={item.id}>
                        <div>
                          <strong>{item.kind === "full" ? "完整比赛" : "精彩集锦"}</strong>
                          <span className="export-job-status">
                            {item.status === "ready"
                              ? "已完成"
                              : item.status === "failed"
                                ? failureReason
                                : `渲染中 ${Math.round(item.progress * 100)}%`}
                          </span>
                        </div>
                        {item.status === "ready" ? (
                          <a href={`/api/exports/${item.id}/file`} className="download-link">
                            <Download size={15} /> 下载
                          </a>
                        ) : item.status === "failed" ? (
                          <span
                            className="export-error-indicator"
                            role="img"
                            tabIndex={0}
                            aria-label={`${failureReason}。请${retryLabel}。`}
                            aria-describedby={tooltipId}
                            title={`${failureReason}。请${retryLabel}。`}
                          >
                            <AlertTriangle size={16} />
                            <span className="export-error-tooltip" id={tooltipId} role="tooltip">
                              <strong>导出失败</strong>
                              <span>{failureReason}</span>
                              <em>请{retryLabel}。</em>
                            </span>
                          </span>
                        ) : (
                          <LoaderCircle className="spin" size={16} />
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </section>
            </div>

            <section
              className="side-card timeline-card"
              ref={rallyLogRef}
              style={rallyLogHeight ? { height: `${rallyLogHeight}px`, maxHeight: "none" } : undefined}
            >
              <div className="side-card-head">
                <div>
                  <span className="section-kicker">RALLY LOG</span>
                  <h2>回合校对</h2>
                </div>
                <button className="icon-button" title="添加手工回合" onClick={addManualRally}>
                  <Plus size={17} />
                </button>
              </div>

              <div className="filter-tabs">
                <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>
                  全部 {project.timeline.length}
                </button>
                <button className={filter === "unresolved" ? "active" : ""} onClick={() => setFilter("unresolved")}>
                  待确认 {project.unresolved_count}
                </button>
                <button className={filter === "invalid" ? "active" : ""} onClick={() => setFilter("invalid")}>
                  无效 {project.invalid_count}
                </button>
              </div>

              <div className="rally-list" ref={rallyListRef}>
                {filteredRallies.length === 0 && (
                  <div className="empty-list">
                    <CheckCircle2 size={23} />
                    当前筛选下没有回合
                  </div>
                )}
                {filteredRallies.map((rally) => (
                  <article
                    key={rally.id}
                    ref={(element) => {
                      if (element) rallyRowRefs.current.set(rally.id, element);
                      else rallyRowRefs.current.delete(rally.id);
                    }}
                    aria-current={active?.id === rally.id ? "true" : undefined}
                    className={`rally-row ${rally.id === selectedId ? "selected" : ""} ${active?.id === rally.id ? "playing" : ""} ${rally.unresolved ? "unresolved" : ""} ${!rally.is_valid || rally.is_let ? "invalid-rally" : ""}`}
                  >
                    <button className="rally-row-main" onClick={() => selectRally(rally)}>
                      <span className="rally-index">{String(rally.order_index + 1).padStart(2, "0")}</span>
                      <span className="rally-time">{formatTime(rally.start_time)}</span>
                      <span className={`rally-result ${!rally.is_valid || rally.is_let ? "invalid" : rally.winner?.toLowerCase() ?? "pending"}`}>
                        {!rally.is_valid || rally.is_let ? "无效" : rally.winner ? `${rally.winner} +1` : "待定"}
                      </span>
                      <span className="rally-score" aria-label={`本回合前 ${rally.score_before.A} 比 ${rally.score_before.B}，本回合后 ${rally.score_after.A} 比 ${rally.score_after.B}`}>
                        <span className="rally-score-before">{rally.score_before.A}:{rally.score_before.B}</span>
                        <span className="rally-score-arrow" aria-hidden="true">→</span>
                        <strong className="rally-score-after">{rally.score_after.A}:{rally.score_after.B}</strong>
                      </span>
                      {active?.id === rally.id ? (
                        <span className="live-dot" title="当前进行中" />
                      ) : (
                        rally.unresolved && <span className="unresolved-dot" title="待确认" />
                      )}
                    </button>
                    <div className="rally-quick-actions">
                      <button
                        className={!rally.is_valid || rally.is_let ? "invalid-active" : ""}
                        onClick={() => markInvalid(rally)}
                        disabled={!rally.is_valid || rally.is_let}
                        title="标记为无效回合（含重发）"
                      >
                        <X size={12} />
                      </button>
                      <button
                        className={rally.is_valid && !rally.is_let && rally.winner === "A" ? "active" : ""}
                        onClick={() => setWinner(rally, "A")}
                        title={`${project.player_a_name} 得分（自动确认有效）`}
                      >
                        A
                      </button>
                      <button
                        className={rally.is_valid && !rally.is_let && rally.winner === "B" ? "active" : ""}
                        onClick={() => setWinner(rally, "B")}
                        title={`${project.player_b_name} 得分（自动确认有效）`}
                      >
                        B
                      </button>
                    </div>
                    {active?.id === rally.id && (
                      <span
                        className="rally-current-progress"
                        style={{
                          width: `${Math.max(
                            0,
                            Math.min(
                              100,
                              ((currentTime - rally.start_time) /
                                Math.max(0.1, rally.end_time - rally.start_time)) *
                                100,
                            ),
                          )}%`,
                        }}
                      />
                    )}
                  </article>
                ))}
              </div>
            </section>

          </aside>
        </main>
      )}

      {settingsOpen && (
        <div className="settings-drawer-backdrop" onClick={() => setSettingsOpen(false)}>
          <aside className="settings-drawer" onClick={(event) => event.stopPropagation()}>
            <div className="drawer-head">
              <div>
                <span className="section-kicker">MATCH SETUP</span>
                <h2>比赛设置</h2>
              </div>
              <button className="icon-button" onClick={() => setSettingsOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <div className="drawer-body">
              <label className="field">
                <span>项目名称</span>
                <input
                  value={project.title}
                  onChange={(event) => setProject({ ...project, title: event.target.value })}
                />
              </label>
              <div className="form-grid">
                <label className="field">
                  <span>A 方姓名</span>
                  <input
                    value={project.player_a_name}
                    onChange={(event) => setProject({ ...project, player_a_name: event.target.value })}
                  />
                </label>
                <label className="field">
                  <span>B 方姓名</span>
                  <input
                    value={project.player_b_name}
                    onChange={(event) => setProject({ ...project, player_b_name: event.target.value })}
                  />
                </label>
                <label className="field score-field">
                  <span>A 起始分</span>
                  <input
                    type="number"
                    min={0}
                    value={project.initial_a_score}
                    onChange={(event) => setProject({ ...project, initial_a_score: Number(event.target.value) })}
                  />
                </label>
                <label className="field score-field">
                  <span>B 起始分</span>
                  <input
                    type="number"
                    min={0}
                    value={project.initial_b_score}
                    onChange={(event) => setProject({ ...project, initial_b_score: Number(event.target.value) })}
                  />
                </label>
                <label className="field">
                  <span>首先发球</span>
                  <select
                    value={project.first_server}
                    onChange={(event) => setProject({ ...project, first_server: event.target.value as PlayerKey })}
                  >
                    <option value="A">{project.player_a_name}</option>
                    <option value="B">{project.player_b_name}</option>
                  </select>
                </label>
                <label className="field">
                  <span>A 初始半场</span>
                  <select
                    value={project.initial_a_side}
                    onChange={(event) => setProject({ ...project, initial_a_side: event.target.value as "top" | "bottom" })}
                  >
                    <option value="bottom">画面近端 / 下方</option>
                    <option value="top">画面远端 / 上方</option>
                  </select>
                </label>
              </div>
              <div className="drawer-note">
                <MapPin size={16} />
                <span>{project.source_path}</span>
              </div>
            </div>
            <div className="drawer-footer">
              <button className="secondary-button" onClick={() => setSettingsOpen(false)}>
                取消
              </button>
              <button className="primary-button" onClick={() => { saveSettings(); setSettingsOpen(false); }}>
                <Save size={16} /> 保存设置
              </button>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
