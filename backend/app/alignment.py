from __future__ import annotations

import re
import json
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .config import settings
from .text import repair_mojibake


WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True)
class TimedWord:
    text: str
    start: float
    end: float


ALIGNMENT_VERSION = 13


def _isolate_vocals(audio: Path) -> Path | None:
    """Extract the vocal stem with Demucs so Whisper hears the words, not the mix."""
    model_name = settings.demucs_model or "htdemucs"
    cached = audio.with_name("vocals.demucs.wav" if model_name == "htdemucs" else f"vocals.{model_name}.wav")
    if cached.exists():
        return cached
    try:
        import torch
        from demucs.apply import apply_model
        from demucs.audio import AudioFile
        from demucs.pretrained import get_model
    except ImportError:
        print("alignment: demucs not installed; transcribing the full mix", flush=True)
        return None
    try:
        started = time.time()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = get_model(model_name)
        model.cpu().eval()
        track = AudioFile(str(audio)).read(streams=0, samplerate=model.samplerate, channels=model.audio_channels)
        reference = track.mean(0)
        scale = reference.std() + 1e-8
        track = (track - reference.mean()) / scale
        with torch.no_grad():
            sources = apply_model(model, track[None], device=device, split=True, overlap=0.35, shifts=1, progress=False)[0]
        vocals = sources[model.sources.index("vocals")] * scale + reference.mean()
        import soundfile as sf
        sf.write(str(cached), vocals.cpu().clamp(-1, 1).numpy().T, model.samplerate)
        del model, sources, track, vocals
        if device == "cuda":
            torch.cuda.empty_cache()
        print(f"alignment: {model_name} vocal isolation on {device} in {time.time() - started:.1f}s", flush=True)
        return cached
    except Exception as exc:
        print(f"alignment: demucs failed ({exc}); transcribing the full mix", flush=True)
        cached.unlink(missing_ok=True)
        return None


def align_txt(audio: Path, lyrics_txt: Path, output_srt: Path, language: str = "en") -> Path:
    """Keep the supplied words and infer their timing from local Whisper output."""
    lines = [clean for raw in repair_mojibake(lyrics_txt.read_text(encoding="utf-8-sig")).splitlines() if (clean := re.sub(r"\s+", " ", raw).strip()) and not _is_section_label(clean)]
    if not lines:
        raise ValueError("The lyrics TXT file is empty.")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper is not installed.") from exc

    settings.models_dir.mkdir(parents=True, exist_ok=True)
    try:
        model = WhisperModel(settings.whisper_model, device="cuda", compute_type="float16", download_root=str(settings.models_dir))
        print("alignment: whisper running on CUDA (float16)", flush=True)
    except Exception as exc:
        print(f"alignment: CUDA unavailable ({exc}); falling back to CPU (int8)", flush=True)
        model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8", download_root=str(settings.models_dir))
    vocals = _isolate_vocals(audio)
    prompt = " ".join(lines)
    segments, _ = model.transcribe(
        str(vocals or audio), language=None if language == "auto" else language, beam_size=5,
        word_timestamps=True, vad_filter=False, condition_on_previous_text=False,
        initial_prompt=prompt[:500], hotwords=None,
    )
    heard: list[TimedWord] = []
    for segment in segments:
        for word in segment.words or []:
            normalized = _normalize(word.word)
            probability = float(getattr(word, "probability", 1.0) or 0.0)
            if normalized and probability >= .08:
                heard.append(TimedWord(normalized, float(word.start), max(float(word.start) + .02, float(word.end))))
    heard = _merge_elisions(heard, language)
    if not heard:
        raise RuntimeError("Whisper could not detect sung words in this track.")
    vocal_intervals = _vocal_intervals(vocals or audio)

    target: list[str] = []
    ranges: list[tuple[int, int]] = []
    for line in lines:
        start = len(target)
        target.extend(_normalize(token) for token in WORD.findall(line))
        ranges.append((start, len(target)))
    mapping, matched = _map_lines(target, ranges, heard)

    # A line is a trustworthy anchor only if enough of its words were actually heard;
    # lines whisper missed (fast rap, stacked vocals) must not inherit interpolated garbage.
    entries: list[dict] = []
    for line, (first, last) in zip(lines, ranges):
        if last <= first:
            continue
        total_words = last - first
        matched_indices = [i for i in range(first, last) if matched[i]]
        matched_words = len(matched_indices)
        reliable = (matched_words >= 2 and matched_words / total_words >= 0.4) or (total_words <= 2 and matched_words == total_words)
        first_anchor = matched_indices[0] if matched_indices else first
        last_anchor = matched_indices[-1] if matched_indices else last - 1
        leading = first_anchor - first
        trailing = last - 1 - last_anchor
        estimated_start = max(0.0, heard[mapping[first_anchor]].start - min(.75, leading * .18))
        if leading and vocal_intervals:
            anchor_time = heard[mapping[first_anchor]].start
            onset = next((start for start, end in reversed(vocal_intervals) if start <= anchor_time <= end + .18), None)
            if onset is not None:
                maximum_lookback = min(2.8, .9 + leading * .65)
                estimated_start = min(estimated_start, max(onset, anchor_time - maximum_lookback))
        entries.append({
            "line": line, "first": first, "last": last, "reliable": reliable,
            "start": estimated_start,
            "end": heard[mapping[last_anchor]].end + min(.75, trailing * .18),
        })
    if not entries:
        raise RuntimeError("No lyric lines could be aligned.")

    previous_end = 0.0
    for entry in entries:
        if entry["reliable"] and (entry["start"] < previous_end - 0.5 or entry["end"] <= entry["start"]):
            entry["reliable"] = False
        if entry["reliable"]:
            previous_end = entry["end"]

    # Spread runs of unheard lines across the gap between anchors, weighted by word count.
    try:
        import soundfile as sf
        total_end = float(sf.info(str(audio)).duration) - .05
    except Exception:
        total_end = heard[-1].end + 0.5
    index = 0
    while index < len(entries):
        if entries[index]["reliable"]:
            index += 1
            continue
        stop = index
        while stop < len(entries) and not entries[stop]["reliable"]:
            stop += 1
        window_start = entries[index - 1]["end"] + 0.05 if index else 0.0
        window_end = entries[stop]["start"] - 0.05 if stop < len(entries) else total_end
        if window_end - window_start < 0.4 * (stop - index):
            window_end = window_start + 0.4 * (stop - index)
        weights = [entry["last"] - entry["first"] for entry in entries[index:stop]]
        total_weight = sum(weights) or 1
        cursor = window_start
        for entry, weight in zip(entries[index:stop], weights):
            span = (window_end - window_start) * weight / total_weight
            entry["start"], entry["end"] = cursor, cursor + max(0.3, span - 0.02)
            cursor += span
        index = stop

    blocks: list[str] = []
    word_cues: list[dict] = []
    previous_end = 0.0
    for number, entry in enumerate(entries, 1):
        line, first, last = entry["line"], entry["first"], entry["last"]
        if entry["reliable"]:
            start = max(previous_end, entry["start"] - .08)
            next_start = entries[number]["start"] if number < len(entries) else None
            natural_end = entry["end"] + .16
            end = max(start + .3, min(natural_end, next_start - .035) if next_start is not None and next_start > start + .3 else natural_end)
        else:
            start = max(previous_end, entry["start"])
            end = max(start + .3, entry["end"])
        blocks.append(f"{number}\n{_time(start)} --> {_time(end)}\n{line}")
        display_words = line.split()
        timed_words = []
        if entry["reliable"]:
            token_times = _mapped_token_times(target, first, last, mapping, heard, start, end)
            target_index = first
            for display_word in display_words:
                token_count = max(1, len(WORD.findall(display_word)))
                final_target = min(last - 1, target_index + token_count - 1)
                if target_index >= last:
                    break
                word_start = token_times[target_index][0]
                word_end = token_times[final_target][1]
                timed_words.append({"text": display_word, "start": round(word_start, 4), "end": round(max(word_start + .01, word_end), 4)})
                target_index += token_count
        else:
            word_weights = [max(1, len(display_word)) for display_word in display_words]
            weight_sum = sum(word_weights)
            cursor = start
            for display_word, weight in zip(display_words, word_weights):
                span = (end - start) * weight / weight_sum
                timed_words.append({"text": display_word, "start": round(cursor, 4), "end": round(min(end, cursor + span), 4)})
                cursor += span
        word_cues.append({"start": round(start, 4), "end": round(end, 4), "text": line, "words": timed_words})
        previous_end = end + .01
    output_srt.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    output_srt.with_suffix(".words.json").write_text(json.dumps({"version": 2, "cues": word_cues}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_srt.with_suffix(".alignment.json").write_text(json.dumps({
        "version": 2,
        "language": language,
        "heard": [{"text": word.text, "start": word.start, "end": word.end} for word in heard],
        "lines": [{key: value for key, value in entry.items() if key in {"line", "first", "last", "reliable", "start", "end"}} for entry in entries],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_srt


def _mapped_token_times(
    target: list[str], first: int, last: int, mapping: list[int], heard: list[TimedWord], line_start: float, line_end: float,
) -> dict[int, tuple[float, float]]:
    """Split merged Whisper tokens and keep target word timing monotonic."""
    result: dict[int, tuple[float, float]] = {}
    index = first
    cursor = line_start
    while index < last:
        source_index = mapping[index]
        stop = index + 1
        while stop < last and mapping[stop] == source_index:
            stop += 1
        source_word = heard[source_index]
        group_start = max(cursor, line_start, min(line_end, source_word.start))
        group_end = min(line_end, max(group_start + .02 * (stop - index), source_word.end))
        weights = [max(1, len(target[position])) for position in range(index, stop)]
        total_weight = sum(weights)
        local_cursor = group_start
        for position, weight in zip(range(index, stop), weights):
            span = (group_end - group_start) * weight / total_weight
            token_end = min(line_end, max(local_cursor + .01, local_cursor + span))
            result[position] = (local_cursor, token_end)
            local_cursor = token_end
        cursor = max(cursor, group_end)
        index = stop
    return result


def _map_words(target: list[str], heard: list[TimedWord]) -> tuple[list[int], list[bool]]:
    """Anchor exact lyric runs first, then interpolate only inside unmatched gaps."""
    source = [word.text for word in heard]
    mapping: list[int | None] = [None] * len(target)
    matched = [False] * len(target)
    if not target:
        return [], []
    if not source:
        return [0] * len(target), matched
    for tag, i1, i2, j1, j2 in SequenceMatcher(a=target, b=source, autojunk=False).get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapping[i1 + offset] = j1 + offset
                matched[i1 + offset] = True
        elif tag == "replace":
            # Fuzzy matching is deliberately local: it may repair "fantasma" / "fantofmo"
            # but cannot drag a whole verse into an unrelated repeated chorus.
            available = set(range(j1, j2))
            for target_index in range(i1, i2):
                choices = [(SequenceMatcher(None, target[target_index], source[source_index]).ratio(), source_index) for source_index in available]
                if choices:
                    similarity, source_index = max(choices)
                    if similarity >= .68:
                        mapping[target_index] = source_index
                        matched[target_index] = True
                        available.remove(source_index)
    known = [(index, value) for index, value in enumerate(mapping) if value is not None]
    if not known:
        return [round(index * (len(heard) - 1) / max(1, len(target) - 1)) for index in range(len(target))], matched
    for index, value in enumerate(mapping):
        if value is not None:
            continue
        left = next(((i, v) for i, v in reversed(known) if i < index), None)
        right = next(((i, v) for i, v in known if i > index), None)
        if left and right:
            ratio = (index - left[0]) / (right[0] - left[0])
            mapping[index] = round(int(left[1]) + ratio * (int(right[1]) - int(left[1])))
        else:
            mapping[index] = int((left or right or (0, 0))[1])
    resolved = [min(len(heard) - 1, max(0, int(value or 0))) for value in mapping]
    return _monotonic_mapping(resolved), matched


def _map_lines(target: list[str], ranges: list[tuple[int, int]], heard: list[TimedWord]) -> tuple[list[int], list[bool]]:
    """Align each supplied line after the previous one so repeated choruses cannot swap."""
    source = [word.text for word in heard]
    mapping: list[int | None] = [None] * len(target)
    matched = [False] * len(target)
    cursor = 0
    for first, last in ranges:
        lyric = target[first:last]
        if not lyric or cursor >= len(source):
            continue
        best: tuple[float, float, int, int] | None = None
        minimum = max(1, len(lyric) - 2)
        maximum = len(lyric) + 3
        for source_start in range(cursor, len(source)):
            if heard[source_start].start - heard[cursor].start > 12.0:
                break
            strong_at_start: tuple[float, float, int, int] | None = None
            for length in range(minimum, maximum + 1):
                source_end = min(len(source), source_start + length)
                if source_end <= source_start:
                    continue
                if heard[source_end - 1].end - heard[source_start].start > max(3.2, len(lyric) * 1.1):
                    continue
                ratio = SequenceMatcher(None, lyric, source[source_start:source_end], autojunk=False).ratio()
                score = ratio - abs(length - len(lyric)) * .025 - min(.18, (source_start - cursor) * .002)
                candidate = (score, ratio, source_start, source_end)
                if best is None or score > best[0]:
                    best = candidate
                if strong_at_start is None or ratio > strong_at_start[1]:
                    strong_at_start = candidate
            # Prefer the first convincing occurrence over a marginally cleaner repeated chorus later.
            if strong_at_start is not None and strong_at_start[1] >= .78:
                best = strong_at_start
                break
        threshold = .72 if len(lyric) <= 2 else .48
        if best is None or best[0] < threshold:
            continue
        _, _, source_start, source_end = best
        local_source = source[source_start:source_end]
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, lyric, local_source, autojunk=False).get_opcodes():
            if tag == "equal":
                for offset in range(i2 - i1):
                    mapping[first + i1 + offset] = source_start + j1 + offset
                    matched[first + i1 + offset] = True
            elif tag == "replace":
                available = set(range(j1, j2))
                for local_target in range(i1, i2):
                    choices = [(SequenceMatcher(None, lyric[local_target], local_source[index]).ratio(), index) for index in available]
                    if choices:
                        similarity, local_index = max(choices)
                        if similarity >= .68:
                            mapping[first + local_target] = source_start + local_index
                            matched[first + local_target] = True
                            available.remove(local_index)
        line_matches = sum(1 for index in range(first, last) if matched[index])
        line_reliable = (line_matches >= 2 and line_matches / len(lyric) >= .4) or (len(lyric) <= 2 and line_matches == len(lyric))
        if line_reliable:
            mapped_line = [mapping[index] for index in range(first, last) if mapping[index] is not None]
            cursor = max(int(index) for index in mapped_line) + 1 if mapped_line else source_end
        else:
            for index in range(first, last):
                mapping[index] = None
                matched[index] = False
    known = [(index, value) for index, value in enumerate(mapping) if value is not None]
    if not known:
        return _map_words(target, heard)
    for index, value in enumerate(mapping):
        if value is not None:
            continue
        left = next(((i, v) for i, v in reversed(known) if i < index), None)
        right = next(((i, v) for i, v in known if i > index), None)
        if left and right:
            ratio = (index - left[0]) / (right[0] - left[0])
            mapping[index] = round(int(left[1]) + ratio * (int(right[1]) - int(left[1])))
        else:
            mapping[index] = int((left or right or (0, 0))[1])
    resolved = [min(len(heard) - 1, max(0, int(value or 0))) for value in mapping]
    return _monotonic_mapping(resolved), matched


def _monotonic_mapping(mapping: list[int]) -> list[int]:
    for index in range(1, len(mapping)):
        mapping[index] = max(mapping[index - 1], mapping[index])
    return mapping


def _is_section_label(line: str) -> bool:
    stripped = line.strip()
    if re.fullmatch(r"[\[(].{1,40}[\])]", stripped):
        return True
    normalized = _normalize(stripped.rstrip(":"))
    return bool(re.fullmatch(r"(?:intro|outro|verse|strofa|chorus|ritornello|bridge|ponte|prechorus|preritornello|hook|refrain|instrumental|interlude)\d*", normalized))


def _merge_elisions(words: list[TimedWord], language: str) -> list[TimedWord]:
    """Rejoin Whisper tokens such as Italian `l` + `ombra` to TXT `l'ombra`."""
    if language not in {"it", "fr", "auto"}:
        return words
    prefixes = {"l", "d", "all", "dall", "dell", "nell", "sull", "un", "quest", "c", "m", "t", "s", "j", "n", "qu"}
    merged: list[TimedWord] = []
    index = 0
    while index < len(words):
        current = words[index]
        if index + 1 < len(words) and current.text in prefixes and words[index + 1].start - current.end <= .09:
            following = words[index + 1]
            merged.append(TimedWord(current.text + following.text, current.start, following.end))
            index += 2
        else:
            merged.append(current)
            index += 1
    return merged


def _vocal_intervals(audio: Path) -> list[tuple[float, float]]:
    """Return active vocal regions used to recover words missed at line boundaries."""
    try:
        import librosa
        signal, sample_rate = librosa.load(str(audio), sr=16000, mono=True)
        raw = librosa.effects.split(signal, top_db=32, frame_length=1024, hop_length=256)
        intervals = [(float(start / sample_rate), float(end / sample_rate)) for start, end in raw]
        merged: list[tuple[float, float]] = []
        for start, end in intervals:
            if merged and start - merged[-1][1] < .16:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))
        return merged
    except Exception as exc:
        print(f"alignment: vocal activity detection failed ({exc})", flush=True)
        return []


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed.casefold() if char.isalnum() and not unicodedata.combining(char))


def _time(value: float) -> str:
    milliseconds = max(0, round(value * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"
