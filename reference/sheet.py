"""Render a contact sheet of the cloud types.

    python sheet.py out.jpg [width] [quality] [samples] [lighting] [types...]
"""

import math
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

import clouds as C
from presets import TYPES

LIGHTS = {
    # sun elevation, azimuth (deg from camera forward), sun intensity
    "day": (35.0, 50.0, 14.0),
    "golden": (6.0, 15.0, 14.0),
    "back": (14.0, 5.0, 14.0),
}


def sky_colours(sun_elev, sun_int):
    tr = np.array(C.atmos_trans(math.sin(math.radians(sun_elev)), 0.0))
    day = min(max(sun_elev / 30.0, 0.0), 1.0)
    sky = np.array([0.16, 0.32, 0.75]) * (0.35 + 0.65 * day) * sun_int * 0.055
    sky = sky * (0.6 + 0.4 * tr / max(tr.max(), 1e-6))
    haze = np.array([0.85, 0.8, 0.8]) * tr * sun_int * 0.05 + sky * 0.35
    gnd = np.array([0.12, 0.11, 0.09]) * tr * sun_int * 0.06 * max(math.sin(math.radians(sun_elev)), 0.1)
    return sky, haze, gnd


def tonemap(x):
    # ACES fit (Narkowicz) then sRGB.
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    y = np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0, 1)
    return np.where(y <= 0.0031308, 12.92 * y, 1.055 * np.power(y, 1 / 2.4) - 0.055)


COMBOS = {
    "Layered: Cumulus + Altocumulus + Cirrus": ["Cumulus", "Altocumulus", "Cirrus"],
    "Layered: Stratocumulus + Cirrus": ["Stratocumulus", "Cirrus"],
}


def render_type(name, w, h, quality, samples, light, extra=None, pitch=18.0, cam_y=300.0):
    names = COMBOS.get(name, [name])
    # Lowest layer first, so the march meets the near layers first.
    L = np.stack([TYPES[n] for n in sorted(names, key=lambda n: TYPES[n][0])])
    se, sa, si = LIGHTS[light]
    sky, haze, gnd = sky_colours(se, si)
    focal, hap = 24.0, 36.0
    t = time.time()
    img = C.render(L, len(L), w, h, cam_y, pitch, 0.0, focal, hap, se, sa, si, sky, gnd,
                   1.0 / 60000.0, haze, 80000.0, quality, samples, 0.0)
    bg = C.background(w, h, pitch, focal, hap, se, sa, si, sky, haze, gnd)
    comp = img[..., :3] + bg * (1.0 - img[..., 3:4])
    return comp, img, time.time() - t


def main():
    out = sys.argv[1]
    w = int(sys.argv[2]) if len(sys.argv) > 2 else 480
    q = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    s = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    light = sys.argv[5] if len(sys.argv) > 5 else "day"
    names = sys.argv[6:] or list(TYPES)
    h = int(w * 9 / 16)
    tiles = []
    for n in names:
        comp, img, secs = render_type(n, w, h, q, s, light)
        print("%-18s %.1fs  alpha mean %.2f" % (n, secs, img[..., 3].mean()), flush=True)
        tile = Image.fromarray((tonemap(comp * 0.9) * 255).astype(np.uint8))
        ImageDraw.Draw(tile).text((8, 6), n, fill=(255, 255, 255))
        tiles.append(tile)
    cols = 2 if len(tiles) > 1 else 1
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h))
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % cols) * w, (k // cols) * h))
    sheet.save(out, quality=92)


if __name__ == "__main__":
    main()
