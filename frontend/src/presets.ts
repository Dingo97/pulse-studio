import type { EditorSettings } from "./Editor";

export const PRESET_SCHEMA = "https://pulse-studio.dev/schemas/preset-v1.json";
const STORAGE_KEY = "pulse-studio.community-presets.v1";
const NEW_DEFAULTS = { word_animation:"highlight", active_word_color:"#ff8a4c", safe_area:"auto", show_safe_guides:true, smart_crop:true, background_loop:"repeat", section_cuts:true, background_brightness:100, background_saturation:100, background_video_offset:0, background_video_speed:1, lyrics_x_landscape:.715, lyrics_y_landscape:.57, lyrics_x_vertical:.5, lyrics_y_vertical:.71, visualizer_x_landscape:.725, visualizer_y_landscape:.42, visualizer_x_vertical:.5, visualizer_y_vertical:.58 } as const;

export type PulsePreset = {
  $schema: string;
  formatVersion: 1;
  name: string;
  description?: string;
  author?: string;
  license?: string;
  tags?: string[];
  createdWith: string;
  settings: EditorSettings;
};

export function createPreset(name: string, settings: EditorSettings): PulsePreset {
  return {
    $schema: PRESET_SCHEMA, formatVersion: 1, name: name.trim().slice(0, 80),
    description: "Created with Pulse Studio", author: "", license: "CC0-1.0",
    tags: [], createdWith: "Pulse Studio 0.1.0-alpha.1", settings,
  };
}

export function parsePreset(source: string): PulsePreset {
  const value = JSON.parse(source) as Partial<PulsePreset>;
  if (value.formatVersion !== 1 || value.$schema !== PRESET_SCHEMA || !value.settings || typeof value.name !== "string") {
    throw new Error("This is not a supported Pulse Studio preset.");
  }
  value.settings = { ...NEW_DEFAULTS, ...value.settings } as EditorSettings;
  const s = value.settings as unknown as Record<string, unknown>;
  const oneOf = (key: string, values: string[]) => typeof s[key] === "string" && values.includes(s[key] as string);
  const integer = (key: string, min: number, max: number) => Number.isInteger(s[key]) && Number(s[key]) >= min && Number(s[key]) <= max;
  const bool = (key: string) => typeof s[key] === "boolean";
  const unit = (key: string) => typeof s[key] === "number" && Number.isFinite(s[key]) && Number(s[key]) >= 0 && Number(s[key]) <= 1;
  const color = (key: string) => typeof s[key] === "string" && /^#[0-9a-f]{6}$/i.test(s[key] as string);
  const valid =
    oneOf("background_mode", ["blurred_cover", "solid", "custom"]) && color("background_color") && integer("background_blur", 0, 80) && integer("background_brightness",20,150) && integer("background_saturation",0,200) && typeof s.background_video_offset === "number" && Number(s.background_video_offset)>=0 && Number(s.background_video_offset)<=600 && typeof s.background_video_speed === "number" && Number(s.background_video_speed)>=.25 && Number(s.background_video_speed)<=2 &&
    oneOf("visualizer", ["none", "bars", "wave", "ring"]) && bool("visualizer_enabled") && color("visualizer_color") && bool("visualizer_pulse") &&
    oneOf("overlay", ["none", "grain", "dust", "vignette", "scratches", "light_leaks", "film_burn", "rain", "scanlines", "vhs", "bokeh", "prism"]) && integer("overlay_intensity", 0, 100) && bool("cover_enabled") && bool("cover_shadow") &&
    typeof s.font_family === "string" && s.font_family.length > 0 && s.font_family.length <= 80 && integer("font_size", 24, 160) && color("text_color") &&
    bool("text_bold") && bool("text_italic") && oneOf("text_align", ["left", "center", "right"]) && color("shadow_color") &&
    integer("shadow_blur", 0, 60) && integer("shadow_distance", 0, 40) && integer("shadow_opacity", 0, 100) &&
    oneOf("animation", ["fade", "typewriter", "blur", "pop"]) && oneOf("animation_direction", ["up", "down", "left", "right", "none"]) &&
    oneOf("word_animation", ["none", "highlight", "pop", "karaoke", "bounce", "constellation", "impact", "ink"]) && color("active_word_color") &&
    oneOf("safe_area", ["auto", "youtube", "shorts", "reels", "tiktok", "none"]) && bool("show_safe_guides") && bool("smart_crop") &&
    oneOf("background_loop", ["repeat", "pingpong", "freeze"]) && bool("section_cuts") &&
    ["lyrics_x_landscape","lyrics_y_landscape","lyrics_x_vertical","lyrics_y_vertical","visualizer_x_landscape","visualizer_y_landscape","visualizer_x_vertical","visualizer_y_vertical"].every(unit);
  if (!valid) throw new Error("The preset contains missing, invalid or out-of-range settings.");
  return value as PulsePreset;
}

export function loadPresets(): PulsePreset[] {
  try { return (JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]") as PulsePreset[]).filter(item => item.formatVersion === 1).map(item => ({...item,settings:{...NEW_DEFAULTS,...item.settings}})); }
  catch { return []; }
}

export function storePresets(presets: PulsePreset[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(presets.slice(0, 100)));
}

export function downloadPreset(preset: PulsePreset) {
  const blob = new Blob([JSON.stringify(preset, null, 2) + "\n"], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${preset.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "pulse-preset"}.pulsepreset.json`;
  link.click();
  URL.revokeObjectURL(link.href);
}
