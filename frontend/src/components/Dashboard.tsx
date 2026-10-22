import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileVideo2,
  LoaderCircle,
  Plus,
  Radio,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { formatBytes, formatTime } from "../lib/score";
import type { CreateProjectInput, PlayerKey, ProjectSummary, CourtSide, VideoSide } from "../types";

interface Props {
  onOpen: (id: string) => void;
}

const initialForm: CreateProjectInput = {
  title: "",
  player_a_name: "球员 A",
  player_b_name: "球员 B",
  initial_a_score: 0,
  initial_b_score: 0,
  first_server: "A",
  first_server_court: "",
  initial_a_side: "bottom",
};

function statusLabel(status: string) {
  if (status === "ready") return "可复盘";
  if (status === "failed") return "需处理";
  if (status === "analyzing") return "分析中";
  return "排队中";
}

export default function Dashboard({ onOpen }: Props) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState<CreateProjectInput>(initialForm);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [projectToDelete, setProjectToDelete] = useState<ProjectSummary | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const refresh = async () => {
    try {
      setProjects(await api.listProjects());
    } catch (err) {
      setError(err instanceof Error ? err.message : "无法读取项目列表");
    } finally {
      setLoadingProjects(false);
    }
  };

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      if (projects.some((item) => ["queued", "analyzing"].includes(item.status))) {
        void refresh();
      }
    }, 1800);
    return () => window.clearInterval(timer);
  }, [projects.some((item) => ["queued", "analyzing"].includes(item.status))]);

  const deleteProject = async () => {
    if (!projectToDelete) return;
    setDeletingId(projectToDelete.id);
    setError("");
    try {
      await api.deleteProject(projectToDelete.id);
      setProjects((current) => current.filter((item) => item.id !== projectToDelete.id));
      setProjectToDelete(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除项目失败");
    } finally {
      setDeletingId(null);
    }
  };

  const update = <K extends keyof CreateProjectInput>(key: K, value: CreateProjectInput[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      if (!file) throw new Error("请先选择视频文件");
      const project = await api.upload(file, form);
      onOpen(project.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建项目失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#">
          <span className="brand-mark">
            <span />
            <span />
          </span>
          <span>
            <strong>羽球飞扬</strong>
            <small>RALLY REVIEW</small>
          </span>
        </a>
        <div className="topbar-badges">
          <span className="pill subtle">
            <ShieldCheck size={14} /> 本地处理
          </span>
          <span className="pill subtle">
            <Radio size={14} /> 离线可用
          </span>
        </div>
      </header>

      <main className="dashboard-main">
        <section className="hero-grid">
          <div className="hero-copy">
            <div className="eyebrow">
              <Sparkles size={15} /> BADMINTON MATCH INTELLIGENCE
            </div>
            <h1>
              让每一拍
              <br />
              <span>都值得复盘。</span>
            </h1>
            <p>
              上传羽毛球单打视频，自动拆解回合、生成比分时间线，并在画面左上角同步显示双方比分。识别结果随时可校正。
            </p>
            <div className="hero-facts">
              <span>
                <CheckCircle2 size={17} /> 自动回合切分
              </span>
              <span>
                <CheckCircle2 size={17} /> 发球权与比分校正
              </span>
              <span>
                <CheckCircle2 size={17} /> 完整视频 / 集锦导出
              </span>
            </div>
          </div>

          <form className="import-card" onSubmit={submit}>
            <div className="import-card-head">
              <div>
                <span className="section-kicker">NEW REVIEW</span>
                <h2>开始一次复盘</h2>
              </div>

            </div>

            <label className="dropzone">
              <input
                type="file"
                accept=".mp4,.mov,.mkv,.avi,.m4v,.webm,video/*"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <Upload size={26} />
              <strong>{file ? file.name : "选择或拖入比赛视频"}</strong>
              <small>{file ? formatBytes(file.size) : "MP4 / MOV / MKV，本地保存"}</small>
            </label>

            <div className="form-grid">
              <label className="field wide">
                <span>项目名称</span>
                <input
                  value={form.title}
                  onChange={(event) => update("title", event.target.value)}
                  placeholder="留空则使用视频文件名"
                />
              </label>
              <label className="field">
                <span>A 方姓名</span>
                <input value={form.player_a_name} onChange={(event) => update("player_a_name", event.target.value)} />
              </label>
              <label className="field">
                <span>B 方姓名</span>
                <input value={form.player_b_name} onChange={(event) => update("player_b_name", event.target.value)} />
              </label>
              <label className="field score-field">
                <span>A 起始分</span>
                <input
                  type="number"
                  min={0}
                  value={form.initial_a_score}
                  onChange={(event) => update("initial_a_score", Number(event.target.value))}
                />
              </label>
              <label className="field score-field">
                <span>B 起始分</span>
                <input
                  type="number"
                  min={0}
                  value={form.initial_b_score}
                  onChange={(event) => update("initial_b_score", Number(event.target.value))}
                />
              </label>
              <label className="field">
                <span>首先发球</span>
                <select value={form.first_server} onChange={(event) => update("first_server", event.target.value as PlayerKey)}>
                  <option value="A">{form.player_a_name}</option>
                  <option value="B">{form.player_b_name}</option>
                </select>
              </label>
              <label className="field">
                <span>A 初始半场</span>
                <select value={form.initial_a_side} onChange={(event) => update("initial_a_side", event.target.value as VideoSide)}>
                  <option value="bottom">画面近端 / 下方</option>
                  <option value="top">画面远端 / 上方</option>
                </select>
              </label>
              <label className="field">
                <span>首发球区</span>
                <select
                  value={form.first_server_court}
                  onChange={(event) => update("first_server_court", event.target.value as CourtSide | "")}
                >
                  <option value="">按分数自动判断</option>
                  <option value="right">右发球区</option>
                  <option value="left">左发球区</option>
                </select>
              </label>
            </div>

            {error && <div className="inline-error">{error}</div>}

            <button className="primary-button import-submit" disabled={submitting} type="submit">
              {submitting ? <LoaderCircle className="spin" size={18} /> : <Plus size={18} />}
              {submitting ? "正在创建..." : "创建并开始识别"}
            </button>
          </form>
        </section>

        <section className="project-section">
          <div className="section-heading">
            <div>
              <span className="section-kicker">LOCAL LIBRARY</span>
              <h2>最近的复盘</h2>
            </div>
            <span className="muted-count">{projects.length} 个项目</span>
          </div>

          {loadingProjects ? (
            <div className="empty-state">
              <LoaderCircle className="spin" />
              正在读取本地项目…
            </div>
          ) : projects.length === 0 ? (
            <div className="empty-state">
              <FileVideo2 size={26} />
              还没有比赛项目。使用上方表单导入第一段视频。
            </div>
          ) : (
            <div className="project-grid">
              {projects.map((project) => (
                <article
                  className="project-card"
                  key={project.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => onOpen(project.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onOpen(project.id);
                    }
                  }}
                >
                  <div className="project-cover">
                    {project.thumbnail_path ? (
                      <img src={`/api/projects/${project.id}/thumbnail`} alt="" />
                    ) : (
                      <div className="cover-placeholder">
                        <FileVideo2 size={30} />
                      </div>
                    )}
                    <span className={`status-chip ${project.status}`}>{statusLabel(project.status)}</span>
                    <button
                      type="button"
                      className="project-delete"
                      title="删除项目"
                      aria-label={`删除项目：${project.title}`}
                      disabled={deletingId === project.id}
                      onClick={(event) => {
                        event.stopPropagation();
                        setProjectToDelete(project);
                      }}
                    >
                      {deletingId === project.id ? <LoaderCircle className="spin" size={15} /> : <Trash2 size={15} />}
                    </button>
                    <span className="duration-chip">
                      <Clock3 size={13} /> {formatTime(project.duration)}
                    </span>
                  </div>
                  <div className="project-card-body">
                    <h3>{project.title}</h3>
                    <p>
                      {project.player_a_name} <span>vs</span> {project.player_b_name}
                    </p>
                    <div className="project-meta">
                      <span>{project.rally_count || 0} 个回合</span>
                      <span>{project.invalid_count || 0} 个无效</span>
                      <ArrowRight size={17} />
                    </div>
                    {["queued", "analyzing"].includes(project.status) && (
                      <div className="mini-progress">
                        <span style={{ width: `${Math.max(3, project.progress * 100)}%` }} />
                      </div>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </main>


      {projectToDelete && (
        <div className="confirm-backdrop" onClick={() => (deletingId ? null : setProjectToDelete(null))}>
          <div className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-project-title" onClick={(event) => event.stopPropagation()}>
            <div className="confirm-icon">
              <AlertTriangle size={22} />
            </div>
            <span className="section-kicker">DELETE PROJECT</span>
            <h3 id="delete-project-title">确认删除这个复盘？</h3>
            <p>
              将永久删除「<strong>{projectToDelete.title}</strong>」的项目记录、分析数据、预览和导出文件。
              如果视频是上传到本机的，源视频也会一并删除。此操作无法撤销。
            </p>
            <div className="confirm-actions">
              <button type="button" className="secondary-button" disabled={Boolean(deletingId)} onClick={() => setProjectToDelete(null)}>
                取消
              </button>
              <button type="button" className="danger-button" disabled={Boolean(deletingId)} onClick={() => void deleteProject()}>
                {deletingId ? <LoaderCircle className="spin" size={16} /> : <Trash2 size={16} />}
                {deletingId ? "正在删除…" : "确认删除"}
              </button>
            </div>
          </div>
        </div>
      )}
      <footer className="app-footer">
        <span>羽球飞扬 · 本地单打比赛分析</span>
        <span>视频与比分数据仅保存在本机</span>
      </footer>
    </div>
  );
}