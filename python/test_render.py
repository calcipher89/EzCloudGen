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
    sky = nuke.nodes.Constant(name="TestSky", channels="rgba")
    # A list can't be passed as a knob argument to nuke.nodes (it is read as TCL).
    sky["color"].setValue([0.12, 0.22, 0.5, 1])
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

    def mean_alpha():
        # The clouds' own alpha (the cloud layer), not the comp's, on a coarse grid. A CurveTool
        # keeps its first result when executed again in a terminal session.
        n, tot = 0, 0.0
        for y in range(H // 60, H, H // 30):
            for x in range(W // 96, W, W // 48):
                tot += g.sample("cloud.alpha", x + 0.5, y + 0.5, frame=1001)
                n += 1
        return tot / n

    def render(name):
        w["file"].setValue("%s/%s.png" % (OUT, name))
        t = time.time()
        nuke.execute(w, 1001, 1001)
        secs = time.time() - t
        a = mean_alpha()
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

    def set_type(p, tname):
        g[p + "type"].setValue(tname)
        # The type menu fills the knobs from knobChanged; set them here too so the test does not lean on it.
        for k, v in cloud_types.full(tname).items():
            if g.knob(p + k) is not None:
                g[p + k].setValue(list(v) if isinstance(v, tuple) else v)
        if g[p + "volume"].value() > 0.5:
            g[p + "place"].execute()

    for tname in cloud_types.TYPES:
        set_type("l1_", tname)
        render(tname.replace(" ", "_").lower())

    # The erosion stack on a hero cumulus. Grain is finer than a pixel at the type's 12 km (the
    # kernel fades detail out by footprint), so grain is checked on a close hero at 4 km.
    set_type("l1_", "Hero Cumulus")
    for knob, value in (("wisp_amount", 0.9), ("grain_amount", 0.8), ("swirl", 0.6), ("shear", 0.5)):
        if knob == "grain_amount":
            g["l1_place_km"].setValue(4)
            g["l1_place"].execute()
            render("hero_cumulus_near")
        old = g["l1_" + knob].value()
        g["l1_" + knob].setValue(value)
        render("hero_cumulus_" + knob)
        g["l1_" + knob].setValue(old)
        if knob == "grain_amount":
            g["l1_place_km"].setValue(12)
            g["l1_place"].execute()

    # Layer check: a deck, a hero volume in front of it, and cirrus, sorted by depth.
    set_type("l1_", "Cumulus")
    g["l2_enable"].setValue(True)
    set_type("l2_", "Hero Cumulus")
    g["l2_place_km"].setValue(5)
    g["l2_place"].execute()
    g["l3_enable"].setValue(True)
    render("layered")
    # The same with layers 1 and 2 swapped (every knob, seed included): must look the same.
    # knobChanged is off meanwhile, or the type knobs would reset their layer.
    kc = g["knobChanged"].value()
    g["knobChanged"].setValue("")
    for k in g.knobs():
        if k.startswith("l1_") and g.knob("l2_" + k[3:]) is not None:
            a, b = g[k], g["l2_" + k[3:]]
            if isinstance(a, (nuke.PyScript_Knob, nuke.Text_Knob, nuke.Tab_Knob)):
                continue
            sa, sb = a.toScript(), b.toScript()
            a.fromScript(sb)
            b.fromScript(sa)
    g["knobChanged"].setValue(kc)
    render("layered_swapped")
    # The variations sheet of layer 1 (a cumulus deck).
    g["l2_enable"].setValue(False)
    g["l3_enable"].setValue(False)
    set_type("l1_", "Cumulus")
    g["variations_of"].setValue("Layer 1")
    g["show_variations"].execute()
    render("variations")
    g["variation_pick"].setValue(5)
    seed = g["l1_seed"].value()
    g["use_variation"].execute()
    if g["l1_seed"].value() != seed + 4 or g["view"].value() != "Comp":
        raise RuntimeError("use it: seed %g view %s" % (g["l1_seed"].value(), g["view"].value()))
    g["l1_seed"].setValue(seed)

    # The coverage map: a soft white disc on the left, a grey band on the right, black elsewhere.
    black = nuke.nodes.Constant(name="TestMapBlack", channels="rgba")
    black["color"].setValue([0, 0, 0, 0])
    disc = nuke.nodes.Radial(name="TestMapDisc", softness=0.6)
    disc["area"].setValue([W * 0.05, H * 0.3, W * 0.45, H * 0.85])
    disc.setInput(0, black)
    band = nuke.nodes.Rectangle(name="TestMapBand", softness=H * 0.06)
    band["area"].setValue([W * 0.55, H * 0.45, W * 0.98, H * 0.6])
    band["color"].setValue(0.5)
    band.setInput(0, disc)
    blur = nuke.nodes.Blur(name="TestMapBlur", size=W / 40.0)
    blur.setInput(0, band)
    g.setInput(4, blur)
    g["map_frame"].setValue(1001)
    render("map")
    g["l1_map_amount"].setValue(0)
    render("map_off")
    g["l1_map_amount"].setValue(1)
    g.setInput(4, None)

    # The 3D box: a hero cumulus linked to a Cube, then the Cube moved, turned and scaled.
    g["l1_enable"].setValue(True)
    set_type("l1_", "Hero Cumulus")
    g["l1_vol_rotate"].setValue([0, 25, 0])
    render("box_before")
    g["l1_make_box"].execute()
    box = nuke.toNode(g["l1_box"].value())
    if box is None:
        raise RuntimeError("make 3D box made no Cube")
    render("box_linked")  # must match box_before
    pos0 = g["l1_vol_position"].value()
    box["translate"].setValue([box["translate"].value(0) - 15000, box["translate"].value(1),
                               box["translate"].value(2) + 30000])
    box["rotate"].setValue([10, 60, 5])
    box["scaling"].setValue([box["scaling"].value(0) * 1.5, box["scaling"].value(1), box["scaling"].value(2)])
    pos1 = g["l1_vol_position"].value()
    print("box: position %s -> %s, rotate %s, size %s" % (pos0, pos1, g["l1_vol_rotate"].value(),
                                                         g["l1_vol_size"].value()))
    if abs(pos1[0] - pos0[0] + 15000) > 1 or abs(pos1[2] - pos0[2] - 30000) > 1:
        raise RuntimeError("the volume doesn't follow the box")
    render("box_moved")
    # The Cube's rotation must be the kernel's (Y, then X, then Z): compare its matrix.
    import math
    ax, ay, az = [math.radians(v) for v in (10, 60, 5)]
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    col0 = (cz * cy - sz * sx * sy, sz * cy + cz * sx * sy, -cx * sy)
    # A Cube has no world_matrix knob; an Axis with the same transform knobs gives its matrix.
    ax3 = nuke.nodes.Axis3() if hasattr(nuke.nodes, "Axis3") else nuke.nodes.Axis2()
    for kn in ("translate", "rotate", "scaling", "uniform_scale", "rot_order", "xform_order"):
        ax3[kn].fromScript(box[kn].toScript())
    m = ax3["world_matrix"]
    sc = box["scaling"].value(0) * box["uniform_scale"].value()
    got = (m.getValue(0) / sc, m.getValue(4) / sc, m.getValue(8) / sc)
    print("rotation check: kernel %s cube %s" % (["%.4f" % v for v in col0], ["%.4f" % v for v in got]))
    if max(abs(a - b) for a, b in zip(col0, got)) > 1e-3:
        raise RuntimeError("Cube rot_order doesn't match the kernel")
    nuke.delete(ax3)
    t0 = box["translate"].value()
    g["l1_place"].execute()
    print("place moves the box: %s -> %s" % (t0, box["translate"].value()))
    if abs(box["translate"].value(0) - t0[0]) + abs(box["translate"].value(2) - t0[2]) < 1:
        raise RuntimeError("place in front of camera didn't move the box")
    # Picking a type with the box linked sizes the box and keeps the links.
    g["l1_type"].setValue("Storm Anvil")
    want = cloud_types.full("Storm Anvil")["vol_size"]
    if max(abs(a - b) for a, b in zip(g["l1_vol_size"].value(), want)) > 1e-2 * max(want):
        # Terminal Nuke doesn't run knobChanged: run the node's script as the GUI would.
        saved = nuke.thisNode, nuke.thisKnob
        nuke.thisNode, nuke.thisKnob = (lambda: g), (lambda: g["l1_type"])
        try:
            exec(g["knobChanged"].value(), {"nuke": nuke})
        finally:
            nuke.thisNode, nuke.thisKnob = saved
        print("type change: knobChanged run by hand")
    got_size = g["l1_vol_size"].value()
    print("type change: size %s (type %s), linked %s" % (got_size, want, g["l1_vol_size"].isAnimated()))
    if not (g["l1_vol_size"].hasExpression() and g["l1_vol_position"].hasExpression()
            and g["l1_vol_rotate"].hasExpression()):
        raise RuntimeError("picking a type broke the box links")
    if max(abs(a - b) for a, b in zip(got_size, want)) > 1e-2 * max(want):
        raise RuntimeError("picking a type didn't size the box")
    g["l1_release_box"].execute()
    if g["l1_vol_position"].isAnimated() or g["l1_box"].value():
        raise RuntimeError("release box left a link")
    render("box_released")  # must match the last placed state
    nuke.delete(box)

    # The layers the node adds.
    print("channels: " + " ".join(sorted(set(c.split(".")[0] for c in g.channels()))))


if __name__ == "__main__":
    main()
