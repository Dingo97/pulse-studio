"""Generate a contact sheet for manual overlay quality review.

Run inside the backend container. The output is intentionally ignored by git.
"""
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from app.renderer import PulseRenderer


root = Path("/app/data/projects")
cover_path = next(root.glob("*/input/cover.png"))
source = cv2.cvtColor(cv2.imread(str(cover_path)), cv2.COLOR_BGR2RGB)
height, width = 360, 640
source = PulseRenderer._crop_fill(source, width, height, False)
renderer = PulseRenderer.__new__(PulseRenderer)
renderer.profile = SimpleNamespace(beats=np.arange(0, 300, .5))

effects = ["grain", "dust", "scratches", "light_leaks", "film_burn", "rain", "scanlines", "vhs", "bokeh", "prism", "vignette"]
tiles = []
for effect in effects:
    renderer.settings = SimpleNamespace(overlay=effect, overlay_intensity=55)
    sample_time = 0.0 if effect in {"film_burn", "scratches"} else 4.25
    frame = renderer._finish(source.copy(), sample_time)
    cv2.rectangle(frame, (0, 0), (width, 35), (8, 8, 10), -1)
    cv2.putText(frame, effect.replace("_", " ").upper(), (14, 24), cv2.FONT_HERSHEY_SIMPLEX, .55, (245, 245, 245), 1, cv2.LINE_AA)
    tiles.append(frame)

if len(tiles) % 2:
    tiles.append(np.zeros_like(tiles[0]))
sheet = np.vstack([np.hstack(tiles[index:index + 2]) for index in range(0, len(tiles), 2)])
output = Path("/app/data/overlay-contact-sheet.jpg")
cv2.imwrite(str(output), cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 93])
print(output)
