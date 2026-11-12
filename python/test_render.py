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

    # The fog types sit low: look level at them (the test camera is pitched 18 degrees up).
    FOG = ("Ground Fog", "Wispy Fog", "Torn Low Cloud")
    for tname in cloud_types.TYPES:
        cam["rotate"].setValue([2 if tname in FOG else 18, 0, 0])
        set_type("l1_", tname)
        render(tname.replace(" ", "_").lower())
    cam["rotate"].setValue([18, 0, 0])

    # The erosion stack on a hero cumulus. Grain is finer than a pixel at the type's 12 km (the
    # kernel fades detail out by footprint), so grain is checked on a close hero at 4 km.
    set_type("l1_", "Hero Cumulus")
    for knob, value in (("wisp_amount", 0.9), ("grain_amount", 0.8), ("swirl", 0.6), ("shear", 0.5),
                        ("shadow_depth", 1.0)):
        if knob == "grain_amount":
            g["l1_place_km"].setValue(4)
            g["l1_place"].execute()
            render("hero_cumulus_near")
            # The same with the fine edge steps off: grainier (the reference shows the difference).
            g["edge_steps"].setValue(1)
            render("hero_cumulus_near_edge_steps_off")
            g["edge_steps"].setValue(3)
        old = g["l1_" + knob].value()
        g["l1_" + knob].setValue(value)
        render("hero_cumulus_" + knob)
        g["l1_" + knob].setValue(old)
        if knob == "grain_amount":
            g["l1_place_km"].setValue(12)
            g["l1_place"].execute()

    # Torn edges: crumble and turbulence on the torn low cloud, and the ground fog's per-side
    # fades: with them off it fills more of its box.
    cam["rotate"].setValue([2, 0, 0])
    set_type("l1_", "Torn Low Cloud")
    for knob in ("crumble", "turbulence"):
        old = g["l1_" + knob].value()
        g["l1_" + knob].setValue(0)
        render("torn_low_cloud_no_" + knob)
        g["l1_" + knob].setValue(old)
    set_type("l1_", "Ground Fog")
    fades = ("fade_top", "fade_bottom", "fade_left", "fade_right", "fade_front", "fade_back")
    with_fades = mean_alpha()
    olds = [g["l1_" + k].value() for k in fades]
    for k in fades:
        g["l1_" + k].setValue(0)
    render("ground_fog_no_fades")
    no_fades = mean_alpha()
    for k, v in zip(fades, olds):
        g["l1_" + k].setValue(v)
    print("fades: ground fog alpha %.3f with, %.3f without" % (with_fades, no_fades))
    if not with_fades < no_fades - 0.005:
        raise RuntimeError("the per-side fades didn't thin the ground fog")
    cam["rotate"].setValue([18, 0, 0])

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
            if k[3:].startswith("box_"):
                continue  # read from the layer's own knobs and box input (box1, box2...)
            sa, sb = a.toScript(), b.toScript()
            a.fromScript(sb)
            b.fromScript(sa)
    g["knobChanged"].setValue(kc)
    render("layered_swapped")

    # Layers shadow each other: a cumulus deck under an altocumulus deck gets less direct sun
    # with 'layers shadow each other' on; the altocumulus on its own is untouched.
    g["l3_enable"].setValue(False)
    set_type("l1_", "Cumulus")
    set_type("l2_", "Altocumulus")
    g["l2_coverage"].setValue(0.75)

    def mean_sun():
        n, tot = 0, 0.0
        for y in range(H // 60, H, H // 30):
            for x in range(W // 96, W, W // 48):
                tot += g.sample("cloud_sun.green", x + 0.5, y + 0.5, frame=1001)
                n += 1
        return tot / n

    g["layer_shadows"].setValue(False)
    render("layer_shadows_off")
    sun_off = mean_sun()
    g["layer_shadows"].setValue(True)
    render("layer_shadows")
    sun_on = mean_sun()
    g["l1_enable"].setValue(False)
    top_on = mean_sun()
    g["layer_shadows"].setValue(False)
    top_off = mean_sun()
    g["layer_shadows"].setValue(True)
    g["l1_enable"].setValue(True)
    print("layer shadows: sun share %.4f -> %.4f, top layer alone %.4f -> %.4f"
          % (sun_off, sun_on, top_off, top_on))
    if not sun_on < sun_off * 0.98:
        raise RuntimeError("the upper layer cast no shadow on the lower one")
    if abs(top_on - top_off) > 1e-4:
        raise RuntimeError("layer shadows changed a layer with nothing above it")
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

    # The 3D box: a hero cumulus in a Cube plugged into box1, then the Cube moved, turned and scaled.
    g["l1_enable"].setValue(True)
    set_type("l1_", "Hero Cumulus")
    g["l1_vol_rotate"].setValue([0, 25, 0])
    render("box_before")
    g["l1_make_box"].execute()
    box = g.input(5)
    if box is None or box.Class() != "Cube":
        raise RuntimeError("make 3D box didn't plug a Cube into box1")

    def box_state():
        return ("found %d centre %s size %s axis_x %s" % (
            g["l1_box_found"].value(), ["%.1f" % v for v in g["l1_box_center"].value()],
            ["%.1f" % v for v in g["l1_box_size"].value()], ["%.4f" % v for v in g["l1_box_axis_x"].value()]))
    print("box: " + box_state())
    render("box_linked")  # must match box_before
    c0 = g["l1_box_center"].value()
    box["translate"].setValue([box["translate"].value(0) - 15000, box["translate"].value(1),
                               box["translate"].value(2) + 30000])
    box["rotate"].setValue([10, 60, 5])
    box["scaling"].setValue([box["scaling"].value(0) * 1.5, box["scaling"].value(1), box["scaling"].value(2)])
    c1 = g["l1_box_center"].value()
    print("box moved: " + box_state())
    if abs(c1[0] - c0[0] + 15000) > 1 or abs(c1[2] - c0[2] - 30000) > 1:
        raise RuntimeError("the volume doesn't follow the box")
    # The box's axes must be the kernel's rotation for the same angles (Y, then X, then Z).
    import math
    ax, ay, az = [math.radians(v) for v in (10, 60, 5)]
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    col0 = (cz * cy - sz * sx * sy, sz * cy + cz * sx * sy, -cx * sy)
    got = g["l1_box_axis_x"].value()
    print("rotation check: kernel %s box %s" % (["%.4f" % v for v in col0], ["%.4f" % v for v in got]))
    if max(abs(p - q) for p, q in zip(col0, got)) > 1e-3:
        raise RuntimeError("the box's axes don't match the kernel's rotation")
    # The same transform on an Axis3 (which has a world_matrix) must give the same box: checks the
    # Cube matrix code against Nuke's own.
    ax3 = nuke.nodes.Axis3() if hasattr(nuke.nodes, "Axis3") else nuke.nodes.Axis2()
    for kn in ("translate", "rotate", "scaling", "uniform_scale", "rot_order", "xform_order", "pivot"):
        ax3[kn].fromScript(box[kn].toScript())
    m = ax3["world_matrix"]
    sc = box["scaling"].value(0) * box["uniform_scale"].value()
    want_axis = (m.getValue(0) / sc, m.getValue(4) / sc, m.getValue(8) / sc)
    want_c = (m.getValue(3), m.getValue(7), m.getValue(11))
    print("Axis3 check: axis %s centre %s" % (["%.4f" % v for v in want_axis], ["%.1f" % v for v in want_c]))
    if max(abs(p - q) for p, q in zip(want_axis, got)) > 1e-3 or max(abs(p - q) for p, q in zip(want_c, c1)) > 1:
        raise RuntimeError("box matrix doesn't match Nuke's Axis3")
    render("box_moved")
    # Plugging the Axis3 in place of the Cube gives the same cloud (any 3D node works).
    g.setInput(5, ax3)
    print("Axis3 plugged: " + box_state())
    render("box_axis")  # must match box_moved
    g.setInput(5, box)
    nuke.delete(ax3)
    # The cloud must travel with the box: moved back by the same amount, it renders as before
    # the move (its noise lives in the box's frame).
    t = box["translate"].value()
    box["translate"].setValue([t[0] + 15000, t[1], t[2] - 30000])
    box["rotate"].setValue([0, 25, 0])
    box["scaling"].setValue([box["scaling"].value(0) / 1.5, box["scaling"].value(1), box["scaling"].value(2)])
    render("box_back")  # must match box_linked
    box["translate"].setValue([t[0], t[1], t[2]])
    box["rotate"].setValue([10, 60, 5])
    box["scaling"].setValue([box["scaling"].value(0) * 1.5, box["scaling"].value(1), box["scaling"].value(2)])
    # Renaming the Cube changes nothing (the old expression links broke on a rename).
    box.setName("RenamedBox")
    if g["l1_box_found"].value() < 0.5:
        raise RuntimeError("renaming the box lost it")
    # A parent Axis: Nuke 15's Cube has no axis input, so geometry is parented through a
    # TransformGeo (Cube -> TransformGeo, Axis in its axis input). Turned 90 degrees about Y and
    # moved 1000 in x, the centre (x, y, z) must go to (z + 1000, y, -x).
    parent_axis = nuke.nodes.Axis3() if hasattr(nuke.nodes, "Axis3") else nuke.nodes.Axis2()
    parent_axis["translate"].setValue([1000, 0, 0])
    parent_axis["rotate"].setValue([0, 90, 0])
    tgeo = nuke.nodes.TransformGeo()
    tgeo.setInput(0, box)
    tgeo.setInput(1, parent_axis)
    c_before = g["l1_box_center"].value()
    g.setInput(5, tgeo)
    c_after = g["l1_box_center"].value()
    want = [c_before[2] + 1000, c_before[1], -c_before[0]]
    print("parent axis (TransformGeo): centre %s -> %s, want %s" % (
        ["%.1f" % v for v in c_before], ["%.1f" % v for v in c_after], ["%.1f" % v for v in want]))
    if max(abs(a - b) for a, b in zip(c_after, want)) > 1:
        raise RuntimeError("a parent Axis through a TransformGeo is not followed")
    g.setInput(5, box)
    nuke.delete(tgeo)
    nuke.delete(parent_axis)
    t0 = box["translate"].value()
    g["l1_place"].execute()
    print("place moves the box: %s -> %s" % (t0, box["translate"].value()))
    if abs(box["translate"].value(0) - t0[0]) + abs(box["translate"].value(2) - t0[2]) < 1:
        raise RuntimeError("place in front of camera didn't move the box")
    # Picking a type with the box plugged in sizes the box.
    g["l1_type"].setValue("Storm Anvil")
    want = cloud_types.full("Storm Anvil")["vol_size"]
    if max(abs(p - q) for p, q in zip(g["l1_box_size"].value(), want)) > 1e-2 * max(want):
        # Terminal Nuke doesn't run knobChanged: run the node's script as the GUI would.
        saved = nuke.thisNode, nuke.thisKnob
        nuke.thisNode, nuke.thisKnob = (lambda: g), (lambda: g["l1_type"])
        try:
            exec(g["knobChanged"].value(), {"nuke": nuke})
        finally:
            nuke.thisNode, nuke.thisKnob = saved
        print("type change: knobChanged run by hand")
    got_size = g["l1_box_size"].value()
    print("type change: box size %s (type %s)" % (got_size, want))
    if max(abs(p - q) for p, q in zip(got_size, want)) > 1e-2 * max(want):
        raise RuntimeError("picking a type didn't size the box")
    render("box_placed")
    g["l1_release_box"].execute()
    if g.input(5) is not None or g["l1_box_found"].value() > 0.5:
        raise RuntimeError("release box left the box plugged in")
    print("released: position %s rotate %s size %s" % (g["l1_vol_position"].value(), g["l1_vol_rotate"].value(),
                                                      g["l1_vol_size"].value()))
    render("box_released")  # must match box_placed
    nuke.delete(box)

    # Occlusion and ground shadows: a ridge 8 km away (depth.Z, Planar Z in decimetres) across
    # the bottom of the frame, in front of a cumulus deck.
    g["l1_enable"].setValue(True)
    g["l2_enable"].setValue(False)
    g["l3_enable"].setValue(False)
    set_type("l1_", "Cumulus")
    ridge_line = "(y < %g * (0.3 + 0.05 * sin(x / %g)))" % (H, W / 14.0)
    ridge = nuke.nodes.Expression(name="TestRidge", channel0="rgb", expr0="%s ? 0.03 : r" % ridge_line,
                                  channel1="depth", expr1="%s ? 80000 : 0" % ridge_line,
                                  channel2="none", channel3="none")
    ridge.setInput(0, sky)
    g.setInput(0, ridge)

    def region_mean(channel, below):
        # Mean of a channel over the grid points below (or well above) the ridge.
        n, tot = 0, 0.0
        for y in range(H // 60, H, H // 30):
            for x in range(W // 96, W, W // 48):
                top = H * (0.3 + 0.05 * math.sin(x / (W / 14.0)))
                if (y < top - 2) if below else (y > top + H * 0.08):
                    tot += g.sample(channel, x + 0.5, y + 0.5, frame=1001)
                    n += 1
        return tot / max(n, 1)

    g["occlude"].setValue(False)
    render("occlude_off")
    off_below, off_above = region_mean("cloud.alpha", True), region_mean("cloud.alpha", False)
    g["occlude"].setValue(True)
    render("occlude")
    on_below, on_above = region_mean("cloud.alpha", True), region_mean("cloud.alpha", False)
    shade = region_mean("cloud_shadow.red", True)
    print("occlusion: alpha below the ridge %.3f -> %.3f, above %.3f -> %.3f, shadow on it %.3f"
          % (off_below, on_below, off_above, on_above, shade))
    if not on_below < 0.5 * off_below:
        raise RuntimeError("the ridge didn't hide the clouds behind it")
    if abs(on_above - off_above) > 0.01:
        raise RuntimeError("occlusion changed the sky above the ridge")
    if not 0.02 < shade < 0.98:
        raise RuntimeError("no believable cloud shadow on the ridge")
    if region_mean("cloud_shadow.red", False) > 1e-4:
        raise RuntimeError("cloud shadow on the sky")
    g["view"].setValue("Shadow")
    render("shadow_view")
    g["view"].setValue("Comp")
    # ScanlineRender's 1/Z, same ridge: must match.
    ridge["expr1"].setValue("%s ? 1.0 / 80000 : 0" % ridge_line)
    g["depth_mode"].setValue("1/Z (ScanlineRender)")
    render("occlude_inverse_z")
    inv_below = region_mean("cloud.alpha", True)
    print("1/Z: alpha below the ridge %.3f (Planar Z %.3f)" % (inv_below, on_below))
    if abs(inv_below - on_below) > 0.01:
        raise RuntimeError("1/Z depth doesn't match Planar Z")
    g["depth_mode"].setValue("Planar Z")
    # The depth channel knob reaches the DepthSource node inside (checked, not rendered).
    g["depth_channel"].setValue("rgba.alpha")
    saved = nuke.thisNode, nuke.thisKnob
    nuke.thisNode, nuke.thisKnob = (lambda: g), (lambda: g["depth_channel"])
    try:
        exec(g["knobChanged"].value(), {"nuke": nuke})
    finally:
        nuke.thisNode, nuke.thisKnob = saved
    # Nuke gives channels back by short name ('alpha' for rgba.alpha).
    if (g.node("DepthSource")["from0"].value() not in ("rgba.alpha", "alpha")
            or g.node("DepthEnsure")["channels"].value() not in ("rgba.alpha", "alpha")):
        raise RuntimeError("depth channel knob didn't reach DepthSource")
    # Back to depth.Z: the knob says 'depth', which a Copy would read as cutout.depth.
    g["depth_channel"].setValue("depth.Z")
    nuke.thisNode, nuke.thisKnob = (lambda: g), (lambda: g["depth_channel"])
    try:
        exec(g["knobChanged"].value(), {"nuke": nuke})
    finally:
        nuke.thisNode, nuke.thisKnob = saved
    if g.node("DepthSource")["from0"].value() != "depth.Z":
        raise RuntimeError("depth.Z on the knob gave DepthSource " + g.node("DepthSource")["from0"].value())
    g.setInput(0, sky)

    # Motion vectors: the camera pans 0.5 degrees left per frame (rotate.y), no wind. The clouds
    # move right by about W * (focal / haperture) * tan(0.5 deg) at the centre, and back again.
    set_type("l1_", "Cumulus")
    g["l1_wind_speed"].setValue(0)
    g["motion_vectors"].setValue(True)
    cam["rotate"].setAnimated(1)
    for f, yaw in ((1000, -0.5), (1001, 0.0), (1002, 0.5)):
        cam["rotate"].setValueAt(yaw, f, 1)
    render("motion_pan")
    # The camera's own aperture (Nuke's default is 24.576 mm, not 36), and its 18 degree tilt:
    # a pan about world Y turns a tilted camera about its own Y by only cos(tilt) of it.
    print("test camera: focal %g, haperture %g" % (cam["focal"].value(), cam["haperture"].value()))
    want = (W * cam["focal"].value() / cam["haperture"].value() * math.tan(math.radians(0.5))
            * math.cos(math.radians(18)))
    n, fu, fv, bu = 0, 0.0, 0.0, 0.0
    for y in range(H // 3, 2 * H // 3, H // 30):
        for x in range(W // 3, 2 * W // 3, W // 48):
            if g.sample("cloud.alpha", x + 0.5, y + 0.5, frame=1001) > 0.5:
                fu += g.sample("forward.u", x + 0.5, y + 0.5, frame=1001)
                fv += g.sample("forward.v", x + 0.5, y + 0.5, frame=1001)
                bu += g.sample("backward.u", x + 0.5, y + 0.5, frame=1001)
                n += 1
    n = max(n, 1)
    fu, fv, bu = fu / n, fv / n, bu / n
    print("motion: forward.u %.2f (about %.2f), forward.v %.2f, backward.u %.2f, %d samples"
          % (fu, want, fv, bu, n))
    if not 0.8 * want < fu < 1.4 * want:
        raise RuntimeError("forward vectors don't follow the camera pan")
    if abs(bu + fu) > 0.1 * abs(fu):
        raise RuntimeError("backward vectors aren't the reverse of forward ones")
    # Wind alone (static camera): the deck drifts, so the vectors aren't zero, and are zero without it.
    cam["rotate"].clearAnimated()
    cam["rotate"].setValue([18, 0, 0])
    g["l1_wind_speed"].setValue(30)
    render("motion_wind")
    wu = g.sample("forward.u", W / 2 + 0.5, H / 2 + 0.5, frame=1001)
    wv = g.sample("forward.v", W / 2 + 0.5, H / 2 + 0.5, frame=1001)
    print("motion: wind 30 m/s, centre vector (%.3f, %.3f)" % (wu, wv))
    g["l1_wind_speed"].setValue(5.0)
    g["motion_vectors"].setValue(False)
    if "forward" in set(c.split(".")[0] for c in g.channels()):
        raise RuntimeError("motion vectors off still outputs forward")

    # Preview: faster, and close to the full render.
    g["l1_enable"].setValue(True)
    g["l2_enable"].setValue(True)
    g["l3_enable"].setValue(True)
    set_type("l1_", "Cumulus")
    set_type("l2_", "Hero Cumulus")
    g["l2_place_km"].setValue(5)
    g["l2_place"].execute()
    times = {}
    for preview in (False, True):
        g["preview"].setValue(preview)
        g["seed"].setValue(g["seed"].value() + 1)  # fresh frames, not Nuke's cache
        render("preview_on" if preview else "preview_off")
        t = time.time()
        for f in range(3):
            g["seed"].setValue(g["seed"].value() + 1)
            nuke.execute(w, 1001, 1001)
        times[preview] = (time.time() - t) / 3
    print("preview: %.3f s/frame off, %.3f s/frame on (%.1fx faster), label '%s'"
          % (times[False], times[True], times[False] / max(times[True], 1e-6), g["label"].evaluate()))
    if not times[True] < times[False]:
        raise RuntimeError("preview isn't faster")
    g["preview"].setValue(False)

    # Bake: three frames to tests/out/bake, played back from disk, and out of date after a change.
    g["bake_folder"].setValue(OUT + "/bake")
    g["bake_first"].setValue(1001)
    g["bake_last"].setValue(1003)
    print("bake status before: " + g["bake_status"].evaluate())
    render("bake_live")
    live = [g.sample(c, W / 2 + 0.5, H / 2 + 0.5, frame=1001) for c in ("rgba.red", "cloud.alpha", "depth.Z")]
    t = time.time()
    g["bake_now"].execute()
    print("bake: 3 frames in %.2fs to %s" % (time.time() - t, g.node("BakeWrite")["file"].evaluate()))
    if not g["use_bake"].value():
        raise RuntimeError("bake now didn't switch to the bake")
    print("bake status after: " + g["bake_status"].evaluate())
    if g["bake_status"].evaluate() != "up to date":
        raise RuntimeError("fresh bake isn't up to date")
    render("bake_played")  # must match bake_live
    baked = [g.sample(c, W / 2 + 0.5, H / 2 + 0.5, frame=1001) for c in ("rgba.red", "cloud.alpha", "depth.Z")]
    print("bake: live %s, baked %s, label '%s'" % (live, baked, g["label"].evaluate()))
    if max(abs(a - b) / max(abs(a), 1e-3) for a, b in zip(live, baked)) > 1e-3:
        raise RuntimeError("baked frames don't match the live render")
    g["l1_coverage"].setValue(g["l1_coverage"].value() + 0.05)
    print("bake status after a change: " + g["bake_status"].evaluate())
    if not g["bake_status"].evaluate().startswith("OUT OF DATE"):
        raise RuntimeError("bake isn't flagged out of date after a change")
    g["l1_coverage"].setValue(g["l1_coverage"].value() - 0.05)
    g["use_bake"].setValue(False)
    g["l2_enable"].setValue(False)
    g["l3_enable"].setValue(False)

    # The layers the node adds.
    print("channels: " + " ".join(sorted(set(c.split(".")[0] for c in g.channels()))))


if __name__ == "__main__":
    main()
