"""Build groups/EzCloudGen_group.nk and gizmos/EzCloudGen.gizmo, in NukeX:

    Nuke15.1.exe --nukex -t python/build_group.py

It runs inside Nuke so Nuke compiles the kernel itself and writes its own kernel hash (a
hand-written hash makes a BlinkScript load fine but silently cancel every render).

The node is self-contained: the kernel source, the type presets and every expression live on
the node, so it needs no init.py, menu.py or Python module.

Inputs: 0 bg (the plate or sky to comp over; it also sets the format, optional), 1 camera,
2 atmos (an EzAtmosScatter, optional: sun direction, sun and sky colour), 3 sun (an Axis,
optional: overrides the sun direction), 4 map (optional: a coverage map painted over the shot;
see 'coverage map').

Up to three layers (sky decks or placed volumes), each its own BlinkScript (one per output: colour, sun share, depth).
Layers are put over each other nearest first, per pixel (blink/EzCloudGenStack.blink).
"""

import os
import sys

import nuke

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))
import cloud_types  # noqa: E402
import node_layout  # noqa: E402

VERSION = "0.3.0"
KERNEL = "EzCloudGen"
KERNEL_FILE = os.path.join(ROOT, "blink", KERNEL + ".blink")
STACK_KERNEL = "EzCloudGenStack"
GROUP_PATH = os.path.join(ROOT, "groups", "EzCloudGen_group.nk")
GIZMO_PATH = os.path.join(ROOT, "gizmos", "EzCloudGen.gizmo")
TYPE_NAMES = list(cloud_types.TYPES)
LAYER_DEFAULTS = [("Cumulus", True), ("Hero Cumulus", False), ("Cirrus", False)]

# Per layer knobs: (kernel param, label, tooltip, min, max). The first block is always shown;
# the rest are under "shape".
MAIN = [
    ("base", "base height", "Height of the cloud base above the ground, in metres.", 0, 12000),
    ("thickness", "thickness", "Depth of the layer, base to top, in metres.", 50, 6000),
    ("coverage", "coverage", "How much of the sky the layer covers.", 0, 1),
    ("scale_km", "size", "Size of the cloud shapes across the ground, in km.", 0.1, 10),
    ("wind_deg", "wind direction", "Direction the shapes stretch and drift along, in degrees "
                                   "(0 = away from the world -Z axis, 90 = +X).", -180, 180),
]
SHAPE = [
    ("stretch", "stretch", "Elongation along the wind (1 = round).", 1, 10),
    ("edge", "edge softness", "Softness of the cloud edges.", 0.01, 0.5),
    ("taper", "domes", "How much the clouds narrow going up: cumulus domes and towers.", 0, 2),
    ("bottom_round", "base rounding", "Rounding at the base, as a share of the thickness (small = flat base).", 0, 1),
    ("top_round", "top rounding", "Rounding at the top, as a share of the thickness.", 0, 1),
    ("sigma", "thickness of cloud", "Extinction per metre: high is dense and hard edged, low is thin and veil-like.",
     0.0005, 0.1),
    ("cells", "cells", "Cellular rows (altocumulus, cirrocumulus).", 0, 1),
    ("cell_km", "cell size", "Size of the cells, in km.", 0.05, 2),
    ("warp", "warp", "How much the shapes swirl.", 0, 4),
    ("forward", "forward scatter", "How much light the clouds throw forward: the silver lining when backlit.", 0, 0.95),
    ("ambient", "sky light", "How much sky light the layer takes.", 0, 3),
    ("octaves", "detail octaves", "Detail levels (more is finer and slower).", 0, 5),
    ("billow", "billows", "1: billowy cauliflower detail. 0: soft wisps.", 0, 1),
    ("streaks", "streaks", "1: fibrous streaks (cirrus).", 0, 1),
    ("vary", "height variation", "How much the base and top move up and down across the deck.", 0, 0.5),
]

# The erosion stack, shown on each layer.
EROSION = [
    ("erosion", "billows", "How much the billows (cauliflower bumps, or soft wisps with 'billow' at 0) break "
                           "up the surface.", 0, 1),
    ("detail_size", "billow size", "Size of the billows, in metres.", 10, 1000),
    ("wisp_amount", "wisps", "Fine wisps that eat into the thin edges.", 0, 1),
    ("wisp_size", "wisp size", "Size of the wisps, in metres.", 2, 500),
    ("grain_amount", "grain", "The finest breakup of the edges.", 0, 1),
    ("grain_size", "grain size", "Size of the grain, in metres.", 1, 100),
    ("swirl", "swirl", "Curls the detail around, for swirly wisps.", 0, 1),
    ("swirl_size", "swirl size", "Size of the swirls, in metres.", 20, 3000),
    ("shear", "wind shear", "Leans the tops downwind (along 'wind direction').", -1, 1),
]
# A placed volume (types with volume on).
VOLUME = [
    ("lumps", "lumps", "Big noise that breaks the shape into towers and bulges.", 0, 1.5),
    ("lump_size", "lump size", "Size of the lumps, in metres.", 20, 5000),
]
VOL_SHAPES = ["Ellipsoid", "Dome", "Anvil", "Box"]
# Knobs shown only for decks, and only for volumes.
DECK_ONLY = ["thickness", "scale_km", "stretch", "taper", "top_round", "cells", "cell_km", "warp", "streaks", "vary",
             "map_amount", "map_channel"]
MAP_CHANNELS = ["luminance", "red", "green", "blue", "alpha"]
VOL_ONLY = ["vol_divider", "vol_shape", "vol_position", "vol_rotate", "vol_size", "place", "place_km", "lumps",
            "lump_size"]

LAYERS = {"cloud": ["red", "green", "blue", "alpha"],
          "cloud_sun": ["red", "green", "blue"],
          "cloud_sky": ["red", "green", "blue"]}


def find(var, index, knob):
    """Python that sets `var` to the node in input `index` that has `knob`, through Dots or NoOps."""
    return ("%s = nuke.thisNode().input(%d)\n"
            "while %s is not None and not %s.knob('%s'):\n"
            "    %s = %s.input(0) if %s.inputs() else None\n" % (var, index, var, var, knob, var, var, var))


FIND_CAMERA = find("c", 1, "focal")
FIND_ATMOS = find("a", 2, "haze_density")
FIND_AXIS = find("x", 3, "world_matrix")
VIEWS = ["Comp", "Clouds", "Sun share", "Depth", "Variations"]


def py(code):
    return "[python -execlocal {%s}]" % code


def atmos_light(pixel, channel, fallback):
    """Python expression: one channel of a pixel of the EzAtmosScatter's measured HDRI light."""
    return py(FIND_ATMOS +
              "l = nuke.toNode(a.fullName() + '.Light') if a is not None else None\n"
              "ret = l.sample('%s', %g, 0.5) if l is not None else %s\n" % (channel, pixel + 0.5, fallback))


# ---- The type menu ------------------------------------------------------------------------

def knob_changed():
    # Plain top-level code: Nuke runs knob scripts with separate locals, which functions and
    # comprehensions can't see.
    table = dict((name, cloud_types.full(name)) for name in TYPE_NAMES)
    return ("k = nuke.thisKnob()\n"
            "n = nuke.thisNode()\n"
            "layers = []\n"
            "if k.name() in ('l1_type', 'l2_type', 'l3_type'):\n"
            "    p = k.name()[:3]\n"
            "    t = %r\n"
            "    for key, v in t[k.value()].items():\n"
            "        if n.knob(p + key) is not None:\n"
            "            n[p + key].setValue(list(v) if isinstance(v, tuple) else v)\n"
            "    # A PyScript button can't be executed from inside knobChanged ('already executing'), so\n"
            "    # its code runs here. Every volume type re-places (base and distance come with the type),\n"
            "    # unless the position is animated or linked.\n"
            "    if n[p + 'volume'].value() > 0.5 and not n[p + 'vol_position'].isAnimated():\n"
            "        exec(n[p + 'place'].value(), {'nuke': nuke})\n"
            "    layers = [p]\n"
            "elif k.name() == 'showPanel':\n"
            "    layers = ['l1_', 'l2_', 'l3_']\n"
            "for p in layers:\n"
            "    vol = n[p + 'volume'].value() > 0.5\n"
            "    for name in %r:\n"
            "        n[p + name].setVisible(not vol)\n"
            "    for name in %r:\n"
            "        n[p + name].setVisible(vol)\n" % (table, DECK_ONLY, VOL_ONLY))


def place_script(p):
    """The 'place in front of camera' button: the volume's base centre 'place km' ahead of the
    camera (level, along where it looks), at the layer's base height."""
    return ("n = nuke.thisNode()\n"
            "m = n['cam_world_matrix']\n"
            "s = n['scene_scale'].value() or 1.0\n"
            "fx, fz = -m.getValue(2), -m.getValue(10)\n"
            "l = (fx * fx + fz * fz) ** 0.5\n"
            "if l < 1e-6:\n"
            "    fx, fz, l = 0.0, -1.0, 1.0\n"
            "d = n['%splace_km'].value() * 1000.0 / s\n"
            "n['%svol_position'].setValue([m.getValue(3) + fx / l * d, n['ground_height'].value() + "
            "n['%sbase'].value() / s, m.getValue(11) + fz / l * d])\n" % (p, p, p))


# The variations buttons: the layer is 'variations of'.
VARIATIONS_LAYER = ("n = nuke.thisNode()\n"
                    "p = 'l%d_' % (int(n['variations_of'].getValue()) + 1)\n")
VARIATIONS_SHOW = VARIATIONS_LAYER + "n[p + 'enable'].setValue(True)\nn['view'].setValue('Variations')\n"
VARIATIONS_NEXT = (VARIATIONS_LAYER + "n[p + 'seed'].setValue(n[p + 'seed'].value() + 9)\n"
                   "n['view'].setValue('Variations')\n")
VARIATIONS_USE = (VARIATIONS_LAYER + "k = min(max(int(n['variation_pick'].value()), 1), 9)\n"
                  "n[p + 'seed'].setValue(n[p + 'seed'].value() + k - 1)\n"
                  "n['view'].setValue('Comp')\n")


# ---- Knobs --------------------------------------------------------------------------------

def add(g, knob, tooltip=None, flags=()):
    if tooltip:
        knob.setTooltip(tooltip)
    for f in flags:
        knob.setFlag(f)
    g.addKnob(knob)
    return knob


def hidden(g, knob):
    knob.setFlag(nuke.INVISIBLE)
    g.addKnob(knob)
    return knob


def build_knobs(g):
    add(g, nuke.Tab_Knob("ezcloudgen", "EzCloudGen"))
    v = add(g, nuke.Enumeration_Knob("view", "view", VIEWS),
            "Comp: the clouds over 'bg' (or alone without it). Clouds: the clouds alone, premultiplied. "
            "Sun share: the direct sunlight part of the clouds. Depth: Planar Z of the clouds, scene units. "
            "Variations: nine seeds of one layer side by side (see 'variations').")
    v.setValue("Comp")
    add(g, nuke.Boolean_Knob("breakout", "breakout layers"),
        "Adds the layers cloud (rgba), cloud_sun and cloud_sky (rgb), for re-grading the clouds over the "
        "plate. Takes a second pass per layer.").setValue(True)
    r = add(g, nuke.Enumeration_Knob("resolution", "resolution", ["Full", "Half", "Quarter"]),
            "Render the clouds smaller and scale them back up: much faster, softer.")
    r.setValue("Half")
    add(g, nuke.Double_Knob("quality", "quality"),
        "Ray march step count: higher is smoother and slower.").setValue(1.0)
    g["quality"].setRange(0.25, 4)
    s = add(g, nuke.Int_Knob("samples", "samples"), "Jittered samples per pixel: anti-aliasing and less grain.")
    s.setValue(1)
    add(g, nuke.Double_Knob("max_distance", "max distance"),
        "Clouds further than this (km) are not drawn.").setValue(80)
    g["max_distance"].setRange(5, 200)

    add(g, nuke.Text_Knob("scene_divider", "scene"))
    add(g, nuke.Double_Knob("scene_scale", "units to metres"),
        "Scene units to metres: 0.1 for decimetres.").setValue(0.1)
    add(g, nuke.Double_Knob("ground_height", "ground height"),
        "Height of the ground in scene units; the camera's height above it places it under the clouds."
        ).setValue(0)
    g["ground_height"].setRange(-10000, 10000)

    add(g, nuke.Text_Knob("sun_divider", "sun"))
    sf = add(g, nuke.Enumeration_Knob("sun_from", "sun from", ["Auto", "Axis", "EzAtmosScatter", "Manual"]),
             "Auto: the Axis in 'sun' if there is one, else the EzAtmosScatter in 'atmos', else 'sun direction'.")
    sf.setValue("Auto")
    sd = add(g, nuke.XYZ_Knob("sun_direction", "sun direction"), "Direction towards the sun, +Y up.")
    sd.setValue([0.3, 0.35, -1.0])
    add(g, nuke.XYZ_Knob("sun_in_use", "sun in use"), "The sun direction being used (read only).")
    g["sun_in_use"].setEnabled(False)
    lf = add(g, nuke.Enumeration_Knob("light_from", "light from", ["Auto", "Manual"]),
             "Auto: the sun and sky light the EzAtmosScatter in 'atmos' measures in its HDRI. "
             "Manual (or no atmos): 'sun color' and 'sky color'.")
    lf.setValue("Auto")
    c = add(g, nuke.Color_Knob("sun_color", "sun color"), "Sunlight (irradiance) when the light is Manual.")
    c.setValue([12.0, 11.3, 10.0])
    c = add(g, nuke.Color_Knob("sky_color", "sky color"), "Sky light (radiance) when the light is Manual.")
    c.setValue([0.12, 0.25, 0.58])
    c = add(g, nuke.Color_Knob("ground_color", "ground bounce"), "Light bounced up from the ground onto the cloud bases.")
    c.setValue([0.08, 0.07, 0.06])
    add(g, nuke.Double_Knob("sun_intensity", "sun intensity"), "Multiplies the sunlight.").setValue(1.0)
    add(g, nuke.Double_Knob("sky_intensity", "sky intensity"), "Multiplies the sky light.").setValue(1.0)

    add(g, nuke.Text_Knob("haze_divider", "air"))
    add(g, nuke.Double_Knob("haze_distance", "haze distance"),
        "Distance (km) over which far clouds fade into the haze colour. 0: off.").setValue(60)
    g["haze_distance"].setRange(0, 200)
    c = add(g, nuke.Color_Knob("haze_color", "haze color"),
            "Colour far clouds fade to. With the light from an atmos it multiplies the atmos's sky colour.")
    c.setValue([1.4, 1.35, 1.3])

    add(g, nuke.Text_Knob("gap_divider", "sun gap"))
    add(g, nuke.Double_Knob("gap_amount", "gap toward sun"),
        "Opens a hole in every layer where the line from the camera to the sun crosses it, so the sun "
        "and EzCloudShafts' shafts come through.").setValue(0)
    add(g, nuke.Double_Knob("gap_size", "gap size"), "Radius of the gap, in km.").setValue(2)

    add(g, nuke.Text_Knob("time_divider", "time"))
    add(g, nuke.Double_Knob("evolve_speed", "evolve"),
        "How fast the cloud detail boils, in metres per second.").setValue(0.5)
    add(g, nuke.Double_Knob("seed", "seed"), "Changes every layer's clouds.").setValue(0)

    add(g, nuke.Text_Knob("variations_divider", "variations"))
    k = add(g, nuke.Enumeration_Knob("variations_of", "variations of", ["Layer 1", "Layer 2", "Layer 3"]),
            "The layer 'show me variations' shows.")
    add(g, nuke.PyScript_Knob("show_variations", "show me variations", VARIATIONS_SHOW),
        "Shows nine seeds of this layer side by side (view: Variations). Pick one with 'use number'.")
    g["show_variations"].clearFlag(nuke.STARTLINE)
    add(g, nuke.PyScript_Knob("next_variations", "next nine", VARIATIONS_NEXT), "Nine more seeds.")
    g["next_variations"].clearFlag(nuke.STARTLINE)
    k = add(g, nuke.Int_Knob("variation_pick", "use number"),
            "1 is the top left, reading along the rows to 9 at the bottom right.")
    k.setValue(1)
    add(g, nuke.PyScript_Knob("use_variation", "use it", VARIATIONS_USE),
        "Sets the layer's seed to that variation and goes back to the Comp view.")
    g["use_variation"].clearFlag(nuke.STARTLINE)

    add(g, nuke.Text_Knob("map_divider", "coverage map"))
    add(g, nuke.Text_Knob("map_help", "",
                          "Plug a picture into 'map' to say where the decks have clouds, as seen\n"
                          "through the camera on 'map frame': white covers the sky, mid grey keeps\n"
                          "the layer's coverage, black clears it. Paint it with a Roto over the plate,\n"
                          "soft and blurred. It stays put in the world and drifts with the wind."))
    k = add(g, nuke.Int_Knob("map_frame", "map frame"), "The frame the map is painted on.")
    k.setValue(int(nuke.root()["first_frame"].value()))
    add(g, nuke.PyScript_Knob("map_frame_here", "use this frame",
                              "nuke.thisNode()['map_frame'].setValue(nuke.frame())"),
        "Sets 'map frame' to the current frame.")
    g["map_frame_here"].clearFlag(nuke.STARTLINE)

    for i, (tname, on) in enumerate(LAYER_DEFAULTS):
        p = "l%d_" % (i + 1)
        add(g, nuke.Tab_Knob(p + "tab", "Layer %d" % (i + 1)))
        add(g, nuke.Boolean_Knob(p + "enable", "enable"),
            "Draw this layer. Layers sort themselves by depth.").setValue(on)
        t = add(g, nuke.Enumeration_Knob(p + "type", "type", TYPE_NAMES),
                "Sets this layer's shape knobs to the type's values (they can be tuned after).")
        t.setValue(tname)
        vals = cloud_types.full(tname)
        for name, label, tip, lo, hi in MAIN:
            k = add(g, nuke.Double_Knob(p + name, label), tip)
            k.setRange(lo, hi)
            k.setValue(vals[name])
        k = add(g, nuke.Double_Knob(p + "map_amount", "follow map"),
                "How much this deck follows the coverage map (when 'map' is plugged in).")
        k.setValue(1.0)
        k = add(g, nuke.Enumeration_Knob(p + "map_channel", "map channel", MAP_CHANNELS),
                "Which channel of the map this deck reads: paint each deck in its own channel to place "
                "them separately.")
        k.clearFlag(nuke.STARTLINE)
        add(g, nuke.Text_Knob(p + "vol_divider", "volume"))
        k = add(g, nuke.Enumeration_Knob(p + "vol_shape", "shape", VOL_SHAPES),
                "The volume's overall shape, before lumps and erosion break it up.")
        k.setValue(int(vals["vol_shape"]))
        add(g, nuke.XYZ_Knob(p + "vol_position", "position"),
            "Centre of the volume's base, in scene units (drag it in the 3D viewer, or link it to an Axis).")
        add(g, nuke.XYZ_Knob(p + "vol_rotate", "rotate"), "Turns the volume, in degrees (Y, then X, then Z).")
        k = g[p + "vol_position"]
        if vals["volume"]:
            # In front of the default view (no camera: looking along -Z), in decimetres.
            k.setValue([0, vals["base"] / 0.1, -vals["place_km"] * 1000 / 0.1])
        k = add(g, nuke.XYZ_Knob(p + "vol_size", "size"), "Width, height and depth of the volume, in metres.")
        k.setValue(list(vals["vol_size"]))
        add(g, nuke.PyScript_Knob(p + "place", "place in front of camera", place_script(p)),
            "Puts the volume 'distance' ahead of the camera, on the ground at 'base height'.")
        k = add(g, nuke.Double_Knob(p + "place_km", "distance"), "How far ahead 'place in front of camera' puts it, km.")
        k.setValue(vals["place_km"])
        k.clearFlag(nuke.STARTLINE)
        for name, label, tip, lo, hi in VOLUME:
            k = add(g, nuke.Double_Knob(p + name, label), tip)
            k.setRange(lo, hi)
            k.setValue(vals[name])
        add(g, nuke.Text_Knob(p + "erosion_divider", "erosion"))
        for name, label, tip, lo, hi in EROSION:
            k = add(g, nuke.Double_Knob(p + name, label), tip)
            k.setRange(lo, hi)
            k.setValue(vals[name])
        add(g, nuke.Text_Knob(p + "more_divider", ""))
        add(g, nuke.Double_Knob(p + "density", "density"), "Multiplies the cloud density.").setValue(1.0)
        add(g, nuke.Double_Knob(p + "wind_speed", "wind speed"), "Drift along the wind direction, m/s.").setValue(5.0)
        add(g, nuke.Double_Knob(p + "seed", "seed"), "Changes this layer's clouds.").setValue(i * 11.0)
        add(g, nuke.Tab_Knob(p + "shape", "more shape", nuke.TABBEGINCLOSEDGROUP))
        for name, label, tip, lo, hi in SHAPE:
            k = add(g, nuke.Double_Knob(p + name, label), tip)
            k.setRange(lo, hi)
            k.setValue(vals[name])
        add(g, nuke.Tab_Knob(p + "shape_end", "", nuke.TABENDGROUP))
        k = hidden(g, nuke.Int_Knob(p + "volume"))
        k.setValue(int(vals["volume"]))
        for name in (DECK_ONLY if vals["volume"] else VOL_ONLY):
            g[p + name].setVisible(False)

    add(g, nuke.Tab_Knob("about", "About"))
    add(g, nuke.Text_Knob("version", "", "EzCloudGen v%s" % VERSION))

    # Hidden: the camera, atmos and Axis through any Dots or NoOps in their inputs.
    m = hidden(g, nuke.Array_Knob("cam_world_matrix", "camera matrix", 16))
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    # Without a camera: 300 m up (in decimetres), looking level along -Z.
    identity[7] = 3000
    for i in range(16):
        m.setExpression(py(FIND_CAMERA + "ret = c['world_matrix'].getValueAt(nuke.frame(), %d) "
                                         "if c is not None else %g" % (i, identity[i])), i)
    for name, default in (("focal", 24), ("haperture", 36)):
        k = hidden(g, nuke.Double_Knob("cam_" + name))
        k.setExpression(py(FIND_CAMERA + "ret = c['%s'].getValueAt(nuke.frame()) if c is not None else %g"
                           % (name, default)))
    # The camera on the map frame.
    m = hidden(g, nuke.Array_Knob("map_cam_matrix", "map camera matrix", 16))
    for i in range(16):
        m.setExpression(py(FIND_CAMERA + "ret = c['world_matrix'].getValueAt(nuke.thisNode()['map_frame'].value(), %d) "
                                         "if c is not None else %g" % (i, identity[i])), i)
    for name, default in (("focal", 24), ("haperture", 36)):
        k = hidden(g, nuke.Double_Knob("map_cam_" + name))
        k.setExpression(py(FIND_CAMERA + "ret = c['%s'].getValueAt(nuke.thisNode()['map_frame'].value()) "
                                         "if c is not None else %g" % (name, default)))
    k = hidden(g, nuke.Int_Knob("map_found"))
    k.setExpression(py("ret = 1 if nuke.thisNode().input(4) is not None else 0"))
    k = hidden(g, nuke.Int_Knob("atm_found"))
    k.setExpression(py(FIND_ATMOS + "ret = 1 if a is not None else 0"))
    k = hidden(g, nuke.XYZ_Knob("atm_sun"))
    for i in range(3):
        k.setExpression(py(FIND_ATMOS + "ret = (a.knob('sun_in_use') or a.knob('sun_direction'))"
                                        ".getValueAt(nuke.frame(), %d) if a is not None else 0" % i), i)
    k = hidden(g, nuke.Double_Knob("atm_rotation"))
    k.setExpression(py(FIND_ATMOS + "ret = a['hdri_rotation'].getValueAt(nuke.frame()) "
                                    "if a is not None and a.knob('hdri_rotation') else 0"))
    k = hidden(g, nuke.Color_Knob("atm_sun_color"))
    for i, ch in enumerate(("red", "green", "blue")):
        k.setExpression(atmos_light(1, ch, 0), i)
    k = hidden(g, nuke.Color_Knob("atm_sky_color"))
    for i, ch in enumerate(("red", "green", "blue")):
        k.setExpression(atmos_light(2, ch, 0), i)
    k = hidden(g, nuke.Int_Knob("axis_found"))
    k.setExpression(py(FIND_AXIS + "ret = 1 if x is not None else 0"))
    k = hidden(g, nuke.XYZ_Knob("axis_position"))
    for i in range(3):
        k.setExpression(py(FIND_AXIS + "ret = x['world_matrix'].getValueAt(nuke.frame(), %d) "
                                       "if x is not None else 0" % (3 + 4 * i)), i)
    k = hidden(g, nuke.Int_Knob("bg_found"))
    k.setExpression(py("ret = 1 if nuke.thisNode().input(0) is not None else 0"))
    # 0 manual, 1 Axis, 2 atmos.
    k = hidden(g, nuke.Int_Knob("sun_source"))
    k.setExpression("sun_from==1 ? (axis_found ? 1 : 0) : sun_from==2 ? (atm_found ? 2 : 0) : "
                    "sun_from==3 ? 0 : (axis_found ? 1 : atm_found ? 2 : 0)")
    # The atmos light is used when asked for and when it measured something (it is 0 when self lit).
    k = hidden(g, nuke.Int_Knob("light_source"))
    k.setExpression("light_from==0 && atm_found && (atm_sun_color.r + atm_sun_color.g + atm_sun_color.b) > 0 "
                    "? 1 : 0")
    k = hidden(g, nuke.Double_Knob("sun_rotation_in_use"))
    k.setExpression("sun_source==2 ? atm_rotation : 0")
    k = hidden(g, nuke.Color_Knob("sun_color_in_use"))
    k2 = hidden(g, nuke.Color_Knob("sky_color_in_use"))
    k3 = hidden(g, nuke.Color_Knob("haze_color_in_use"))
    for i, c in enumerate("rgb"):
        g["sun_in_use"].setExpression("sun_source==1 ? axis_position.%s : sun_source==2 ? atm_sun.%s : "
                                      "sun_direction.%s" % ("xyz"[i], "xyz"[i], "xyz"[i]), i)
        k.setExpression("(light_source ? atm_sun_color.%s : sun_color.%s) * sun_intensity" % (c, c), i)
        k2.setExpression("(light_source ? atm_sky_color.%s : sky_color.%s) * sky_intensity" % (c, c), i)
        k3.setExpression("light_source ? atm_sky_color.%s * haze_color.%s : haze_color.%s * 0.43" % (c, c, c), i)
    k = hidden(g, nuke.Double_Knob("work_scale"))
    k.setExpression("resolution==0 ? 1 : resolution==1 ? 0.5 : 0.25")
    k = hidden(g, nuke.Double_Knob("time_s"))
    k.setExpression("frame / max(root.fps, 1)")

    g["knobChanged"].setValue(knob_changed())


# ---- The nodes inside --------------------------------------------------------------------

def blink(name, output, src, cmap, layer, source_file):
    n = compiled(name, source_file)
    n.setInput(0, src)
    n.setInput(1, cmap)
    k = KERNEL + "_"
    p = "parent.l%d_" % layer
    n[k + "output"].setValue(output)
    rows = ((0, 1, 2), (4, 5, 6), (8, 9, 10))
    for r, idx in enumerate(rows):
        for j, m in enumerate(idx):
            n[k + "cam_row%d" % r].setExpression("parent.cam_world_matrix.%d" % m, j)
    for j, m in enumerate((3, 7, 11)):
        n[k + "cam_position"].setExpression("parent.cam_world_matrix.%d" % m, j)
    n[k + "focal"].setExpression("parent.cam_focal")
    n[k + "haperture"].setExpression("parent.cam_haperture")
    # The camera frame is the work format.
    n[k + "frame_size"].setExpression("width", 0)
    n[k + "frame_size"].setExpression("height", 1)
    n[k + "scene_scale"].setExpression("parent.scene_scale")
    n[k + "ground_height"].setExpression("parent.ground_height")
    for j, c in enumerate("xyz"):
        n[k + "sun_direction"].setExpression("parent.sun_in_use.%s" % c, j)
    n[k + "sun_rotation"].setExpression("parent.sun_rotation_in_use")
    for j, c in enumerate("rgb"):
        n[k + "sun_color"].setExpression("parent.sun_color_in_use.%s" % c, j)
        n[k + "sky_color"].setExpression("parent.sky_color_in_use.%s" % c, j)
        n[k + "ground_color"].setExpression("parent.ground_color.%s * parent.sky_intensity" % c, j)
        n[k + "haze_color"].setExpression("parent.haze_color_in_use.%s" % c, j)
    n[k + "haze_distance"].setExpression("parent.haze_distance * 1000")
    n[k + "max_distance"].setExpression("parent.max_distance * 1000")
    n[k + "quality"].setExpression("parent.quality")
    n[k + "samples"].setExpression("parent.samples")
    n[k + "seed"].setExpression("parent.seed + %sseed" % p)
    n[k + "evolve"].setExpression("parent.evolve_speed * parent.time_s")
    # Drift with the wind: the field is sampled upwind.
    n[k + "offset"].setExpression("-%swind_speed * parent.time_s * sin(radians(%swind_deg))" % (p, p), 0)
    n[k + "offset"].setExpression("%swind_speed * parent.time_s * cos(radians(%swind_deg))" % (p, p), 1)
    n[k + "gap_amount"].setExpression("parent.gap_amount")
    n[k + "gap_size"].setExpression("parent.gap_size * 1000")
    for name, _, _, _, _ in MAIN + SHAPE + EROSION + VOLUME:
        n[k + name].setExpression(p + name)
    n[k + "volume"].setExpression(p + "volume")
    n[k + "vol_shape"].setExpression(p + "vol_shape")
    n[k + "vol_center"].setExpression(p + "vol_position.x", 0)
    n[k + "vol_center"].setExpression("%svol_position.y + %svol_size.y / 2 / max(parent.scene_scale, 1e-6)" % (p, p), 1)
    n[k + "vol_center"].setExpression(p + "vol_position.z", 2)
    for j, c in enumerate("xyz"):
        n[k + "vol_rotate"].setExpression("%svol_rotate.%s" % (p, c), j)
        n[k + "vol_size"].setExpression("%svol_size.%s" % (p, c), j)
    n[k + "density"].setExpression(p + "density")
    # The coverage map, through the camera on the map frame, drifting with the wind since then.
    n[k + "use_map"].setExpression("parent.map_found")
    n[k + "map_amount"].setExpression(p + "map_amount")
    n[k + "map_channel"].setExpression(p + "map_channel")
    for r, idx in enumerate(rows):
        for j, m in enumerate(idx):
            n[k + "map_row%d" % r].setExpression("parent.map_cam_matrix.%d" % m, j)
    for j, m in enumerate((3, 7, 11)):
        n[k + "map_position"].setExpression("parent.map_cam_matrix.%d" % m, j)
    n[k + "map_focal"].setExpression("parent.map_cam_focal")
    n[k + "map_haperture"].setExpression("parent.map_cam_haperture")
    since = "(parent.time_s - parent.map_frame / max(root.fps, 1))"
    n[k + "map_drift"].setExpression("-%swind_speed * %s * sin(radians(%swind_deg))" % (p, since, p), 0)
    n[k + "map_drift"].setExpression("%swind_speed * %s * cos(radians(%swind_deg))" % (p, since, p), 1)
    # The variations sheet.
    n[k + "tiles"].setExpression("parent.view==4 && parent.variations_of==%d ? 3 : 1" % (layer - 1))
    n["disable"].setExpression(DISABLE % (layer, layer - 1))
    return n


# A layer is off when disabled, and in the Variations view unless it is the one shown.
DISABLE = "!parent.l%d_enable || (parent.view==4 && parent.variations_of!=%d)"


def lf_copy(kernel):
    """An LF-only copy of a kernel in the temp folder (a Windows checkout may have CRLF)."""
    import tempfile
    with open(os.path.join(ROOT, "blink", kernel + ".blink")) as f:
        text = f.read().replace("\r\n", "\n")
    path = os.path.join(tempfile.gettempdir(), kernel + ".blink").replace("\\", "/")
    with open(path, "w", newline="\n") as f:
        f.write(text)
    return path


def compiled(name, source_file):
    """A BlinkScript compiled from a file. Terminal Nuke only compiles a kernel loaded from a file
    (setting kernelSource and pressing recompile leaves it uncompiled, and renders cancel). The
    file is then cleared, so the node keeps the source and needs no file."""
    n = nuke.nodes.BlinkScript(name=name)
    n["kernelSourceFile"].setValue(source_file)
    n["reloadKernelSourceFile"].execute()
    n["recompile"].execute()
    n["kernelSourceFile"].setValue("")
    return n


def build():
    for layer, chans in LAYERS.items():
        nuke.Layer(layer, ["%s.%s" % (layer, c) for c in chans])
    source = lf_copy(KERNEL)
    stack_source = lf_copy(STACK_KERNEL)

    g = nuke.nodes.Group(name="EzCloudGen")
    build_knobs(g)
    g["tile_color"].setValue(0x8fb3d9ff)
    with g:
        bg = nuke.nodes.Input(name="bg")
        cam = nuke.nodes.Input(name="camera")
        atm = nuke.nodes.Input(name="atmos")
        sun = nuke.nodes.Input(name="sun")
        mp = nuke.nodes.Input(name="map")
        for n in (cam, atm, sun, mp):
            n.setXYpos(-1000, -1000)  # placed by the layout
        # The format: the bg's, or the script's without one.
        rootfmt = nuke.nodes.Constant(name="RootFormat", channels="rgba", color=0)
        fmt = nuke.nodes.Switch(name="FormatSource")
        fmt.setInput(0, rootfmt)
        fmt.setInput(1, bg)
        fmt["which"].setExpression("parent.bg_found")
        # Black rgba in the work format: the kernels' src (a disabled layer passes it through).
        black = nuke.nodes.Remove(name="WorkClear", operation="keep", channels="rgba")
        black.setInput(0, fmt)
        black = nuke.nodes.Multiply(name="WorkBlack", channels="rgba", value=0)
        black.setInput(0, nuke.toNode("WorkClear"))
        work = nuke.nodes.Reformat(name="WorkFormat", type="scale", filter="Impulse", black_outside=True)
        work["scale"].setExpression("parent.work_scale")
        work.setInput(0, black)

        colour, sunpart, depth, zkeys = [], [], [], []
        for i in range(1, 4):
            colour.append(blink("L%d_Color" % i, 0, work, mp, i, source))
            sp = blink("L%d_Sun" % i, 1, work, mp, i, source)
            sp["disable"].setExpression("(%s) || !(parent.breakout || parent.view==2)" % (DISABLE % (i, i - 1)))
            sunpart.append(sp)
            d = blink("L%d_Depth" % i, 2, work, mp, i, source)
            zkeys.append(d)
            pm = nuke.nodes.Premult(name="L%d_DepthPremult" % i, channels="rgb")
            pm.setInput(0, d)
            depth.append(pm)

        def stack(prefix, nodes):
            # Nearest layer first, per pixel, ordered by the depth passes.
            m = compiled(prefix + "_Stack", stack_source)
            for j, n in enumerate(nodes + zkeys):
                m.setInput(j, n)
            return m

        col = stack("Color", colour)
        sunm = stack("Sun", sunpart)
        dep = stack("Depth", depth)
        unp = nuke.nodes.Unpremult(name="DepthUnpremult", channels="rgb")
        unp.setInput(0, dep)

        def up(name, src):
            r = nuke.nodes.Reformat(name=name, type="to box", box_fixed=True, resize="distort",
                                    filter="Cubic", black_outside=True)
            r["box_width"].setExpression("FormatSource.width")
            r["box_height"].setExpression("FormatSource.height")
            r.setInput(0, src)
            return r

        col_up = up("ColorUp", col)
        sun_up = up("SunUp", sunm)
        dep_up = nuke.nodes.Reformat(name="DepthUp", type="to box", box_fixed=True, resize="distort",
                                     filter="Impulse", black_outside=True)
        dep_up["box_width"].setExpression("FormatSource.width")
        dep_up["box_height"].setExpression("FormatSource.height")
        dep_up.setInput(0, unp)

        # Comp: the clouds over the bg (or alone).
        over = nuke.nodes.Merge2(name="CompOver", operation="over")
        over.setInput(0, bg)
        over.setInput(1, col_up)
        comp = nuke.nodes.Switch(name="CompOrClouds")
        comp.setInput(0, col_up)
        comp.setInput(1, over)
        comp["which"].setExpression("parent.bg_found")

        # The layers.
        z = nuke.nodes.Copy(name="Layer_DepthZ", from0="rgba.red", to0="depth.Z")
        z.setInput(0, comp)
        z.setInput(1, dep_up)
        cl = nuke.nodes.Copy(name="Layer_Cloud")
        for j, c in enumerate(("red", "green", "blue", "alpha")):
            cl["from%d" % j].setValue("rgba." + c)
            cl["to%d" % j].setValue("cloud." + c)
        cl.setInput(0, z)
        cl.setInput(1, col_up)
        cs = nuke.nodes.Copy(name="Layer_CloudSun")
        for j, c in enumerate(("red", "green", "blue")):
            cs["from%d" % j].setValue("rgba." + c)
            cs["to%d" % j].setValue("cloud_sun." + c)
        cs.setInput(0, cl)
        cs.setInput(1, sun_up)
        sky = nuke.nodes.Merge2(name="SkyPart", operation="from", output="rgb")
        sky.setInput(0, col_up)
        sky.setInput(1, sun_up)
        ck = nuke.nodes.Copy(name="Layer_CloudSky")
        for j, c in enumerate(("red", "green", "blue")):
            ck["from%d" % j].setValue("rgba." + c)
            ck["to%d" % j].setValue("cloud_sky." + c)
        ck.setInput(0, cs)
        ck.setInput(1, sky)
        layers = nuke.nodes.Switch(name="BreakoutOrNot")
        layers.setInput(0, z)
        layers.setInput(1, ck)
        layers["which"].setExpression("parent.breakout")

        # Views.
        clouds_view = nuke.nodes.Copy(name="View_Clouds", channels="rgba")
        clouds_view.setInput(0, layers)
        clouds_view.setInput(1, col_up)
        sun_view = nuke.nodes.Copy(name="View_Sun", channels="rgba")
        sun_view.setInput(0, layers)
        sun_view.setInput(1, sun_up)
        depth_view = nuke.nodes.Copy(name="View_Depth", channels="rgba")
        depth_view.setInput(0, layers)
        depth_view.setInput(1, dep_up)
        view = nuke.nodes.Switch(name="ViewOutput")
        # Variations: the comp, with only the layer shown, tiled (by the kernels).
        for j, n in enumerate((layers, clouds_view, sun_view, depth_view, layers)):
            view.setInput(j, n)
        view["which"].setExpression("parent.view")
        out = nuke.nodes.Output(name="Output1")
        out.setInput(0, view)

    # Inputs in the order nuke numbers them: by creation, bg 0, camera 1, atmos 2, sun 3, map 4.
    problems = node_layout.apply_nuke(g, modules=MODULES, labels=LABELS)
    for p in problems:
        print("layout: " + p)
    return g


MODULES = [
    ("Inputs", 0x4a5a6aff, r"(bg|camera|atmos|sun|map|RootFormat|FormatSource|WorkClear|WorkBlack|WorkFormat)"),
    ("Cloud layers", 0x3a5a4aff, r"(L\d_.*)"),
    ("Stack the layers", 0x4a5a6aff, r"(Color_Stack|Sun_Stack|Depth_Stack|DepthUnpremult)"),
    ("Back to full size", 0x444444ff, r"(ColorUp|SunUp|DepthUp)"),
    ("Comp", 0x3a4a6aff, r"(CompOver|CompOrClouds)"),
    ("Layers", 0x6a4a4aff, r"(Layer_.*|SkyPart|BreakoutOrNot)"),
    ("Views", 0x5a4a6aff, r"(View_.*|ViewOutput)"),
    ("Output", 0x6a4a4aff, r"(Output\d*)"),
]
LABELS = {"FormatSource": "bg plugged in", "CompOrClouds": "bg plugged in", "BreakoutOrNot": "breakout",
          "ViewOutput": "view"}


def save(g):
    for n in nuke.selectedNodes():
        n.setSelected(False)
    g.setSelected(True)
    for path in (GROUP_PATH, GIZMO_PATH):
        d = os.path.dirname(path)
        if not os.path.isdir(d):
            os.makedirs(d)
    nuke.nodeCopy(GROUP_PATH)
    with open(GROUP_PATH) as f:
        text = f.read()
    # The gizmo: the same node with Gizmo in place of Group, and no paste stack lines.
    lines = [l for l in text.splitlines() if not l.startswith(("set cut_paste_input", "push $cut_paste_input"))]
    gizmo = "\n".join(lines).replace("\nGroup {", "\nGizmo {", 1)
    if "Gizmo {" not in gizmo:
        gizmo = gizmo.replace("Group {", "Gizmo {", 1)
    with open(GIZMO_PATH, "w") as f:
        f.write(gizmo + "\n")
    print("wrote " + GROUP_PATH)
    print("wrote " + GIZMO_PATH)


if __name__ == "__main__":
    save(build())
