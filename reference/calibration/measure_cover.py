"""Visible cover of each deck type against the kernel's 'coverage', on the CPU (no Nuke).

    python3 reference/calibration/measure_cover.py [--res 192] [--seeds 3]

Renders the kernel's sun map pass (output 5) with the sun straight overhead: each texel is the
optical depth straight up through the layer over that ground point. Visible cover is the share
of the central ground tile (about 20 x 20 km) whose optical depth is over TAU_VIS, i.e. that hides
more than half of the sky behind it. Averaged over a few layer offsets (different clouds).
Writes reference/calibration/cover_tables.json: {type: [[coverage, cover], ...]}.
"""
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "python"))
sys.path.insert(0, os.path.join(ROOT, "reference", "blink_check"))
import cloud_types  # noqa: E402
import run_kernel  # noqa: E402

TAU_VIS = 0.7          # exp(-0.7) ~ 0.5: hides half the sky behind it
# ... but a thin type (cirrus, mist) never gets there: count what reaches
# own full column (sigma x thickness): a tenth of it, as visible.
# Below 0 too: kernel coverage 0 still leaves a few wisps, so visible cover 0 sits a little under it.
COVERAGES = [round(-0.3 + 0.1 * i, 2) for i in range(14)]


def args_for(name):
    out = []
    for k, v in cloud_types.full(name).items():
        if k == "place_km":
            continue           # a build-side knob, not a kernel param
        if k == "detail_model":
            v = 1 if v == "soft billows" else 0
        if isinstance(v, (tuple, list)):
            v = ",".join(str(x) for x in v)
        out += [k, str(v)]
    return out


def tau_vis(full):
    return min(TAU_VIS, 0.1 * full["sigma"] * full["thickness"])


def cover(exe, base_args, cov, res, seeds, tv):
    vals = []
    for s in range(seeds):
        a = [exe, str(res), str(res)] + base_args + [
            "coverage", str(cov), "output", "5", "only_layer", "0", "sun_direction", "0,1,0",
            "frame_size", "%d,%d" % (res, res), "offset", "%d,%d" % (37000 * s, 23000 * s)]
        raw = subprocess.check_output(a)
        tau = np.frombuffer(raw, np.float32).reshape(res, res, 4)[..., 0]
        q = res // 4
        vals.append(float((tau[q:res - q, q:res - q] > tv).mean()))
    return sum(vals) / len(vals)


def main(argv):
    # The texel must be as fine as Nuke's own sun map (1536 over the same tile): at a coarse
    # footprint the kernel fades the erosion detail out and the clouds come out fuller.
    res = int(argv[argv.index("--res") + 1]) if "--res" in argv else 1024
    seeds = int(argv[argv.index("--seeds") + 1]) if "--seeds" in argv else 4
    exe = run_kernel.build()
    tables = {}
    for name in cloud_types.TYPES:
        full = cloud_types.full(name)
        if full.get("volume"):
            continue
        base = args_for(name)
        tv = tau_vis(full)
        rows = [[c, round(cover(exe, base, c, res, seeds, tv), 3)] for c in COVERAGES]
        # Kernel coverage at cover 0, .25, .5, .75, 1 (the curve inverted, kept monotone).
        cs = [r[0] for r in rows]
        vs = list(np.maximum.accumulate([r[1] for r in rows]))
        five = []
        # Cover 0: the highest coverage that still leaves (almost) nothing.
        empty = [c for c, v in zip(cs, vs) if v <= 0.005]
        # ... less a margin: under the visibility threshold a few faint wisps are left, which a
        # normal view still shows.
        five.append(round(max(cs[0], (max(empty) if empty else cs[0]) - 0.15), 3))
        for target in (0.25, 0.5, 0.75, 1.0):
            if target <= vs[0]:
                five.append(cs[0])
            elif target >= vs[-1]:
                five.append(cs[-1])
            else:
                five.append(round(float(np.interp(target, vs, cs)), 3))
        tables[name] = {"curve": rows, "table": five, "tau_vis": round(tv, 3)}
        print("%-18s tau %.2f | table %s | max cover %.2f" % (name, tv, five, vs[-1]), flush=True)
    with open(os.path.join(HERE, "cover_tables.json"), "w") as f:
        json.dump(tables, f, indent=1)


if __name__ == "__main__":
    main(sys.argv)
