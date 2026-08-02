import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Check, Download, FileDown, FileUp, ImagePlus, ListMusic, MonitorPlay, Pause, Play, Save, SlidersHorizontal, Trash2, Type, Upload, Volume2, VolumeX } from "lucide-react";
import "./editor.css";
import "./editor-features.css";
import { createPreset, downloadPreset, loadPresets, parsePreset, storePresets, type PulsePreset } from "./presets";
import OverlayCanvas from "./OverlayCanvas";

export type TimedWord = { text: string; start: number; end: number };
export type Cue = { start: number; end: number; text: string; words?: TimedWord[] };
export type OutputKind = "teaser" | "chorus" | "lyrics" | "youtube";
export type ExportPlan = {outputs:OutputKind[];ranges:{output:OutputKind;start:number;duration:number}[];quality:string};
const EXPORTS:{id:OutputKind;title:string;meta:string}[]=[{id:"teaser",title:"Teaser",meta:"9:16"},{id:"chorus",title:"Chorus",meta:"9:16"},{id:"lyrics",title:"Lyrics cut",meta:"9:16"},{id:"youtube",title:"Full song",meta:"16:9 · YouTube"}];
const parseClock=(value:string)=>{const parts=value.trim().replace(",",".").split(":").map(Number);return parts.some(Number.isNaN)?NaN:parts.length===1?parts[0]:parts.slice(0,-1).reduce((total,part)=>total*60+part,0)*60+parts.at(-1)!};
export type EditorSettings = {
  background_mode: "blurred_cover" | "solid" | "custom"; background_color: string; background_blur: number; background_brightness:number; background_saturation:number; background_video_offset:number; background_video_speed:number;
  visualizer: "none" | "bars" | "wave" | "ring"; visualizer_enabled: boolean; visualizer_color: string; visualizer_pulse: boolean;
  overlay: "none" | "grain" | "dust" | "vignette" | "scratches" | "light_leaks" | "film_burn" | "rain" | "scanlines" | "vhs" | "bokeh" | "prism"; overlay_intensity: number; cover_enabled: boolean; cover_shadow: boolean;
  font_family: string; font_size: number; text_color: string; text_bold: boolean; text_italic: boolean; text_align: "left" | "center" | "right";
  shadow_color: string; shadow_blur: number; shadow_distance: number; shadow_opacity: number;
  animation: "fade" | "typewriter" | "blur" | "pop"; animation_direction: "up" | "down" | "left" | "right" | "none";
  word_animation: "none" | "highlight" | "pop" | "karaoke" | "bounce" | "constellation" | "impact" | "ink"; active_word_color: string;
  safe_area: "auto" | "youtube" | "shorts" | "reels" | "tiktok" | "none"; show_safe_guides: boolean;
  smart_crop: boolean; background_loop: "repeat" | "pingpong" | "freeze"; section_cuts: boolean;
  lyrics_x_landscape: number; lyrics_y_landscape: number; lyrics_x_vertical: number; lyrics_y_vertical: number;
  visualizer_x_landscape: number; visualizer_y_landscape: number; visualizer_x_vertical: number; visualizer_y_vertical: number;
};
export type RenderJob = { id: string; status: string; progress: number; stage: string; message?: string; outputs: string[] };
type DirectedRange={output:OutputKind;start:number;duration:number;score:number;reason:string};
type DirectorPlan={version?:number;intensity?:string;method?:string;signals?:{sections?:number;downbeats?:number;lyric_lines?:number;repeated_lines?:number};ranges?:DirectedRange[]};

const DEFAULTS: EditorSettings = {
  background_mode:"blurred_cover", background_color:"#0b0712", background_blur:30,
  visualizer:"bars", visualizer_enabled:true, visualizer_color:"#ffffff", visualizer_pulse:true,
  overlay:"grain", overlay_intensity:24, cover_enabled:true, cover_shadow:true,
  font_family:"Arial", font_size:64, text_color:"#ffffff", text_bold:true, text_italic:false, text_align:"center",
  shadow_color:"#000000", shadow_blur:18, shadow_distance:5, shadow_opacity:75, animation:"fade", animation_direction:"up",
  word_animation:"highlight", active_word_color:"#ff8a4c", safe_area:"auto", show_safe_guides:true,
  smart_crop:true, background_loop:"repeat", section_cuts:true, background_brightness:100, background_saturation:100, background_video_offset:0, background_video_speed:1,
  lyrics_x_landscape:.715, lyrics_y_landscape:.57, lyrics_x_vertical:.5, lyrics_y_vertical:.71,
  visualizer_x_landscape:.725, visualizer_y_landscape:.42, visualizer_x_vertical:.5, visualizer_y_vertical:.58,
};

type MovableLayer = "lyrics" | "visualizer";
type InstalledFont={family:string;filename:string;url:string};

export default function Editor({ song, cover, cues, bpm, duration, sections, downbeats, director, initialSettings, job, api, busy, error, projectId, files = [], outputs, starts, ends, quality, onOutputsChange, onStartsChange, onEndsChange, onQualityChange, onBack, onExport }: {
  song: File; cover: File; cues: Cue[]; bpm: number; duration: number; sections: number[]; downbeats:number[]; job?: RenderJob; api: string;
  busy?: boolean; error?: string; projectId?: string; files?: string[];
  director?: DirectorPlan; initialSettings?: Partial<EditorSettings>;
  outputs:OutputKind[];starts:Record<OutputKind,string>;ends:Record<OutputKind,string>;quality:string;
  onOutputsChange:(outputs:OutputKind[])=>void;onStartsChange:(starts:Record<OutputKind,string>)=>void;onEndsChange:(ends:Record<OutputKind,string>)=>void;onQualityChange:(quality:string)=>void;
  onBack: () => void; onExport: (settings: EditorSettings, lyrics: Cue[], backgrounds: File[], plan:ExportPlan) => void;
}) {
  const [settings, setSettings] = useState<EditorSettings>({...DEFAULTS,...initialSettings});
  const [section, setSection] = useState<"visuals"|"text"|"timing">("visuals");
  const [localCues, setLocalCues] = useState(cues);
  const [presets, setPresets] = useState<PulsePreset[]>(loadPresets);
  const [presetSelection,setPresetSelection]=useState("");
  const [presetNotice, setPresetNotice] = useState("");
  const [exportError,setExportError]=useState("");
  const [installedFonts,setInstalledFonts]=useState<InstalledFont[]>([]);
  const presetInput = useRef<HTMLInputElement>(null);
  const [visualTab, setVisualTab] = useState<"background"|"visualizer"|"overlay"|"cover">("background");
  const [backgrounds, setBackgrounds] = useState<File[]>([]);
  const [backgroundPreviewUrls,setBackgroundPreviewUrls]=useState<(string|null)[]>([]);
  const [backgroundUploadState,setBackgroundUploadState]=useState<"idle"|"optimizing"|"ready"|"failed">("idle");
  const [backgroundsStored,setBackgroundsStored]=useState(false);
  const backgroundUploadId=useRef(0);
  const [time, setTime] = useState(0); const [playing, setPlaying] = useState(false);
  const [volume, setVolume] = useState(1); const lastVolume = useRef(1);
  const [previewFormat, setPreviewFormat] = useState<"landscape"|"vertical">("landscape");
  const audio = useRef<HTMLAudioElement>(null);
  const backgroundVideoElement=useRef<HTMLVideoElement>(null);
  const lyricElement=useRef<HTMLDivElement>(null);
  const audioContext=useRef<AudioContext|null>(null);const analyser=useRef<AnalyserNode|null>(null);const audioSource=useRef<MediaElementAudioSourceNode|null>(null);
  const [spectrum,setSpectrum]=useState<number[]>(()=>Array(36).fill(.12));
  const preview = useRef<HTMLDivElement>(null);
  const [selectedLayer, setSelectedLayer] = useState<MovableLayer | null>(null);
  const [dragGuides, setDragGuides] = useState({x:false,y:false});
  const blurAmount = useRef(settings.background_blur || 30);
  const songUrl = useMemo(() => URL.createObjectURL(song), [song]);
  const coverUrl = useMemo(() => URL.createObjectURL(cover), [cover]);
  const backgroundUrls = useMemo(() => backgrounds.map(file => URL.createObjectURL(file)), [backgrounds]);
  const sectionIndex = settings.section_cuts ? Math.max(0, sections.reduce((found, value, index) => value <= time ? index : found, -1)) : 0;
  const backgroundIndex = backgrounds.length ? sectionIndex % backgrounds.length : 0;
  const background = backgrounds[backgroundIndex];
  const isVideoBackground=(file?:File)=>Boolean(file&&(file.type.startsWith("video/")||/\.(mp4|mov|mkv|webm|m4v)$/i.test(file.name)));
  const backgroundUrl = isVideoBackground(background) ? (backgroundPreviewUrls[backgroundIndex] ?? (backgroundUploadState==="failed"?backgroundUrls[backgroundIndex]:"")) : (backgroundUrls[backgroundIndex] ?? "");
  useEffect(() => { if (audio.current) audio.current.volume = volume; }, [volume]);
  useEffect(() => () => URL.revokeObjectURL(songUrl), [songUrl]);
  useEffect(() => () => URL.revokeObjectURL(coverUrl), [coverUrl]);
  useEffect(() => () => backgroundUrls.forEach(URL.revokeObjectURL), [backgroundUrls]);
  useEffect(()=>{const video=backgroundVideoElement.current;if(!video||!Number.isFinite(video.duration)||video.duration<=.05)return;syncBackgroundVideo(video)},[time,playing,backgroundUrl,backgroundIndex,settings.background_loop,settings.background_video_offset,settings.background_video_speed,settings.section_cuts]);
  useEffect(()=>{fetch(`${api}/api/fonts`).then(response=>response.json()).then(async(items:InstalledFont[])=>{setInstalledFonts(items);for(const item of items){try{const source=`url("${api}${item.url}")`;const face=new FontFace(item.family,source);await face.load();document.fonts.add(face)}catch(reason){console.warn(`Could not load font ${item.family}`,reason)}}}).catch(()=>undefined)},[api]);
  useEffect(()=>{if(!playing||!analyser.current)return;let frame=0;const data=new Uint8Array(analyser.current.frequencyBinCount);const tick=()=>{analyser.current!.getByteFrequencyData(data);const next=Array.from({length:36},(_,index)=>{const start=Math.floor(Math.pow(index/36,1.7)*(data.length-1));const end=Math.max(start+1,Math.floor(Math.pow((index+1)/36,1.7)*(data.length-1)));let peak=0;for(let i=start;i<end;i++)peak=Math.max(peak,data[i]);return Math.max(.06,peak/255)});setSpectrum(next);if(audio.current)setTime(audio.current.currentTime);frame=requestAnimationFrame(tick)};frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame)},[playing]);
  const cueIndex = localCues.findIndex(item => item.start <= time && time < item.end);
  const cue = cueIndex >= 0 ? localCues[cueIndex] : undefined;
  const cueWords = cue?.text.split(/\s+/).filter(Boolean) ?? [];
  const activeWord = cue ? cue.words?.length === cueWords.length
    ? cue.words.findIndex(word => word.start <= time && time < word.end)
    : Math.min(cueWords.length - 1, Math.max(0, Math.floor((time - cue.start) / Math.max(.01, cue.end - cue.start) * cueWords.length)))
    : -1;
  const previewWords=settings.animation==="typewriter"?cueWords.slice(0,Math.max(0,activeWord+1)):cueWords;
  const running = job && !["completed","failed","cancelled"].includes(job.status);
  useEffect(()=>{const element=lyricElement.current;if(!element||settings.animation==="typewriter"||cueIndex<0)return;const distance=34;const offsets={up:[0,distance],down:[0,-distance],left:[distance,0],right:[-distance,0],none:[0,0]} as const;const [x,y]=offsets[settings.animation_direction];const base="translate(-50%, -50%)";const entered=`translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`;const from:Keyframe=settings.animation==="blur"?{opacity:0,filter:"blur(18px)",transform:`${entered} scale(1.06)`}:settings.animation==="pop"?{opacity:0,transform:`${entered} scale(.72)`}:{opacity:0,transform:entered};const middle:Keyframe=settings.animation==="pop"?{opacity:1,transform:`${base} scale(1.06)`,offset:.72}:{opacity:1};const animation=element.animate([from,middle,{opacity:1,filter:"blur(0px)",transform:`${base} scale(1)`}],{duration:settings.animation==="blur"?620:settings.animation==="pop"?460:480,easing:settings.animation==="pop"?"cubic-bezier(.2,.9,.35,1.25)":"cubic-bezier(.22,.61,.36,1)",fill:"both"});return()=>animation.cancel()},[cueIndex,settings.animation,settings.animation_direction]);

  function set<K extends keyof EditorSettings>(key: K, value: EditorSettings[K]) { setSettings(current => ({...current,[key]:value})); }
  function position(layer: MovableLayer) {
    const suffix = previewFormat === "landscape" ? "landscape" : "vertical";
    return {x:settings[`${layer}_x_${suffix}` as keyof EditorSettings] as number,y:settings[`${layer}_y_${suffix}` as keyof EditorSettings] as number};
  }
  function moveLayer(event: React.PointerEvent<HTMLElement>, layer: MovableLayer) {
    if (!event.currentTarget.hasPointerCapture(event.pointerId) || !preview.current) return;
    const bounds = preview.current.getBoundingClientRect();
    const item = event.currentTarget.getBoundingClientRect();
    const halfX = item.width / bounds.width / 2; const halfY = item.height / bounds.height / 2;
    const platform = settings.safe_area === "auto" ? (previewFormat === "landscape" ? "youtube" : "tiktok") : settings.safe_area;
    const profiles:Record<string,[number,number,number,number]>={youtube:[.05,.05,.05,.1],shorts:[.055,.06,.1,.15],reels:[.055,.06,.1,.16],tiktok:[.055,.06,.11,.17],none:[0,0,0,0]};
    const [left,top,right,bottom] = profiles[platform] ?? profiles.youtube;
    const rawX=(event.clientX-bounds.left)/bounds.width, rawY=(event.clientY-bounds.top)/bounds.height;
    const snapX=Math.abs(rawX-.5)<.025, snapY=Math.abs(rawY-.5)<.025;
    const x = Math.min(1-right-halfX,Math.max(left+halfX,snapX?.5:rawX));
    const y = Math.min(1-bottom-halfY,Math.max(top+halfY,snapY?.5:rawY));
    setDragGuides({x:snapX,y:snapY});
    const suffix = previewFormat === "landscape" ? "landscape" : "vertical";
    setSettings(current=>({...current,[`${layer}_x_${suffix}`]:+x.toFixed(4),[`${layer}_y_${suffix}`]:+y.toFixed(4)}));
  }
  function dragStart(event: React.PointerEvent<HTMLElement>, layer: MovableLayer) { event.preventDefault();event.currentTarget.setPointerCapture(event.pointerId);setSelectedLayer(layer); }
  function dragEnd(event:React.PointerEvent<HTMLElement>){if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);setDragGuides({x:false,y:false})}
  function toggleBackgroundBlur(enabled:boolean){if(enabled)set("background_blur",blurAmount.current||30);else{if(settings.background_blur>0)blurAmount.current=settings.background_blur;set("background_blur",0)}}
  async function selectBackgrounds(files:File[]){
    const requestId=++backgroundUploadId.current;setBackgrounds(files);setBackgroundPreviewUrls(files.map(()=>null));setBackgroundsStored(false);
    if(!files.length){setBackgroundUploadState("idle");return}
    if(!projectId){setBackgroundUploadState("failed");setPresetNotice("Preview optimization is unavailable until the project is created.");return}
    setBackgroundUploadState("optimizing");setPresetNotice("Creating lightweight preview proxies. Original files are preserved for export.");
    try{const body=new FormData();files.forEach(file=>body.append("background",file));const response=await fetch(`${api}/api/projects/${projectId}/background`,{method:"POST",body});if(!response.ok)throw new Error((await response.json()).detail??"Background upload failed");const payload=await response.json() as {previews?:{index:number;preview_url:string|null}[]};if(requestId!==backgroundUploadId.current)return;const urls=files.map(()=>null as string|null);for(const item of payload.previews??[])if(item.preview_url)urls[item.index]=`${api}${item.preview_url}`;const missingProxy=files.some((file,index)=>isVideoBackground(file)&&!urls[index]);setBackgroundPreviewUrls(urls);setBackgroundsStored(true);setBackgroundUploadState(missingProxy?"failed":"ready");setPresetNotice(missingProxy?"Backgrounds uploaded, but a preview proxy could not be created. The original will be used in the editor.":"Backgrounds ready. The editor uses optimized proxies; export uses the originals.")}
    catch(reason){if(requestId!==backgroundUploadId.current)return;setBackgroundUploadState("failed");setPresetNotice(reason instanceof Error?`Preview optimization failed: ${reason.message}`:"Preview optimization failed. The original files will be used.")}
  }
  function syncBackgroundVideo(video:HTMLVideoElement){const sourceDuration=video.duration;if(!Number.isFinite(sourceDuration)||sourceDuration<=.05)return;let local=settings.section_cuts&&sections.length?time-(sections[sectionIndex]??0)+sectionIndex*sourceDuration*.381966:time;local=(Math.max(0,local)+settings.background_video_offset)*settings.background_video_speed;if(settings.background_loop==="freeze")local=Math.min(sourceDuration-.02,local);else if(settings.background_loop==="pingpong"){const cycle=local%(sourceDuration*2);local=cycle<=sourceDuration?cycle:sourceDuration*2-cycle}else local%=sourceDuration;local=Math.max(0,Math.min(sourceDuration-.02,local));if(Math.abs(video.currentTime-local)>.12)video.currentTime=local;video.playbackRate=settings.background_video_speed;if(playing)video.play().catch(()=>undefined);else video.pause()}
  async function installFont(file?:File){if(!file)return;try{const body=new FormData();body.append("font",file);const response=await fetch(`${api}/api/fonts`,{method:"POST",body});if(!response.ok){setPresetNotice((await response.json()).detail??"Font upload failed.");return}const item=await response.json() as InstalledFont;const source=`url("${api}${item.url}")`;const face=new FontFace(item.family,source);await face.load();document.fonts.add(face);setInstalledFonts(current=>[...current.filter(font=>font.family!==item.family),item]);set("font_family",item.family);setPresetNotice(`Installed ${item.family} permanently.`)}catch(reason){setPresetNotice(reason instanceof Error?`Font installation failed: ${reason.message}`:"Font installation failed.")}}
  function toggleOutput(output:OutputKind){onOutputsChange(outputs.includes(output)?outputs.filter(item=>item!==output):[...outputs,output])}
  function startExport(){if(backgroundUploadState==="optimizing"){setExportError("Wait for the background preview optimization to finish.");return}const ranges=[] as ExportPlan["ranges"];for(const output of outputs){const start=parseClock(starts[output]),end=parseClock(ends[output]);if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start||end>duration+.25){setExportError(`Check the From / To range for ${EXPORTS.find(item=>item.id===output)?.title}.`);return}ranges.push({output,start,duration:end-start})}if(!outputs.length){setExportError("Select at least one export.");return}setExportError("");onExport(settings,localCues,backgroundsStored?[]:backgrounds,{outputs,ranges,quality})}
  function savePreset() {
    const name = window.prompt("Preset name", "My Pulse preset")?.trim();
    if (!name) return;
    const next = [...presets.filter(item => item.name.toLowerCase() !== name.toLowerCase()), createPreset(name, settings)];
    setPresets(next); storePresets(next); setPresetNotice(`Saved “${name}” locally.`);
  }
  async function importPreset(file?: File) {
    if (!file) return;
    try {
      const preset = parsePreset(await file.text());
      const next = [...presets.filter(item => item.name.toLowerCase() !== preset.name.toLowerCase()), preset];
      setPresets(next); storePresets(next); setSettings(preset.settings); setPresetNotice(`Imported and applied “${preset.name}”.`);
    } catch (reason) { setPresetNotice(reason instanceof Error ? reason.message : "Preset import failed."); }
  }
  function removePreset(name: string) { const next=presets.filter(item=>item.name!==name);setPresets(next);storePresets(next); }
  function choosePreset(value:string){setPresetSelection(value);if(value==="classic"){setSettings(DEFAULTS);setPresetNotice("Applied Classic Pulse.");return}const preset=presets.find(item=>item.name===value);if(preset){setSettings(preset.settings);setPresetNotice(`Applied “${preset.name}”.`)}}
  function applyDirectorRanges(){const ranges=director?.ranges;if(!ranges?.length)return;onStartsChange({...starts,...Object.fromEntries(ranges.map(item=>[item.output,formatTime(item.start)]))});onEndsChange({...ends,...Object.fromEntries(ranges.map(item=>[item.output,formatTime(Math.min(duration,item.start+item.duration))]))});setPresetNotice("Auto Director suggestions applied to the export ranges.")}
  function previewDirectorRange(item:DirectedRange){setTime(item.start);if(audio.current)audio.current.currentTime=item.start}
  async function togglePlay(){const player=audio.current;if(!player)return;if(!audioContext.current){audioContext.current=new AudioContext();analyser.current=audioContext.current.createAnalyser();analyser.current.fftSize=512;analyser.current.smoothingTimeConstant=.72;audioSource.current=audioContext.current.createMediaElementSource(player);audioSource.current.connect(analyser.current);analyser.current.connect(audioContext.current.destination)}await audioContext.current.resume();if(player.paused){await player.play();setPlaying(true)}else{player.pause();setPlaying(false)}}
  const backgroundStyle = settings.background_mode === "solid" ? {background:settings.background_color} : {backgroundImage:`url(${settings.background_mode === "custom" && backgroundUrl ? backgroundUrl : coverUrl})`};
  const lyricPosition=position("lyrics"), visualizerPosition=position("visualizer");
  const beatPeriod=60/Math.max(1,bpm),anchor=downbeats[0]??0,beatDistance=Math.abs((((time-anchor+beatPeriod/2)%beatPeriod)+beatPeriod)%beatPeriod-beatPeriod/2),beatPulse=Math.exp(-beatDistance*18);
  const shadowAlpha=Math.round(settings.shadow_opacity*2.55).toString(16).padStart(2,"0");
  const lyricStyle = {fontFamily:settings.font_family,fontSize:`${Math.max(18,settings.font_size*.45)}px`,color:settings.text_color,fontWeight:settings.text_bold?800:500,fontStyle:settings.text_italic?"italic":"normal",textAlign:settings.text_align,textShadow:`0 ${settings.shadow_distance}px ${Math.max(1,settings.shadow_blur)}px ${settings.shadow_color}${shadowAlpha}, 0 1px 2px #000000aa`,left:`${lyricPosition.x*100}%`,top:`${lyricPosition.y*100}%`,right:"auto",transform:"translate(-50%,-50%)"} as const;

  return <div className="editor-shell">
    <header className="editor-top"><button onClick={onBack}><ArrowLeft/> Project setup</button><div className="editor-title"><strong>Live editor</strong><small>{Math.round(bpm)} BPM · {Math.floor(duration/60)}:{String(Math.round(duration%60)).padStart(2,"0")}</small></div><button className="export-top" disabled={Boolean(running)||busy||!outputs.length||backgroundUploadState==="optimizing"} onClick={startExport}>{backgroundUploadState==="optimizing"?"Optimizing background…":busy?"Starting…":running?"Rendering…":"Export videos"}</button></header>
    <div className="editor-body">
      <aside className="editor-nav"><button className={section==="visuals"?"active":""} onClick={()=>setSection("visuals")}><MonitorPlay/>Visuals</button><button className={section==="text"?"active":""} onClick={()=>setSection("text")}><Type/>Lyrics style</button><button className={section==="timing"?"active":""} onClick={()=>setSection("timing")}><ListMusic/>Lyrics & timing</button></aside>
      <section className="preview-area">
        <div ref={preview} className={`video-preview preview-${previewFormat}`} style={backgroundStyle} onPointerDown={()=>setSelectedLayer(null)}>
          {settings.background_mode==="custom"&&backgroundUrl&&isVideoBackground(background)&&<video ref={backgroundVideoElement} className="preview-background-video" src={backgroundUrl} muted playsInline preload="auto" disablePictureInPicture onLoadedMetadata={e=>syncBackgroundVideo(e.currentTarget)}/>}
          <div className="preview-blur" style={{backdropFilter:`blur(${settings.background_blur/3}px) brightness(${settings.background_brightness}%) saturate(${settings.background_saturation}%)`}}/>
          {settings.cover_enabled&&<img src={coverUrl} className={settings.cover_shadow?"cover-shadow":""} style={{transform:`translateY(-50%) scale(${1+(settings.visualizer_pulse?beatPulse*.045:0)})`}}/>}
          {dragGuides.x&&<div className="alignment-guide vertical"/>}{dragGuides.y&&<div className="alignment-guide horizontal"/>}
          {settings.visualizer_enabled&&settings.visualizer!=="none"&&<div className={`live-viz draggable-layer ${selectedLayer==="visualizer"?"selected":""} ${settings.visualizer}`} data-layer="Visualizer" onPointerDown={e=>{e.stopPropagation();dragStart(e,"visualizer")}} onPointerMove={e=>moveLayer(e,"visualizer")} onPointerUp={dragEnd} onPointerCancel={dragEnd} style={{color:settings.visualizer_color,left:`${visualizerPosition.x*100}%`,top:`${visualizerPosition.y*100}%`,right:"auto",transform:`translate(-50%,-50%) scale(${1+(settings.visualizer_pulse?beatPulse*.09:0)})`}}>{settings.visualizer==="wave"?<svg viewBox="0 0 360 100" preserveAspectRatio="none"><polyline points={spectrum.map((level,index)=>`${index*10},${50+(index%2?1:-1)*level*42}`).join(" ")}/></svg>:settings.visualizer==="ring"?<b style={{transform:`scale(${.82+spectrum.slice(0,8).reduce((a,b)=>a+b,0)/18})`}}/>:spectrum.slice(0,28).map((level,i)=><i key={i} style={{height:`${Math.max(8,level*100)}%`}}/>)}</div>}
          <div ref={lyricElement} key={`${cueIndex}-${settings.animation}-${settings.animation_direction}`} className={`live-lyric motion-runtime draggable-layer ${selectedLayer==="lyrics"?"selected":""} anim-${settings.animation} dir-${settings.animation_direction} word-${settings.word_animation}`} data-layer="Lyrics" onPointerDown={e=>{e.stopPropagation();dragStart(e,"lyrics")}} onPointerMove={e=>moveLayer(e,"lyrics")} onPointerUp={dragEnd} onPointerCancel={dragEnd} style={lyricStyle}>{previewWords.length?previewWords.map((word,index)=>{const state=index===activeWord?"active":index<activeWord?"sung":"future";const accented=index===activeWord||settings.word_animation==="karaoke"&&index<activeWord;return <span className={state} style={accented?{color:settings.active_word_color}:undefined} key={`${word}-${index}`}>{word} </span>}):localCues.length?null:"Your synchronized lyrics will appear here"}</div>
          {settings.show_safe_guides&&settings.safe_area!=="none"&&<div className={`safe-guide safe-${settings.safe_area==="auto"?(previewFormat==="landscape"?"youtube":"tiktok"):settings.safe_area}`}><span>SAFE AREA</span></div>}
          {settings.overlay!=="none"&&<OverlayCanvas type={settings.overlay} intensity={settings.overlay_intensity} time={time} beatPulse={beatPulse}/>}
        </div>
        <div className="player"><button onClick={togglePlay}>{playing?<Pause/>:<Play/>}</button><span>{time.toFixed(1)}s</span><input type="range" min="0" max={duration||1} step=".05" value={time} onChange={e=>{const value=+e.target.value;setTime(value);if(audio.current)audio.current.currentTime=value}}/><span>{duration.toFixed(1)}s</span><button className="volume-toggle" title={volume===0?"Unmute":"Mute"} onClick={()=>{if(volume===0){setVolume(lastVolume.current||1)}else{lastVolume.current=volume;setVolume(0)}}}>{volume===0?<VolumeX/>:<Volume2/>}</button><input className="volume-slider" type="range" min="0" max="1" step=".01" value={volume} onChange={e=>setVolume(+e.target.value)}/><select className="preview-format" value={previewFormat} onChange={e=>setPreviewFormat(e.target.value as "landscape"|"vertical")}><option value="landscape">16:9</option><option value="vertical">9:16</option></select><audio ref={audio} src={songUrl} onTimeUpdate={e=>setTime(e.currentTarget.currentTime)} onEnded={()=>setPlaying(false)}/></div>
        <div className="export-planner"><div className="export-planner-head"><div><strong>Choose your exports</strong><small>Select the videos and define each exact range in mm:ss.</small></div><label>Quality<select value={quality} onChange={e=>onQualityChange(e.target.value)}><option value="balanced">Balanced</option><option value="high">High</option><option value="max">Maximum</option></select></label></div><div className="export-plan-grid">{EXPORTS.map(output=><div className={`export-plan-row ${outputs.includes(output.id)?"selected":""}`} key={output.id}><button className="plan-check" onClick={()=>toggleOutput(output.id)}>{outputs.includes(output.id)&&<Check/>}</button><button className="plan-name" onClick={()=>toggleOutput(output.id)}><strong>{output.title}</strong><small>{output.meta}</small></button><label>From<input value={starts[output.id]} onChange={e=>onStartsChange({...starts,[output.id]:e.target.value})} placeholder="0:00"/></label><span>→</span><label>To<input value={ends[output.id]} onChange={e=>onEndsChange({...ends,[output.id]:e.target.value})} placeholder={`${Math.floor(duration/60)}:${String(Math.floor(duration%60)).padStart(2,"0")}`}/></label></div>)}</div>{exportError&&<p className="export-plan-error">{exportError}</p>}</div>
        {error&&<div className="editor-job failed"><div><strong>Export failed</strong><small>{error}</small></div></div>}
        {!job&&files.length>0&&projectId&&<div className="editor-job completed"><div><strong>Rendered earlier</strong><small>Files from the last completed render</small></div><span>{files.map(file=><a key={file} href={`${api}/api/projects/${projectId}/files/${file}`}><Download/> {file}</a>)}</span></div>}
        {job&&<div className={`editor-job ${job.status}`}><div><strong>{job.stage}</strong><small>{job.message??`${job.progress}% complete`}</small><i><b style={{width:`${job.progress}%`}}/></i></div>{job.status==="completed"&&<span>{job.outputs.map(file=><a key={file} href={`${api}/api/jobs/${job.id}/files/${file}`}><Download/> {file}</a>)}</span>}</div>}
      </section>
      <aside className="inspector">
        {director&&<details className="director-card"><summary><div><strong>Auto Director</strong><small>{director.ranges?.length??0} suggested ranges · inspect and apply</small></div><span>{director.intensity??"balanced"}</span></summary><div className="director-details"><p>{director.method??"Musical analysis ready."}</p><div className="director-signals"><span>{director.signals?.sections??Math.max(0,sections.length-1)} sections</span><span>{director.signals?.downbeats??downbeats.length} downbeats</span><span>{director.signals?.repeated_lines??0} repeated lines</span></div>{director.ranges?.filter(item=>item.output!=="youtube").map(item=><button className="director-range" key={item.output} onClick={()=>previewDirectorRange(item)}><span><strong>{EXPORTS.find(output=>output.id===item.output)?.title}</strong><small>{formatTime(item.start)} → {formatTime(item.start+item.duration)}</small></span><span><b>{Math.round(item.score*100)}%</b><small>{item.reason}</small></span></button>)}<button className="director-apply" onClick={applyDirectorRanges}>Use suggested ranges</button></div></details>}
        <div className="preset-panel">
          <div className="preset-head"><div><strong>Community presets</strong><small>Portable, safe and open.</small></div><button title="Save current preset" onClick={savePreset}><Save/></button><button title="Export current preset" onClick={()=>downloadPreset(createPreset("My Pulse preset",settings))}><FileDown/></button><button title="Import preset" onClick={()=>presetInput.current?.click()}><FileUp/></button><input ref={presetInput} type="file" accept=".json,.pulsepreset.json,application/json" onChange={e=>importPreset(e.target.files?.[0])}/></div>
          <div className="preset-select-row"><select value={presetSelection} onChange={event=>choosePreset(event.target.value)}><option value="" disabled>Choose a preset…</option><option value="classic">Classic Pulse · Built in</option>{presets.length>0&&<optgroup label="Community & local">{presets.map(preset=><option value={preset.name} key={preset.name}>{preset.name}{preset.author?` · ${preset.author}`:""}</option>)}</optgroup>}</select>{presetSelection&&presetSelection!=="classic"&&<><button title="Export selected preset" onClick={()=>{const preset=presets.find(item=>item.name===presetSelection);if(preset)downloadPreset(preset)}}><FileDown/></button><button title="Delete selected preset" onClick={()=>{removePreset(presetSelection);setPresetSelection("");setPresetNotice("Preset removed.")}}><Trash2/></button></>}</div>
          {presetNotice&&<p className="preset-notice">{presetNotice}</p>}
        </div>
        {section==="text"&&<FontLibrary fonts={installedFonts} selected={settings.font_family} onSelect={family=>set("font_family",family)} onInstall={installFont}/>}
        {section==="visuals"?<>
          <div className="inspector-heading"><div><h2>Visuals</h2><p>Build the scene layer by layer.</p></div><SlidersHorizontal/></div>
          <div className="segmented">{(["background","visualizer","overlay","cover"] as const).map(tab=><button className={visualTab===tab?"active":""} onClick={()=>setVisualTab(tab)} key={tab}>{tab}</button>)}</div>
          {visualTab==="background"&&<div className="control-stack"><ControlTitle title="Background"/><Choice values={["blurred_cover","solid","custom"]} selected={settings.background_mode} onSelect={v=>set("background_mode",v as EditorSettings["background_mode"])}/>{settings.background_mode==="custom"&&<label className={`asset-upload ${backgroundUploadState}`}><input type="file" multiple accept="image/*,video/mp4,video/webm,video/quicktime,.mkv" onChange={e=>selectBackgrounds(Array.from(e.target.files??[]))}/><ImagePlus/><span><strong>{backgroundUploadState==="optimizing"?"Optimizing preview…":backgrounds.length?`${backgrounds.length} background${backgrounds.length>1?"s":""} ready`:"Upload backgrounds"}</strong><small>{backgroundUploadState==="ready"?"Proxy preview · original quality on export":"Images and looping videos · up to 20"}</small></span><Upload/></label>}{settings.background_mode==="solid"&&<Color label="Background color" value={settings.background_color} onChange={v=>set("background_color",v)}/>}<Switch label="Background blur" value={settings.background_blur>0} onChange={toggleBackgroundBlur}/>{settings.background_blur>0&&<Range label="Blur amount" value={settings.background_blur} max={80} onChange={v=>{blurAmount.current=v;set("background_blur",v)}}/>}<Switch label="Smart crop 16:9 / 9:16" value={settings.smart_crop} onChange={v=>set("smart_crop",v)}/><Switch label="Cut on musical sections" value={settings.section_cuts} onChange={v=>set("section_cuts",v)}/><label className="select-row"><span>Short video loop</span><select value={settings.background_loop} onChange={e=>set("background_loop",e.target.value as EditorSettings["background_loop"])}><option value="pingpong">Ping-pong</option><option value="repeat">Repeat</option><option value="freeze">Freeze last frame</option></select></label></div>}
          {visualTab==="visualizer"&&<div className="control-stack"><ControlTitle title="Audio visualizer"/><Choice values={["none","bars","wave","ring"]} selected={settings.visualizer} onSelect={v=>set("visualizer",v as EditorSettings["visualizer"])}/><Switch label="Enabled" value={settings.visualizer_enabled} onChange={v=>set("visualizer_enabled",v)}/><Switch label="Pulse on beats" value={settings.visualizer_pulse} onChange={v=>set("visualizer_pulse",v)}/><Color label="Visualizer color" value={settings.visualizer_color} onChange={v=>set("visualizer_color",v)}/></div>}
          {visualTab==="background"&&settings.background_mode!=="solid"&&<div className="control-stack background-extra"><ControlTitle title="Background filters"/><Range label="Brightness" value={settings.background_brightness} max={150} onChange={v=>set("background_brightness",Math.max(20,v))}/><Range label="Saturation" value={settings.background_saturation} max={200} onChange={v=>set("background_saturation",v)}/>{settings.background_mode==="custom"&&<><ControlTitle title="Video timing"/><Range label="Start offset (seconds)" value={settings.background_video_offset} max={60} onChange={v=>set("background_video_offset",v)}/><label className="select-row"><span>Playback speed</span><select value={settings.background_video_speed} onChange={e=>set("background_video_speed",+e.target.value)}><option value="0.5">0.5×</option><option value="0.75">0.75×</option><option value="1">1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></label></>}</div>}
          {visualTab==="overlay"&&<div className="control-stack"><ControlTitle title="Overlay"/><Choice values={["none","grain","dust","vignette","scratches","light_leaks","film_burn","rain","scanlines","vhs","bokeh","prism"]} selected={settings.overlay} onSelect={v=>set("overlay",v as EditorSettings["overlay"])}/><Range label="Intensity" value={settings.overlay_intensity} max={100} onChange={v=>set("overlay_intensity",v)}/><small className="control-hint">VHS adds analog tracking, scanlines and subtle color bleed. Light leaks and film burn react to the beat.</small></div>}
          {visualTab==="cover"&&<div className="control-stack"><ControlTitle title="Cover art"/><div className="cover-thumb"><img src={coverUrl}/><Check/></div><Switch label="Show cover" value={settings.cover_enabled} onChange={v=>set("cover_enabled",v)}/><Switch label="Cover shadow" value={settings.cover_shadow} onChange={v=>set("cover_shadow",v)}/></div>}
        </>:section==="text"?<TextControls settings={settings} set={set}/>:<div className="timing-editor"><div className="inspector-heading"><div><h2>Lyrics & timing</h2><p>Review the automatic alignment before export.</p></div><ListMusic/></div>{localCues.map((item,index)=><div className={item===cue?"timing-cue active":"timing-cue"} key={index} onClick={()=>{setTime(item.start);if(audio.current)audio.current.currentTime=item.start}}><div><input type="number" step=".05" value={item.start.toFixed(2)} onChange={e=>setLocalCues(current=>current.map((cue,i)=>i===index?{...cue,start:+e.target.value}:cue))}/><span>→</span><input type="number" step=".05" value={item.end.toFixed(2)} onChange={e=>setLocalCues(current=>current.map((cue,i)=>i===index?{...cue,end:+e.target.value}:cue))}/></div><textarea value={item.text} onChange={e=>setLocalCues(current=>current.map((cue,i)=>i===index?{...cue,text:e.target.value}:cue))}/></div>)}</div>}
      </aside>
    </div>
  </div>;
}

function ControlTitle({title}:{title:string}){return <h3 className="control-title">{title}</h3>}
function formatTime(value:number){const total=Math.max(0,Math.round(value));return `${Math.floor(total/60)}:${String(total%60).padStart(2,"0")}`}
function Choice({values,selected,onSelect}:{values:string[];selected:string;onSelect:(v:string)=>void}){const labels:Record<string,string>={constellation:"Spatial",impact:"Impact",ink:"Ink reveal"};return <div className="choice-grid">{values.map(v=><button className={selected===v?"active":""} onClick={()=>onSelect(v)} key={v}>{labels[v]??v.replaceAll("_"," ")}</button>)}</div>}
function Switch({label,value,onChange}:{label:string;value:boolean;onChange:(v:boolean)=>void}){return <label className="switch-row"><span>{label}</span><input type="checkbox" checked={value} onChange={e=>onChange(e.target.checked)}/><i/></label>}
function Range({label,value,max,onChange}:{label:string;value:number;max:number;onChange:(v:number)=>void}){return <label className="range-row"><span>{label}<b>{value}</b></span><input type="range" min="0" max={max} value={value} onChange={e=>onChange(+e.target.value)}/></label>}
function Color({label,value,onChange}:{label:string;value:string;onChange:(v:string)=>void}){return <label className="color-row"><span>{label}</span><input type="color" value={value} onChange={e=>onChange(e.target.value)}/><code>{value}</code></label>}
function FontLibrary({fonts,selected,onSelect,onInstall}:{fonts:InstalledFont[];selected:string;onSelect:(family:string)=>void;onInstall:(file?:File)=>void}){const builtins=["Arial","Arial Black","Georgia","Impact","Trebuchet MS","Verdana","Tahoma","Courier New","Times New Roman"];return <div className="font-library"><div><strong>Font library</strong><small>Custom TTF/OTF fonts remain installed for every project.</small></div><select value={selected} onChange={e=>onSelect(e.target.value)}>{builtins.map(font=><option key={font}>{font}</option>)}{fonts.length>0&&<optgroup label="Installed fonts">{fonts.map(font=><option key={font.filename}>{font.family}</option>)}</optgroup>}</select><label><Upload/> Install font<input type="file" accept=".ttf,.otf,font/ttf,font/otf" onChange={e=>onInstall(e.target.files?.[0])}/></label></div>}
function TextControls({settings,set}:{settings:EditorSettings;set:<K extends keyof EditorSettings>(k:K,v:EditorSettings[K])=>void}){return <div className="control-stack"><ControlTitle title="Typography"/><label className="select-row"><span>Font</span><select value={settings.font_family} onChange={e=>set("font_family",e.target.value)}><option>Arial</option><option>Georgia</option><option>Impact</option><option>Trebuchet MS</option><option>Courier New</option></select></label><Range label="Size" value={settings.font_size} max={160} onChange={v=>set("font_size",Math.max(24,v))}/><Color label="Text color" value={settings.text_color} onChange={v=>set("text_color",v)}/><div className="format-row"><button className={settings.text_bold?"active":""} onClick={()=>set("text_bold",!settings.text_bold)}>B</button><button className={settings.text_italic?"active":""} onClick={()=>set("text_italic",!settings.text_italic)}><i>I</i></button>{(["left","center","right"] as const).map(v=><button className={settings.text_align===v?"active":""} onClick={()=>set("text_align",v)} key={v}>{v[0].toUpperCase()}</button>)}</div><ControlTitle title="Platform safe area"/><Choice values={["auto","youtube","shorts","reels","tiktok","none"]} selected={settings.safe_area} onSelect={v=>set("safe_area",v as EditorSettings["safe_area"])}/><Switch label="Show safe-area guides" value={settings.show_safe_guides} onChange={v=>set("show_safe_guides",v)}/><ControlTitle title="Word-by-word"/><Choice values={["none","highlight","pop","karaoke","bounce","constellation","impact","ink"]} selected={settings.word_animation} onSelect={v=>set("word_animation",v as EditorSettings["word_animation"])}/><Color label="Active word" value={settings.active_word_color} onChange={v=>set("active_word_color",v)}/><ControlTitle title="Text shadow"/><Color label="Shadow color" value={settings.shadow_color} onChange={v=>set("shadow_color",v)}/><Range label="Blur" value={settings.shadow_blur} max={60} onChange={v=>set("shadow_blur",v)}/><Range label="Distance" value={settings.shadow_distance} max={40} onChange={v=>set("shadow_distance",v)}/><Range label="Opacity" value={settings.shadow_opacity} max={100} onChange={v=>set("shadow_opacity",v)}/><ControlTitle title="Line animation"/><Choice values={["fade","typewriter","blur","pop"]} selected={settings.animation} onSelect={v=>set("animation",v as EditorSettings["animation"])}/><Choice values={["up","down","left","right","none"]} selected={settings.animation_direction} onSelect={v=>set("animation_direction",v as EditorSettings["animation_direction"])}/></div>}
