"""Render test frames from groups/EzCloudGen_group.nk in NukeX (synthetic, no plates):

    set EZCLOUDGEN_TEST_WIDTH=960
    Nuke15.1.exe --nukex -i --gpu -t python/test_render.py

(A trailing number on the Nuke command line is read as a frame range, so the width is an
environment variable.)

Writes tests/out/<type>.png (each type on layer 1, comp view, tone mapped by a simple grade)
and tests/out/views_*.png for the views of the default setup, and prints the time per frame
and each render's mean alpha. A render that fails or is cancelled raises, so a bad kernel
shows here.
"""

import math
import os
import sys
import time

import nuke

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))
import cloud_types  # noqa: E402

OUT = os.path.join(ROOT, "tests", "out").replace("\\", "/")
W = int(os.environ.get("EZCLOUDGEN_TEST_WIDTH", "960"))
H = int(W * 9 / 16)


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    nuke.root()["format"].setValue(nuke.addFormat("%d %d 1 EzCloudGenTest" % (W, H)))
    nuke.root()["first_frame"].setValue(1001)
    nuke.root()["last_frame"].setValue(1001)
    nuke.nodePaste(os.path.join(ROOT, "groups", "EzCloudGen_group.nk").replace("\\", "/"))
    g = nuke.selectedNode()
    cam = nuke.nodes.Camera3(name="TestCam") if hasattr(nuke.nodes, "Camera3") else nuke.nodes.Camera2(name="TestCam")
    cam["translate"].setValue([0, 3000, 0])     # 300 m up, decimetres
    cam["rotate"].setValue([18, 0, 0])
    cam["focal"].setValue(24)
    sky = nuke.nodes.Constant(name="TestSky", color=[0.12, 0.22, 0.5, 1])
    g.setInput(0, sky)
    g.setInput(1, cam)
    g["sun_direction"].setValue([0.627, 0.574, -0.527])
    g["resolution"].setValue("Full")
    g["samples"].setValue(2)

    grade = nuke.nodes.Grade(name="TestTone", white=0.8)
    grade.setInput(0, g)
    srgb = nuke.nodes.Colorspace(name="TestSRGB", colorspace_out="sRGB")
    srgb.setInput(0, grade)
    clamp = nuke.nodes.Clamp(name="TestClamp")
    clamp.setInput(0, srgb)
    w = nuke.nodes.Write(name="TestWrite", file_type="png", channels="rgb")
    w.setInput(0, clamp)
    stats = nuke.nodes.CurveTool(name="TestStats", operation="Avg Intensities")
    stats.setInput(0, g)

    def render(name):
        w["file"].setValue("%s/%s.png" % (OUT, name))
        t = time.time()
        nuke.execute(w, 1001, 1001)
        secs = time.time() - t
        nuke.execute(stats, 1001, 1001)
        a = stats["intensitydata"].valueAt(1001, 3)
        print("%-24s %6.2fs  mean alpha %.3f" % (name, secs, a))
        if not os.path.exists("%s/%s.png" % (OUT, name)):
            raise RuntimeError("no output for " + name)

    for view in ("Comp", "Clouds", "Sun share", "Depth"):
        g["view"].setValue(view)
        if view == "Depth":
            grade["white"].setValue(1.0 / 50000.0)
        render("views_" + view.replace(" ", "_").lower())
        grade["white"].setValue(0.8)
    g["view"].setValue("Comp")

    for tname in cloud_types.TYPES:
        g["l1_type"].setValue(tname)
        # The type menu fills the knobs from knobChanged, which a terminal session doesn't run.
        for k, v in cloud_types.full(tname).items():
            if g.knob("l1_" + k) is not None:
                g["l1_" + k].setValue(v)
        render(tname.replace(" ", "_").lower())

    # Layer check: all three on.
    g["l1_type"].setValue("Cumulus")
    for k, v in cloud_types.full("Cumulus").items():
        if g.knob("l1_" + k) is not None:
            g["l1_" + k].setValue(v)
    g["l2_enable"].setValue(True)
    g["l3_enable"].setValue(True)
    render("layered")
    # The layers the node adds.
    print("channels: " + " ".join(sorted(set(c.split(".")[0] for c in g.channels()))))


if __name__ == "__main__":
    main()
