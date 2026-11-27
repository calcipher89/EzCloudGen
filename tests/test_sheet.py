"""The cirrus sheet kernel (blink/EzCirrusSheet.blink) on the CPU, without Nuke (needs g++).

    python3 tests/test_sheet.py

Pass:
- cover follows the knob looking straight up (cover 0.25 / 0.5 / 0.75 read about a quarter, a half
  and three quarters of the sky, within 0.12);
- the far sheet keeps its gaps: looking out at the horizon, cover 0.5 is not a full veil (a pixel
  far off keeps the share of sheet it covers rather than the texture's mean);
- cover 0 draws nothing, nor does a camera above the sheet;
- the bg in front of the sheet hides it (depth holdout), and depth beyond it does not;
- the sun share (output 1) is part of the colour, and looking towards a low sun is brighter than
  away from it (forward scatter).
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "reference", "blink_check"))
import run_sheet  # noqa: E402

UP = {"cam_row1": "0,0,-1", "cam_row2": "0,1,0", "haperture": "24.576", "focal": "20"}
OUT = {"cam_row1": "0,0.984808,-0.173648", "cam_row2": "0,0.173648,0.984808", "haperture": "24.576"}
LIGHT = {"sun_color": "8,6,4", "sky_color": "0.12,0.18,0.35"}


def main():
    exe = run_sheet.build()
    ok = True

    def check(what, good, info):
        print("%-58s %s  %s" % (what, info, "ok" if good else "FAIL"))
        return good

    # Cover, straight up over many small patches (patch size 1 km, no fibres, opaque).
    covers = []
    for c in (0.25, 0.5, 0.75):
        a = run_sheet.render(240, 135, dict(UP, scale_km=1, fibres=0, opacity=2, cover=c), exe)[..., 3]
        covers.append((a > 0.5 * a.max()).mean())
    ok &= check("cover 0.25 / 0.5 / 0.75 straight up", all(abs(v - c) < 0.12 for v, c in zip(covers, (0.25, 0.5, 0.75))),
                " ".join("%.2f" % v for v in covers))

    # Out towards the horizon: gaps stay (the far texture is not its mean everywhere).
    img = run_sheet.render(240, 135, dict(OUT, cover=0.5, fibres=0, opacity=2), exe)
    a = img[..., 3]
    sky = a[:100]  # rows above the horizon
    share = (sky > 0.5 * sky.max()).mean()
    ok &= check("looking out, cover 0.5 keeps gaps", 0.25 < share < 0.85, "%.2f covered" % share)

    a0 = run_sheet.render(120, 68, dict(OUT, cover=0), exe)[..., 3].max()
    ok &= check("cover 0 draws nothing", a0 == 0.0, "max alpha %.3f" % a0)
    a1 = run_sheet.render(120, 68, dict(OUT, cam_position="0,120000,0"), exe)[..., 3].max()
    ok &= check("a camera above the sheet sees none", a1 == 0.0, "max alpha %.3f" % a1)

    # Depth holdout: a near wall (100 m) over the left half hides it; a far one (500 km) does not.
    base = run_sheet.render(120, 68, dict(UP, cover=1), exe)[..., 3]
    for dist, hidden in ((1000.0, True), (5e6, False)):
        z = np.zeros((68, 120), np.float32)
        z[:, :60] = dist  # scene units (decimetres)
        path = os.path.join(run_sheet.BUILD, "test_depth.npy")
        np.save(path, z)
        a = run_sheet.render(120, 68, dict(UP, cover=1, depth=path, sky_depth=1e8), exe)[..., 3]
        left = a[:, :60].max()
        good = (left == 0.0) if hidden else abs(left - base[:, :60].max()) < 1e-6
        ok &= check("bg at %g dm %s the sheet" % (dist, "hides" if hidden else "leaves"), good, "left alpha %.3f" % left)

    # The sun share and forward scatter.
    to = dict(OUT, **LIGHT, sun_direction="0.3,0.12,-0.95")
    away = dict(OUT, **LIGHT, sun_direction="0.3,0.12,0.95")
    c_to = run_sheet.render(120, 68, to, exe)
    s_to = run_sheet.render(120, 68, dict(to, output=1), exe)
    c_aw = run_sheet.render(120, 68, away, exe)
    part = np.all(s_to[..., :3] <= c_to[..., :3] + 1e-5)
    ok &= check("sun share within the colour", part, "")
    lt, la = c_to[..., :3].sum() / max(c_to[..., 3].sum(), 1e-6), c_aw[..., :3].sum() / max(c_aw[..., 3].sum(), 1e-6)
    ok &= check("towards a low sun brighter than away", lt > 1.2 * la, "%.2f vs %.2f" % (lt, la))

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
