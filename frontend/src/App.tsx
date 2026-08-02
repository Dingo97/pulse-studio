import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, Check, ChevronRight, CircleAlert, Download, FileAudio,
  FileText, Gauge, Image, Play, RotateCcw, Sparkles, Upload, WandSparkles,
} from "lucide-react";
import Editor, { type Cue, type EditorSettings, type ExportPlan, type OutputKind } from "./Editor";
import Dashboard from "./Dashboard";

const API = import.meta.env.VITE_API_URL ?? "";
type Output = OutputKind;
type Status = "queued" | "analyzing" | "rendering" | "completed" | "failed" | "cancelled";
type Job = {
  id: string; project_id: string; project_name: string; status: Status;
  progress: number; stage: string; message?: string; outputs: string[];
};
type Health = { status: string; ffmpeg: boolean; nvenc: boolean; gpu?: string };
type Metadata = { duration: number; bpm: number; lyrics: Cue[]; lyrics_source: string; sections: number[]; downbeats: number[] };
const clock = (seconds:number) => `${Math.floor(Math.max(0,seconds)/60)}:${String(Math.floor(Math.max(0,seconds)%60)).padStart(2,"0")}`;

function FileDrop({ label, hint, icon, accept, file, onChange, optional = false }: {
  label: string; hint: string; icon: React.ReactNode; accept: string; file?: File;
  onChange: (file?: File) => void; optional?: boolean;
}) {
  return (
    <label className={`dropzone ${file ? "has-file" : ""}`}>
      <input type="file" accept={accept} onChange={(e) => onChange(e.target.files?.[0])} />
      <span className="file-icon">{file ? <Check size={19} /> : icon}</span>
      <span className="file-copy">
        <strong>{file?.name ?? label}</strong>
        <small>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : `${hint}${optional ? " · Optional" : ""}`}</small>
      </span>
      <Upload size={18} className="upload-icon" />
    </label>
  );
}

function EditorRoute({ id, navigate, loadedId, busy, error, onLoad, children }: {
  id: string; navigate: (path: string) => void; loadedId: string; busy: boolean; error: string;
  onLoad: (id: string) => void; children: React.ReactNode;
}) {
  const loaded = Boolean(id) && id === loadedId;
  const [attemptedId, setAttemptedId] = useState("");
  useEffect(() => {
    if (id && !loaded && !busy && attemptedId !== id) { setAttemptedId(id); onLoad(id); }
  }, [id, loaded, busy, attemptedId, onLoad]);
  if (loaded) return <>{children}</>;
  return (
    <div className="route-status">
      {error && !busy ? <>
        <CircleAlert />
        <p>{error}</p>
        <div>
          <button onClick={() => navigate("/projects")}>Back to projects</button>
          <button className="primary" onClick={() => { if (id) { setAttemptedId(id); onLoad(id); } }}>Retry</button>
        </div>
      </> : <>
        <span className="route-spinner" />
        <p>Loading project…</p>
      </>}
    </div>
  );
}

export default function App() {
  return <AppRoutes />;
}

function AppRoutes() {
  const initialPath = window.location.pathname === "/" ? "/projects" : window.location.pathname;
  const [path, setPath] = useState(initialPath);
  const navigate = useCallback((next: string) => {
    if (window.location.pathname !== next) window.history.pushState({}, "", next);
    setPath(next);
  }, []);
  useEffect(() => {
    if (window.location.pathname === "/") window.history.replaceState({}, "", "/projects");
    const onPopState = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);
  const [song, setSong] = useState<File>();
  const [cover, setCover] = useState<File>();
  const [lyrics, setLyrics] = useState<File>();
  const [title, setTitle] = useState("");
  const [language,setLanguage]=useState("en");
  const [selected, setSelected] = useState<Output[]>(["teaser", "chorus", "lyrics", "youtube"]);
  const [starts, setStarts] = useState<Record<Output, string>>({ teaser: "0", chorus: "0", lyrics: "0", youtube: "0" });
  const [ends, setEnds] = useState<Record<Output, string>>({ teaser: "0:15", chorus: "0:30", lyrics: "0:45", youtube: "" });
  const [quality, setQuality] = useState("high");
  const [health, setHealth] = useState<Health>();
  const [job, setJob] = useState<Job>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [projectId, setProjectId] = useState("");
  const [metadata, setMetadata] = useState<Metadata>();
  const [initialEditor, setInitialEditor] = useState<Partial<EditorSettings>>();
  const [projectFiles, setProjectFiles] = useState<string[]>([]);

  useEffect(() => { fetch(`${API}/api/health`).then(r => r.json()).then(setHealth).catch(() => undefined); }, []);
  useEffect(() => {
    if (!job || ["completed", "failed", "cancelled"].includes(job.status)) return;
    const timer = window.setInterval(() => {
      fetch(`${API}/api/jobs/${job.id}`).then(r => r.json()).then(setJob).catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status]);

  const ready = Boolean(song && cover && title.trim() && !busy);
  const running = job && !["completed", "failed", "cancelled"].includes(job.status);
  const statusText = useMemo(() => health?.gpu ?? (health ? "CPU rendering" : "Checking system…"), [health]);

  async function prepareEditor() {
    if (!song || !cover || !ready) return;
    setBusy(true); setError(""); setJob(undefined); setProjectFiles([]);
    try {
      const body = new FormData();
      body.append("name", title.trim()); body.append("language",language); body.append("song", song); body.append("cover", cover);
      if (lyrics) body.append("lyrics", lyrics);
      const upload = await fetch(`${API}/api/projects`, { method: "POST", body });
      if (!upload.ok) throw new Error((await upload.json()).detail ?? "Upload failed");
      const project = await upload.json(); setProjectId(project.id);
      const prepared = await fetch(`${API}/api/projects/${project.id}/prepare`, { method: "POST" });
      if (!prepared.ok) throw new Error((await prepared.json()).detail ?? "Audio analysis or lyric alignment failed");
      const preparedData = await prepared.json();
      applyDirector(preparedData); setMetadata(preparedData);
      navigate(`/project/${project.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Something went wrong");
    } finally { setBusy(false); }
  }

  async function exportVideos(editor: EditorSettings, alignedLyrics: Cue[], backgrounds: File[], plan: ExportPlan) {
    if (!projectId) return;
    setBusy(true); setError(""); setJob(undefined);
    try {
      const lyricsSave = await fetch(`${API}/api/projects/${projectId}/lyrics`, {method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({lyrics:alignedLyrics})});
      if (!lyricsSave.ok) throw new Error((await lyricsSave.json()).detail ?? "Could not save lyric corrections");
      if (backgrounds.length) {
        const backgroundBody = new FormData(); backgrounds.forEach(background => backgroundBody.append("background", background));
        const backgroundUpload = await fetch(`${API}/api/projects/${projectId}/background`, {method:"POST",body:backgroundBody});
        if (!backgroundUpload.ok) throw new Error((await backgroundUpload.json()).detail ?? "Background upload failed");
      }
      const response = await fetch(`${API}/api/projects/${projectId}/render`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ options: { outputs: plan.outputs, ranges: plan.ranges, quality: plan.quality, encoder: "auto", lyrics_enabled: true, fps: 30, editor } }),
      });
      if (!response.ok) throw new Error((await response.json()).detail ?? "Could not start render");
      setJob(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Something went wrong");
    } finally { setBusy(false); }
  }

  function reset() { setJob(undefined); setError(""); }

  function applyDirector(data:{director?:{ranges?:{output:Output;start:number;duration?:number}[]}}) {
    if (!data.director?.ranges) return;
    setStarts(current => ({...current,...Object.fromEntries(data.director!.ranges!.map(item=>[item.output,clock(item.start)]))}));
    setEnds(current => ({...current,...Object.fromEntries(data.director!.ranges!.filter(item=>item.duration).map(item=>[item.output,clock(item.start+(item.duration??0))]))}));
  }

  async function loadProject(id: string) {
    setBusy(true); setError("");
    try {
      const [detailResponse, preparedResponse, songResponse, coverResponse] = await Promise.all([
        fetch(`${API}/api/projects/${id}`), fetch(`${API}/api/projects/${id}/prepare`,{method:"POST"}),
        fetch(`${API}/api/projects/${id}/assets/song`), fetch(`${API}/api/projects/${id}/assets/cover`),
      ]);
      if (![detailResponse,preparedResponse,songResponse,coverResponse].every(response=>response.ok)) throw new Error("The project could not be reopened.");
      const detail=await detailResponse.json(); const preparedData=await preparedResponse.json();
      const songBlob=await songResponse.blob(); const coverBlob=await coverResponse.blob();
      setSong(new File([songBlob],"project-song",{type:songBlob.type||"audio/wav"}));
      setCover(new File([coverBlob],"project-cover",{type:coverBlob.type||"image/png"}));
      setTitle(detail.name); setProjectId(id); setInitialEditor(detail.settings?.editor??{}); setProjectFiles(detail.files??[]);
      if(detail.settings?.outputs)setSelected(detail.settings.outputs); if(detail.settings?.ranges){setStarts(current=>({...current,...Object.fromEntries(detail.settings.ranges.map((item:{output:Output;start:number})=>[item.output,clock(item.start)]))}));setEnds(current=>({...current,...Object.fromEntries(detail.settings.ranges.filter((item:{duration?:number})=>item.duration).map((item:{output:Output;start:number;duration:number})=>[item.output,clock(item.start+item.duration)]))}))}
      if(detail.settings?.quality)setQuality(detail.settings.quality); if(!detail.settings?.ranges?.length)applyDirector(preparedData); setMetadata(preparedData);
    } catch(reason) { setError(reason instanceof Error?reason.message:"Could not open project"); }
    finally { setBusy(false); }
  }

  function newProject(){setMetadata(undefined);setProjectId("");setInitialEditor(undefined);setSong(undefined);setCover(undefined);setLyrics(undefined);setTitle("");setLanguage("en");setJob(undefined);setError("");setProjectFiles([]);setSelected(["teaser","chorus","lyrics","youtube"]);setStarts({teaser:"0",chorus:"0",lyrics:"0",youtube:"0"});setEnds({teaser:"0:15",chorus:"0:30",lyrics:"0:45",youtube:""});setQuality("high")}

  const editorLoaded = Boolean(metadata && song && cover && projectId);
  const editorElement = metadata && song && cover ? (
    <Editor song={song} cover={cover} cues={metadata.lyrics} bpm={metadata.bpm} duration={metadata.duration} sections={metadata.sections??[]} downbeats={metadata.downbeats??[]} director={(metadata as {director?:Record<string,unknown>}).director} initialSettings={initialEditor} job={job} api={API} busy={busy} error={error} projectId={projectId} files={projectFiles} outputs={selected} starts={starts} ends={ends} quality={quality} onOutputsChange={setSelected} onStartsChange={setStarts} onEndsChange={setEnds} onQualityChange={setQuality} onBack={()=>navigate("/create")} onExport={exportVideos}/>
  ) : null;

  const createPage = (
    <div className="app-shell">
      <aside>
        <a className="brand" href="#"><span className="brand-mark"><Activity /></span><span>Pulse <b>Studio</b></span></a>
        <nav>
          <a className="active"><WandSparkles size={18} /> Create</a>
          <a onClick={()=>navigate("/projects")}><Gauge size={18} /> Projects</a>
        </nav>
        <div className="system-card">
          <span className={`status-dot ${health?.nvenc ? "online" : ""}`} />
          <div><small>Render engine</small><strong>{statusText}</strong></div>
          <span className="chip">{health?.nvenc ? "NVENC" : "CPU"}</span>
        </div>
        <div className="version">Local-first · v0.1 Alpha</div>
      </aside>

      <main>
        <header><div><span className="eyebrow">NEW PROJECT</span><h1>Turn a song into motion.</h1><p>Upload your track, add the artwork and let Pulse build every format.</p></div><div className="template-pill"><Sparkles size={16} /> Classic Pulse</div></header>

        <section className="workspace-grid">
          <div className="panel setup-panel">
            <div className="source-panel-head"><div className="panel-title"><div><h2>Source material</h2><p>Everything stays on this machine.</p></div></div><button className="render-button" disabled={!ready || Boolean(running)} onClick={prepareEditor}>{busy ? lyrics?.name.toLowerCase().endsWith(".txt") ? "Aligning lyrics…" : "Analyzing…" : <>Continue to editor <ChevronRight size={19} /></>}</button></div>
            <label className="field-label">Project title</label>
            <input className="text-input" value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Midnight Drive" />
            <label className="field-label">Lyrics language</label>
            <select className="language-select" value={language} onChange={e=>setLanguage(e.target.value)}><option value="en">English</option><option value="auto">Auto detect</option><option value="it">Italiano</option><option value="es">Español</option><option value="fr">Français</option><option value="de">Deutsch</option><option value="pt">Português</option><option value="nl">Nederlands</option><option value="pl">Polski</option><option value="tr">Türkçe</option><option value="ru">Русский</option><option value="ja">日本語</option><option value="ko">한국어</option><option value="zh">中文</option></select>
            <div className="file-stack">
              <FileDrop label="Choose a song" hint="WAV, FLAC, MP3 or M4A" icon={<FileAudio size={19} />} accept="audio/*,.wav,.flac" file={song} onChange={setSong} />
              <FileDrop label="Choose cover artwork" hint="PNG, JPG or WebP" icon={<Image size={19} />} accept="image/*" file={cover} onChange={setCover} />
              <FileDrop label="Add synchronized lyrics" hint="SRT recommended, TXT supported" icon={<FileText size={19} />} accept=".srt,.txt" file={lyrics} onChange={setLyrics} optional />
            </div>
          </div>

        </section>

        {(job || error) && <section className={`render-card ${job?.status ?? "failed"}`}>
          {error ? <><CircleAlert /><div><strong>Could not start the render</strong><small>{error}</small></div></> : job && <>
            <div className="render-status-icon">{job.status === "completed" ? <Check /> : job.status === "failed" ? <CircleAlert /> : <Play />}</div>
            <div className="render-info"><strong>{job.stage}</strong><small>{job.message ?? `${job.project_name} · ${job.progress}%`}</small><div className="progress"><i style={{ width: `${job.progress}%` }} /></div>
              {job.status === "completed" && <div className="downloads">{job.outputs.map(file => <a href={`${API}/api/jobs/${job.id}/files/${file}`} key={file}><Download size={15} /> {file}</a>)}</div>}
            </div>
            {!running && <button className="icon-button" onClick={reset}><RotateCcw size={18} /></button>}
          </>}
        </section>}

      </main>
    </div>
  );

  if (path === "/projects" || path === "/") {
    return <Dashboard api={API} onOpen={project => navigate(`/project/${project.id}`)} onCreate={() => { newProject(); navigate("/create"); }} />;
  }
  if (path === "/create") return createPage;
  const projectMatch = path.match(/^\/project\/([a-f0-9]+)$/i);
  if (projectMatch) {
    return <EditorRoute id={projectMatch[1]} navigate={navigate} loadedId={editorLoaded ? projectId : ""} busy={busy} error={error} onLoad={loadProject}>
      {editorElement}
    </EditorRoute>;
  }
  window.history.replaceState({}, "", "/projects");
  return <Dashboard api={API} onOpen={project => navigate(`/project/${project.id}`)} onCreate={() => { newProject(); navigate("/create"); }} />;
}
