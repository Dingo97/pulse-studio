from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class JobStatus(StrEnum):
    queued = "queued"
    analyzing = "analyzing"
    rendering = "rendering"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class OutputKind(StrEnum):
    teaser = "teaser"
    chorus = "chorus"
    lyrics = "lyrics"
    youtube = "youtube"


class ClipRange(BaseModel):
    output: OutputKind
    start: float = Field(ge=0)
    duration: float | None = Field(default=None, gt=0)


class EditorSettings(BaseModel):
    background_mode: str = Field(default="blurred_cover", pattern="^(blurred_cover|solid|custom)$")
    background_color: str = Field(default="#0b0712", pattern="^#[0-9a-fA-F]{6}$")
    background_blur: int = Field(default=30, ge=0, le=80)
    background_brightness: int = Field(default=100, ge=20, le=150)
    background_saturation: int = Field(default=100, ge=0, le=200)
    background_video_offset: float = Field(default=0, ge=0, le=600)
    background_video_speed: float = Field(default=1, ge=.25, le=2)
    visualizer: str = Field(default="bars", pattern="^(none|bars|wave|ring)$")
    visualizer_enabled: bool = True
    visualizer_color: str = Field(default="#ffffff", pattern="^#[0-9a-fA-F]{6}$")
    visualizer_pulse: bool = True
    overlay: str = Field(default="grain", pattern="^(none|grain|dust|vignette|scratches|light_leaks|film_burn|rain|scanlines|vhs|bokeh|prism)$")
    overlay_intensity: int = Field(default=24, ge=0, le=100)
    cover_enabled: bool = True
    cover_shadow: bool = True
    font_family: str = Field(default="Arial", max_length=80)
    font_size: int = Field(default=64, ge=24, le=160)
    text_color: str = Field(default="#ffffff", pattern="^#[0-9a-fA-F]{6}$")
    text_bold: bool = True
    text_italic: bool = False
    text_align: str = Field(default="center", pattern="^(left|center|right)$")
    shadow_color: str = Field(default="#000000", pattern="^#[0-9a-fA-F]{6}$")
    shadow_blur: int = Field(default=18, ge=0, le=60)
    shadow_distance: int = Field(default=5, ge=0, le=40)
    shadow_opacity: int = Field(default=75, ge=0, le=100)
    animation: str = Field(default="fade", pattern="^(fade|typewriter|blur|pop)$")
    animation_direction: str = Field(default="up", pattern="^(up|down|left|right|none)$")
    word_animation: str = Field(default="highlight", pattern="^(none|highlight|pop|karaoke|bounce|constellation|impact|ink)$")
    active_word_color: str = Field(default="#ff8a4c", pattern="^#[0-9a-fA-F]{6}$")
    safe_area: str = Field(default="auto", pattern="^(auto|youtube|shorts|reels|tiktok|none)$")
    show_safe_guides: bool = True
    smart_crop: bool = True
    background_loop: str = Field(default="repeat", pattern="^(repeat|pingpong|freeze)$")
    section_cuts: bool = True
    lyrics_x_landscape: float = Field(default=.715, ge=0, le=1)
    lyrics_y_landscape: float = Field(default=.57, ge=0, le=1)
    lyrics_x_vertical: float = Field(default=.5, ge=0, le=1)
    lyrics_y_vertical: float = Field(default=.71, ge=0, le=1)
    visualizer_x_landscape: float = Field(default=.725, ge=0, le=1)
    visualizer_y_landscape: float = Field(default=.42, ge=0, le=1)
    visualizer_x_vertical: float = Field(default=.5, ge=0, le=1)
    visualizer_y_vertical: float = Field(default=.58, ge=0, le=1)


class RenderOptions(BaseModel):
    outputs: list[OutputKind] = Field(default_factory=lambda: [OutputKind.teaser])
    ranges: list[ClipRange] = Field(default_factory=list)
    fps: int = Field(default=30, ge=24, le=60)
    quality: str = Field(default="high", pattern="^(balanced|high|max)$")
    encoder: str = Field(default="auto", pattern="^(auto|nvenc|cpu)$")
    lyrics_enabled: bool = True
    editor: EditorSettings = Field(default_factory=EditorSettings)

    @model_validator(mode="after")
    def unique_outputs(self) -> "RenderOptions":
        self.outputs = list(dict.fromkeys(self.outputs))
        if not self.outputs:
            raise ValueError("Select at least one output.")
        return self


class ProjectCreated(BaseModel):
    id: str
    name: str


class ProjectView(BaseModel):
    id: str
    name: str
    status: str
    has_song: bool
    has_cover: bool
    has_lyrics: bool
    outputs: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    duration: float | None = None
    bpm: float | None = None
    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectView):
    settings: dict = Field(default_factory=dict)
    analysis: dict = Field(default_factory=dict)


class ProjectRename(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RenderRequest(BaseModel):
    options: RenderOptions


class JobView(BaseModel):
    id: str
    project_id: str
    project_name: str
    status: JobStatus
    progress: int
    stage: str
    message: str | None = None
    outputs: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class HealthView(BaseModel):
    status: str
    ffmpeg: bool
    nvenc: bool
    gpu: str | None = None


class WordCueView(BaseModel):
    text: str = Field(max_length=200)
    start: float = Field(ge=0)
    end: float = Field(ge=0)


class LyricCueView(BaseModel):
    start: float
    end: float
    text: str = Field(max_length=1000)
    words: list[WordCueView] = Field(default_factory=list, max_length=500)


class ProjectMetadata(BaseModel):
    duration: float
    bpm: float
    lyrics: list[LyricCueView]
    lyrics_source: str
    downbeats: list[float] = Field(default_factory=list)
    sections: list[float] = Field(default_factory=list)
    director: dict = Field(default_factory=dict)


class LyricsUpdate(BaseModel):
    lyrics: list[LyricCueView] = Field(max_length=10000)
