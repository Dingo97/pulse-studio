import { useEffect, useRef, useState } from "react";
import { Activity, Copy, Download, FileArchive, FolderOpen, Gauge, Plus, RefreshCw, Trash2, Upload, WandSparkles } from "lucide-react";
import "./dashboard.css";

export type ProjectSummary = {
  id: string;
  name: string;
  status: string;
  has_song: boolean;
  has_cover: boolean;
  has_lyrics: boolean;
  outputs: string[];
  duration?: number;
  bpm?: number;
  updated_at: string;
};

export default function Dashboard({ api, onOpen, onCreate }: {
  api: string;
  onOpen: (project: ProjectSummary) => void;
  onCreate: () => void;
}) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const importer = useRef<HTMLInputElement>(null);

  async function refresh() {
    try {
      const response = await fetch(`${api}/api/projects`);
      if (!response.ok) throw new Error("Could not load projects");
      setProjects(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load projects");
    }
  }

  useEffect(() => { refresh(); }, []);

  async function duplicate(id: string) {
    setBusy(id);
    await fetch(`${api}/api/projects/${id}/duplicate`, { method: "POST" });
    await refresh();
    setBusy("");
  }

  async function remove(id: string) {
    if (!window.confirm("Delete this project and its local files?")) return;
    setBusy(id);
    await fetch(`${api}/api/projects/${id}`, { method: "DELETE" });
    await refresh();
    setBusy("");
  }

  async function importProject(file?: File) {
    if (!file) return;
    setBusy("import");
    setError("");
    const body = new FormData();
    body.append("project", file);
    const response = await fetch(`${api}/api/projects/import`, { method: "POST", body });
    if (!response.ok) setError((await response.json()).detail ?? "Import failed");
    await refresh();
    setBusy("");
  }

  return <div className="app-shell dashboard-shell">
    <aside>
      <a className="brand"><span className="brand-mark"><Activity /></span><span>Pulse <b>Studio</b></span></a>
      <nav><a className="active"><Gauge size={18} /> Projects</a><a onClick={onCreate}><WandSparkles size={18} /> Create</a></nav>
      <div className="version">Local-first · v0.1 Alpha</div>
    </aside>
    <main>
      <header className="dashboard-header">
        <div><span className="eyebrow">PROJECT LIBRARY</span><h1>Your releases.</h1><p>Reopen, duplicate and regenerate every Pulse project.</p></div>
        <div className="dashboard-actions">
          <button className="secondary-action" onClick={() => importer.current?.click()}><Upload /> Import .pulseproject</button>
          <input ref={importer} type="file" accept=".pulseproject" onChange={event => importProject(event.target.files?.[0])} />
          <button className="render-button" onClick={onCreate}><Plus /> New project</button>
        </div>
      </header>
      {error && <div className="dashboard-error">{error}</div>}
      <section className="project-grid">
        {projects.map(project => <article className="project-card" key={project.id}>
          <button className="project-cover" onClick={() => onOpen(project)}>
            {project.has_cover ? <img src={`${api}/api/projects/${project.id}/assets/cover`} /> : <FileArchive />}
            <span className={`project-status ${project.status}`}>{project.status}</span>
          </button>
          <div className="project-info">
            <div><h2>{project.name}</h2><p>{project.bpm ? `${Math.round(project.bpm)} BPM · ` : ""}{project.duration ? `${Math.floor(project.duration / 60)}:${String(Math.round(project.duration % 60)).padStart(2, "0")}` : "Not analyzed"}</p></div>
            <button onClick={() => onOpen(project)} title="Open"><FolderOpen /></button>
          </div>
          <div className="project-meta"><span>{project.outputs.length} renders</span><span>{new Date(project.updated_at).toLocaleDateString()}</span></div>
          <div className="project-actions">
            <button onClick={() => duplicate(project.id)} disabled={busy === project.id}><Copy /> Duplicate</button>
            <a href={`${api}/api/projects/${project.id}/export`}><Download /> Project</a>
            <button className="danger" onClick={() => remove(project.id)}><Trash2 /></button>
          </div>
        </article>)}
        {!projects.length && !error && <div className="empty-projects"><RefreshCw /><h2>No projects yet</h2><p>Create your first release or import a `.pulseproject` file.</p><button onClick={onCreate}>Create project</button></div>}
      </section>
    </main>
  </div>;
}
