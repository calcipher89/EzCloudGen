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

Up to three layers (sky decks or placed volumes), marched together by one BlinkScript per output
(colour, sun share, depth, shadow, motion), so where they overlap their clouds interleave.
Each layer also renders its own sun map, which shadows the other layers.
"""

import os
import sys

import nuke

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))
import cloud_types  # noqa: E402
import node_layout  # noqa: E402

VERSION = "0.56.0"
KERNEL = "EzCloudGen"
KERNEL_FILE = os.path.join(ROOT, "blink", KERNEL + ".blink")
GROUP_PATH = os.path.join(ROOT, "groups", "EzCloudGen_group.nk")
GIZMO_PATH = os.path.join(ROOT, "gizmos", "EzCloudGen.gizmo")
TYPE_NAMES = list(cloud_types.TYPES)
LAYER_DEFAULTS = [("Cumulus", True), ("Hero Cumulus", False), ("Cirrus", False)]

# Per layer knobs: (kernel param, label, tooltip, min, max). The first block is always shown;
# the rest are under "shape".
MAIN = [
    ("base", "base height", "Height of the cloud base above the ground, in metres.", 0, 12000),
    ("thickness", "thickness", "Depth of the layer, base to top, in metres.", 50, 6000),
    ("cover", "cover", "How much of the sky the layer hides, seen straight up: 0.3 is three tenths of the sky "
                       "covered. Calibrated per cloud type (the type's table turns it into the kernel's coverage), "
                       "so 0.5 looks half covered whatever the type. Thin types (fog, mist, cirrus) never hide all "
                       "of it: their 1 is their fullest. Tuning edge, erosion or wisps moves it a little.", 0, 1),
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
    ("sky_occlusion", "sky occlusion", "How much the cloud above darkens the sky light below it: deeper "
                                       "undersides and folds. Lower it for tall storms and thick overcast, "
                                       "which go flat grey under their own mass.", 0, 2),
    ("shadow_depth", "shadow depth", "How far light diffuses through the cloud. 0: it glows right through "
                                     "(soft, luminous shadows). 1: folds and cores stay dark (storms).", 0, 1),
    ("octaves", "detail octaves", "Detail levels (more is finer and slower).", 0, 5),
    ("billow", "billows", "1: billowy cauliflower detail. 0: soft wisps.", 0, 1),
    ("streaks", "streaks", "1: fibrous streaks (cirrus).", 0, 1),
    ("vary", "height variation", "How much the base and top move up and down across the deck.", 0, 0.5),
    ("shape_3d", "3D shape", "0: the shapes are drawn on the ground plan and run straight up through the layer, "
                             "so small shapes in a deep layer become tall columns (streaks when you look down "
                             "through them). 1: the shapes vary with height too, round blobs; for small puffs "
                             "or fog a camera flies through. Big, flat decks look the same either way.", 0, 1),
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
    ("turbulence", "turbulence", "A finer, second swirl (a third the size) that makes the edges roll and churn; "
                                 "animate 'evolve' to boil it.", 0, 1),
    ("crumble", "crumble", "Bites chunks out of the thin edges, for torn, ragged cloud and fog.", 0, 1),
    ("crumble_size", "crumble size", "Size of the chunks crumble bites out, in metres.", 5, 1000),
    ("shear", "wind shear", "Leans the tops downwind (along 'wind direction').", -1, 1),
    ("wisp_stretch", "wisp stretch", "Draws the fine detail (billows, wisps, grain and swirls) out along the "
                                     "wind ('wind direction') into filaments that follow the flow: 1 is round, "
                                     "4-10 gives streaks, for fog a camera flies through, combed mist or "
                                     "fibrous cirrus. The layer-scale shapes are set by 'stretch'.", 1, 12),
]
# A placed volume (types with volume on).
VOLUME = [
    ("lumps", "lumps", "Big rounded lobes that break the shape into towers and bulges (volumes and decks). "
                       "Cumulus keep a flat, ragged base under them.", 0, 1.5),
    ("lump_size", "lump size", "Size of the lumps, in metres.", 20, 5000),
    ("small_lumps", "small lumps", "A second set of lobes, a bit under half the size, riding on the lumps: "
                                   "cauliflower heads.", 0, 1),
    ("skirt", "skirt", "Smooth, firm billows on top and a wide, soft skirt of wisps around the base: it calms "
                       "the erosion higher up, and widens the edge and feeds the wisps low down.", 0, 2),
    ("fade_top", "fade top", "Eats the cloud away towards the top of its box, this far in (0..1 of the box): "
                             "the erosion tears the margin up. Fog that sits low and thins out above.", 0, 1),
    ("fade_bottom", "fade bottom", "The same towards the bottom of the box.", 0, 1),
    ("fade_left", "fade left", "The same towards the box's left side (local -X).", 0, 1),
    ("fade_right", "fade right", "The same towards the box's right side (local +X).", 0, 1),
    ("fade_front", "fade front", "The same towards the box's front (local +Z).", 0, 1),
    ("fade_back", "fade back", "The same towards the box's back (local -Z).", 0, 1),
]
VOL_SHAPES = ["Ellipsoid", "Dome", "Anvil", "Box", "Towers", "Shelf"]
# Knobs shown only for decks, and only for volumes.
DECK_ONLY = ["thickness", "scale_km", "stretch", "shape_3d", "taper", "top_round", "cells", "cell_km", "warp", "streaks", "vary",
             "map_amount", "map_channel", "map_use", "sil_distance", "sil_depth", "depth_ramp_on", "depth_ramp_shadows", "depth_ramp_falloff", "depth_ramp"]
MAP_CHANNELS = ["luminance", "red", "green", "blue", "alpha"]
VOL_ONLY = ["vol_divider", "vol_shape", "vol_position", "vol_rotate", "vol_size", "place", "place_km", "make_box",
            "release_box", "fade_top", "fade_bottom", "fade_left", "fade_right",
            "fade_front", "fade_back"]

LAYERS = {"cloud": ["red", "green", "blue", "alpha"],
          "cloud_sun": ["red", "green", "blue"],
          "cloud_sky": ["red", "green", "blue"],
          "cloud_shadow": ["red", "green", "blue"],
          "cloud_sunmap": ["red", "green", "blue"]}


def find(var, index, knob):
    """Python that sets `var` to the node in input `index` that has `knob`, through Dots or NoOps."""
    return ("%s = nuke.thisNode().input(%d)\n"
            "while %s is not None and not %s.knob('%s'):\n"
            "    %s = %s.input(0) if %s.inputs() else None\n" % (var, index, var, var, knob, var, var, var))


FIND_CAMERA = find("c", 1, "focal")
FIND_ATMOS = find("a", 2, "haze_density")
FIND_AXIS = find("x", 3, "world_matrix")
VIEWS = ["Comp", "Clouds", "Sun share", "Depth", "Variations", "Shadow"]
DEPTH_MODES = ["Planar Z", "1/Z (ScanlineRender)", "Distance"]


def py(code):
    return "[python -execlocal {%s}]" % code


def atmos_light(pixel, channel, fallback):
    """Python expression: one channel of the EzAtmosScatter's light. Pixel 1 is the sun
    (irradiance), 2 the sky (mean radiance; its hue from the cosine-weighted mean, pixel 3, when
    the atmos measures it). With an HDRI it is what the atmos measured in it.
    A self-lit atmos (no HDRI) has measured nothing: its sky is its own sky's mean (SelfLight),
    and its sun is its manual sun dimmed by the air it crosses on the way down (Kasten-Young
    air mass, the atmos's own Rayleigh and haze amounts, and from EzAtmosScatter 1.1 its ozone,
    whose white balance divides it out of 'sun color in use')."""
    i = ("red", "green", "blue").index(channel)
    return py(FIND_ATMOS +
              "ret = %s\n"
              "if a is not None:\n"
              "    selflit = a.knob('self_lit') is not None and a['self_lit'].value()\n"
              "    lnode = nuke.toNode(a.fullName() + ('.SelfLight' if selflit and %d == 2 else '.Light'))\n"
              "    if lnode is not None and not (selflit and %d == 1):\n"
              "        ret = lnode.sample('%s', %g, 0.5)\n"
              "        if %d == 2:\n"
              "            # The sky's hue from its cosine-weighted mean (EzAtmosScatter 1.2.1 pixel 3), at the\n"
              "            # plain mean's brightness: at a low sun the plain mean is warm from the bright\n"
              "            # horizon band, and thin cloud lit by it came out brown.\n"
              "            # Plain code: [python -execlocal] lambdas and comprehensions can't see its locals.\n"
              "            lc = 0.2126 * lnode.sample('red', 3.5, 0.5) + 0.7152 * lnode.sample('green', 3.5, 0.5) + 0.0722 * lnode.sample('blue', 3.5, 0.5)\n"
              "            lp = 0.2126 * lnode.sample('red', 2.5, 0.5) + 0.7152 * lnode.sample('green', 2.5, 0.5) + 0.0722 * lnode.sample('blue', 2.5, 0.5)\n"
              "            if lc > 1e-8:\n"
              "                ret = lnode.sample('%s', 3.5, 0.5) * lp / lc\n"
              "    elif selflit:\n"
              "        import math\n"
              "        sk = a['sun_in_use']\n"
              "        sx, sy, sz = sk.getValueAt(nuke.frame(), 0), sk.getValueAt(nuke.frame(), 1), sk.getValueAt(nuke.frame(), 2)\n"
              "        el = math.degrees(math.asin(max(min(sy / (math.sqrt(sx * sx + sy * sy + sz * sz) or 1.0), 1.0), -1.0)))\n"
              "        am = 1.0 / (math.sin(math.radians(max(el, 0.0))) + 0.50572 * (max(el, 0.0) + 6.07995) ** -1.6364)\n"
              "        hk = a['camera_height'].value() / 1000.0\n"
              "        tr = a['rayleigh_coefficients'].getValueAt(nuke.frame(), %d) * a['sky_amount'].value() * a['rayleigh_scale_height'].value() * math.exp(-hk / a['rayleigh_scale_height'].value())\n"
              "        tm = a['mie_coefficient'].value() / 0.9 * a['haze_amount'].value() * a['haze_height'].value() * math.exp(-hk / max(a['haze_height'].value(), 1e-3))\n"
              "        ck = a['sun_color_in_use'] if a.knob('sun_color_in_use') else a['sun_color']\n"
              "        tint = ck.getValueAt(nuke.frame(), %d) if ck.arraySize() > 1 and not ck.singleValue() else ck.getValueAt(nuke.frame(), 0)\n"
              "        oz = 0.0\n"
              "        if a.knob('ozone') is not None:\n"
              "            oz = (0.000650, 0.001881, 0.000085)[%d] * 15.0 * a['ozone'].value() / math.sqrt(math.sin(math.radians(max(el, 0.0))) ** 2 + 50.0 / a['planet_radius'].value())\n"
              "        ret = tint * a['manual_sun_brightness'].value() * a['sun_strength'].value() * math.exp(-(tr + tm) * am - oz) if el > -1 else 0.0\n"
              % (fallback, pixel, pixel, channel, pixel + 0.5, pixel, channel, i, i, i))


def layer_sun_tint(layer, channel):
    """Python expression: one channel of how much brighter (and less red) the sun is at the layer's
    height than at the atmos's camera height. The atmos light (self lit, or measured in an HDRI)
    is the sun as seen from the camera, through all the air above it. A cirrus at 9 km sees the
    sun through a third of that air and no haze: at a 2 degree sun about 3 times brighter and far
    less red, so it isn't lit by a deep red sun (which, with the blue sky light, read brown).
    The atmos's own Rayleigh and haze amounts and heights, Kasten-Young air mass at the sun's
    elevation. 1 with manual light or no atmos. Layer 0 is the cirrus sheet."""
    i = ("red", "green", "blue").index(channel)
    p = "l%d_" % layer if layer else "sheet_"
    return py(FIND_ATMOS +
              "ret = 1.0\n"
              "n = nuke.thisNode()\n"
              "if a is not None and n['light_source'].value():\n"
              "    import math\n"
              "    sk = a['sun_in_use']\n"
              "    sx, sy, sz = sk.getValueAt(nuke.frame(), 0), sk.getValueAt(nuke.frame(), 1), sk.getValueAt(nuke.frame(), 2)\n"
              "    el = max(math.degrees(math.asin(max(min(sy / (math.sqrt(sx * sx + sy * sy + sz * sz) or 1.0), 1.0), -1.0))), 0.0)\n"
              "    am = 1.0 / (math.sin(math.radians(el)) + 0.50572 * (el + 6.07995) ** -1.6364)\n"
              "    hc = a['camera_height'].value() / 1000.0\n"
              "    if n.knob('%(p)sheight') is not None:\n"
              "        hl = n['%(p)sheight'].value() / 1000.0\n"
              "    elif n['%(p)svolume'].value():\n"
              "        hl = (n['%(p)svol_position'].getValue(1) - n['ground_height'].value()) * n['scene_scale'].value() / 1000.0\n"
              "    else:\n"
              "        hl = (n['%(p)sbase'].value() + 0.5 * n['%(p)sthickness'].value()) / 1000.0\n"
              "    hl = max(hl, hc)\n"
              "    hr, hm = a['rayleigh_scale_height'].value(), max(a['haze_height'].value(), 1e-3)\n"
              "    br = a['rayleigh_coefficients'].getValueAt(nuke.frame(), %(i)d) * a['sky_amount'].value() * hr\n"
              "    bm = a['mie_coefficient'].value() / 0.9 * a['haze_amount'].value() * hm\n"
              "    d = br * (math.exp(-hc / hr) - math.exp(-hl / hr)) + bm * (math.exp(-hc / hm) - math.exp(-hl / hm))\n"
              "    ret = min(math.exp(d * am), 50.0)\n" % {"p": p, "i": i})


# ---- 3D box inputs ------------------------------------------------------------------------

# Inputs box1..box3 (5, 6, 7): any 3D node (a Cube, an Axis, a TransformGeo...) that a volume
# layer then fills. The code lives in a hidden knob of the node (no init.py), run by the
# expressions below. Plain Python with its own globals, so functions work.
BOX_INPUT = 4  # box N is input BOX_INPUT + N
BOX_LIB = r"""
import math


def find_box(n, idx):
    # The 3D transforms in the box input, outermost first: TransformGeos down to the geometry
    # (a Cube), or one Axis (its world_matrix already holds its parents). Dots pass through.
    chain = []
    b = n.input(idx)
    while b is not None:
        if b.knob('world_matrix') or b.knob('rot_order'):
            chain.append(b)
            if b.knob('world_matrix') or b.knob('cube'):
                break
        b = b.input(0) if b.maxInputs() else None
    return chain


def mul(a, c):
    r = [0.0] * 16
    for i in range(4):
        for j in range(4):
            r[i * 4 + j] = sum(a[i * 4 + k] * c[k * 4 + j] for k in range(4))
    return r


def rot(axis, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    if axis == 'X':
        return [1, 0, 0, 0, 0, c, -s, 0, 0, s, c, 0, 0, 0, 0, 1]
    if axis == 'Y':
        return [c, 0, s, 0, 0, 1, 0, 0, -s, 0, c, 0, 0, 0, 0, 1]
    return [c, -s, 0, 0, s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def local_matrix(b, f):
    # Translate, rotate (rot_order, first letter applied first), scale, in xform_order, about
    # the pivot: what Nuke's 3D transform knobs do.
    t = [b['translate'].getValueAt(f, i) for i in range(3)]
    r = [b['rotate'].getValueAt(f, i) for i in range(3)] if b.knob('rotate') else [0, 0, 0]
    u = b['uniform_scale'].getValueAt(f) if b.knob('uniform_scale') else 1.0
    sc = [b['scaling'].getValueAt(f, i) * u for i in range(3)] if b.knob('scaling') else [u, u, u]
    pv = [b['pivot'].getValueAt(f, i) for i in range(3)] if b.knob('pivot') else [0, 0, 0]
    T = [1, 0, 0, t[0], 0, 1, 0, t[1], 0, 0, 1, t[2], 0, 0, 0, 1]
    S = [sc[0], 0, 0, 0, 0, sc[1], 0, 0, 0, 0, sc[2], 0, 0, 0, 0, 1]
    R = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    for ax in (b['rot_order'].value() if b.knob('rot_order') else 'ZXY'):
        R = mul(rot(ax, r['XYZ'.index(ax)]), R)
    parts = {'S': S, 'R': R, 'T': T}
    P = [1, 0, 0, pv[0], 0, 1, 0, pv[1], 0, 0, 1, pv[2], 0, 0, 0, 1]
    Pi = [1, 0, 0, -pv[0], 0, 1, 0, -pv[1], 0, 0, 1, -pv[2], 0, 0, 0, 1]
    M = Pi
    for c in (b['xform_order'].value() if b.knob('xform_order') else 'SRT'):
        if c == 'T':
            M = mul(P, M)
        M = mul(parts[c], M)
    return M


def box_matrix(b, f):
    if b.knob('world_matrix'):
        return [b['world_matrix'].getValueAt(f, i) for i in range(16)]
    M = local_matrix(b, f)
    # A parent Axis on the node's axis input (a TransformGeo's input 1; a Cube has none).
    for i in range(1, b.maxInputs()):
        p = b.input(i)
        if p is not None and p.knob('world_matrix'):
            M = mul([p['world_matrix'].getValueAt(f, j) for j in range(16)], M)
            break
    return M


def box_value(n, idx, step, what):
    # what: found, center (3), axis_x/y/z (3, unit), size (3, metres). One float, index in what.
    chain = find_box(n, idx)
    if not chain:
        return 0.0
    if what == 'found':
        return 1.0
    name, i = what.rsplit(':', 1)
    i = int(i)
    M = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    for t in chain:
        M = mul(M, box_matrix(t, nuke.frame() + step))
    b = chain[-1]
    # The geometry's own extent: a Cube's 'cube' knob, else a unit cube about the origin.
    e = [b['cube'].value(j) for j in range(6)] if b.knob('cube') else [-0.5, -0.5, -0.5, 0.5, 0.5, 0.5]
    c = [(e[0] + e[3]) / 2.0, (e[1] + e[4]) / 2.0, (e[2] + e[5]) / 2.0]
    if name == 'center':
        return M[i * 4] * c[0] + M[i * 4 + 1] * c[1] + M[i * 4 + 2] * c[2] + M[i * 4 + 3]
    if name.startswith('axis'):
        j = 'xyz'.index(name[-1])
        col = [M[j], M[4 + j], M[8 + j]]
        l = math.sqrt(col[0] ** 2 + col[1] ** 2 + col[2] ** 2) or 1.0
        return col[i] / l
    if name == 'size':
        col = [M[i], M[4 + i], M[8 + i]]
        l = math.sqrt(col[0] ** 2 + col[1] ** 2 + col[2] ** 2)
        return l * abs(e[3 + i] - e[i]) * (n['scene_scale'].value() or 1.0)
    return 0.0
"""


SHAPE_LIB = r'''
HOLD_INPUT, ADD_INPUT, MAX_SHAPES = 8, 9, 32


def unit_matrix(b):
    # The unit shape (radius 1, half size 1, centred) to the primitive's own object space.
    c = b.Class()
    if c == 'Sphere':
        r = b['radius'].value()
        return [r, 0, 0, 0, 0, r, 0, 0, 0, 0, r, 0, 0, 0, 0, 1], 1.0
    if c == 'Cube':
        e = [b['cube'].value(j) for j in range(6)]
        h = [(e[3] - e[0]) / 2.0, (e[4] - e[1]) / 2.0, (e[5] - e[2]) / 2.0]
        m = [(e[3] + e[0]) / 2.0, (e[4] + e[1]) / 2.0, (e[5] + e[2]) / 2.0]
        return [h[0], 0, 0, m[0], 0, h[1], 0, m[1], 0, 0, h[2], m[2], 0, 0, 0, 1], 2.0
    r, hh = b['radius'].value(), b['height'].value() / 2.0
    return [r, 0, 0, 0, 0, hh, 0, 0, 0, 0, r, 0, 0, 0, 0, 1], 3.0


def collect(b, M, f, out):
    # Scenes and MergeGeos gather, TransformGeos move what is under them, Dots pass through.
    if b is None or len(out) >= MAX_SHAPES or (b.knob('disable') and b['disable'].value()):
        return
    c = b.Class()
    if c in ('Scene', 'MergeGeo', 'MergeGeo2'):
        for i in range(b.inputs()):
            collect(b.input(i), M, f, out)
    elif c in ('Dot', 'NoOp'):
        collect(b.input(0), M, f, out)
    elif c == 'TransformGeo':
        collect(b.input(0), mul(M, box_matrix(b, f)), f, out)
    elif c in ('Sphere', 'Cube', 'Cylinder'):
        U, t = unit_matrix(b)
        out.append((t, mul(mul(M, box_matrix(b, f)), U)))


def shapes(n, f):
    I = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    found = []
    for mode, idx in ((0.0, HOLD_INPUT), (1.0, ADD_INPUT)):
        got = []
        collect(n.input(idx), I, f, got)
        found += [(t, mode, M) for t, M in got]
    return found[:MAX_SHAPES]


def inverse(M):
    # An affine 4x4 (row major): the inverse of its 3x3, and of its translation.
    a = [M[0], M[1], M[2], M[4], M[5], M[6], M[8], M[9], M[10]]
    det = (a[0] * (a[4] * a[8] - a[5] * a[7]) - a[1] * (a[3] * a[8] - a[5] * a[6])
           + a[2] * (a[3] * a[7] - a[4] * a[6]))
    if abs(det) < 1e-12:
        return [0.0] * 12
    inv = [(a[4] * a[8] - a[5] * a[7]) / det, (a[2] * a[7] - a[1] * a[8]) / det, (a[1] * a[5] - a[2] * a[4]) / det,
           (a[5] * a[6] - a[3] * a[8]) / det, (a[0] * a[8] - a[2] * a[6]) / det, (a[2] * a[3] - a[0] * a[5]) / det,
           (a[3] * a[7] - a[4] * a[6]) / det, (a[1] * a[6] - a[0] * a[7]) / det, (a[0] * a[4] - a[1] * a[3]) / det]
    t = [M[3], M[7], M[11]]
    rows = []
    for r in range(3):
        rows += inv[r * 3:r * 3 + 3] + [-(inv[r * 3] * t[0] + inv[r * 3 + 1] * t[1] + inv[r * 3 + 2] * t[2])]
    return rows


# The shape table: one pass reads every shape for a node and frame (walking the 3D graph,
# combining transforms, inverting), and every knob value then looks it up. Any edit to a 3D
# node, a Scene's inputs or the node's own inputs starts a new table (see install).
_cache = {}
_state = {'edits': 0}


def table(n, f):
    key = (n.fullName(), f, _state['edits'])
    t = _cache.get(key)
    if t is None:
        ss = n['scene_scale'].value() or 1.0
        t = []
        for typ, mode, M in shapes(n, f):
            cols = [(M[c] ** 2 + M[4 + c] ** 2 + M[8 + c] ** 2) ** 0.5 for c in range(3)]
            t.append((inverse(M), (typ, mode, min(cols) * ss)))
        if len(_cache) > 512:
            _cache.clear()
        _cache[key] = t
    return t


def shape_value(n, slot, what):
    # what: count; or for shape slot: rN:j (its world-to-unit rows), info:0 type, info:1 mode,
    # info:2 metres per unit (its smallest size).
    t = table(n, nuke.frame())
    if what == 'count':
        return float(len(t))
    if slot >= len(t):
        return 0.0
    inv, info = t[slot]
    name, j = what.split(':')
    if name == 'info':
        return float(info[int(j)])
    return inv[int(name[1]) * 4 + int(j)]


def _edited():
    _state['edits'] += 1


def install():
    # Once per session: new tables after any edit of the nodes a shape can come through.
    for cls in ('Sphere', 'Cube', 'Cylinder', 'TransformGeo', 'Scene', 'MergeGeo', 'MergeGeo2', 'Axis', 'Axis2',
                'Axis3', 'Dot', 'NoOp', 'Group', 'Gizmo'):
        nuke.addKnobChanged(_edited, nodeClass=cls)
    return shape_value
'''


def shape_expr(slot, what):
    """Expression: one value from the shape table (see SHAPE_LIB). The library is loaded once per
    session, under a name that changes with its text. The count checks the inputs first (nothing
    plugged in: 0 without the table); every other value runs no Python at all unless its slot
    holds a shape ('shapes found' is past it), so unused slots cost a plain TCL test."""
    code = py("f = getattr(nuke, '_ezcg_shape_table_0e47c8aa', None)\n"
              "if f is None:\n"
              "    g = {'nuke': nuke}\n"
              "    exec(nuke.thisNode()['box_lib'].getText(), g)\n"
              "    exec(nuke.thisNode()['shape_lib'].getText(), g)\n"
              "    f = g['install']()\n"
              "    setattr(nuke, '_ezcg_shape_table_0e47c8aa', f)\n"
              "ret = f(nuke.thisNode(), %d, '%s')" % (slot, what))
    if what == "count":
        return code.replace("{f = getattr", "{ret = 0\nif nuke.thisNode().input(8) is not None or "
                            "nuke.thisNode().input(9) is not None:\n  f = getattr", 1).replace(
            "\nif f is None:\n    g = {'nuke': nuke}\n    exec(nuke.thisNode()['box_lib'].getText(), g)\n"
            "    exec(nuke.thisNode()['shape_lib'].getText(), g)\n    f = g['install']()\n"
            "    setattr(nuke, '_ezcg_shape_table_0e47c8aa', f)\nret = f(",
            "\n  if f is None:\n    g = {'nuke': nuke}\n    exec(nuke.thisNode()['box_lib'].getText(), g)\n"
            "    exec(nuke.thisNode()['shape_lib'].getText(), g)\n    f = g['install']()\n"
            "    setattr(nuke, '_ezcg_shape_table_0e47c8aa', f)\n  ret = f(")
    # TCL 'if' runs only the branch it takes, so an empty slot never reaches Python.
    return "[if {[value shape_count] > %d} {%s} {expr 0}]" % (slot, code[1:-1])


def box_expr(layer, what, step=0):
    """Expression: one value of the 3D node in layer's box input (see BOX_LIB)."""
    # getText, not value: an eval string knob's value() runs the text through TCL first.
    # Nothing plugged in: 0 at once, without running the library (these are read every frame).
    return py("ret = 0\n"
              "if nuke.thisNode().input(%d) is not None:\n"
              "    g = {'nuke': nuke}\n"
              "    exec(nuke.thisNode()['box_lib'].getText(), g)\n"
              "    ret = g['box_value'](nuke.thisNode(), %d, %d, '%s')"
              % (BOX_INPUT + layer, BOX_INPUT + layer, step, what))


# ---- The type menu ------------------------------------------------------------------------

# The render presets: what 'render preset' sets (see its help). Times are for the clouds of a
# 2400 x 1760 backlit cumulus shot on an RTX GPU.
RENDER_PRESETS = {
    "draft": {"resolution": "Half", "quality": 0.5, "edge_steps": 2.0, "sampling": "Low"},
    "shot": {"resolution": "Full", "quality": 1.0, "edge_steps": 3.0, "sampling": "Medium"},
    "hero": {"resolution": "Full", "quality": 1.0, "edge_steps": 3.0, "sampling": "High"},
}

# 'sampling': samples per pixel at an HD-wide plate (1920), scaled by 1920 / the plate's width, as
# a pixel's share of the frame (its grain and its stair-steps) shrinks with the resolution, and
# kept to 1 .. 16.
SAMPLING = ["Low", "Medium", "High", "Ultra", "Manual"]
SAMPLING_HD = [1, 2, 4, 8]
# The kernels' sample count (an expression inside the group, where the plate's format is known).
SAMPLES_EXPR = ("parent.preview ? 1 : parent.sampling == 4 ? max(1, parent.samples) : max(1, min(16, rint("
                "(parent.sampling == 0 ? %d : parent.sampling == 1 ? %d : parent.sampling == 2 ? %d : %d)"
                " * 1920 / max(FormatBox.width, 1))))" % tuple(SAMPLING_HD))


def knob_changed():
    # Plain top-level code: Nuke runs knob scripts with separate locals, which functions and
    # comprehensions can't see.
    table = dict((name, dict(cloud_types.full(name), cover=cloud_types.preset_cover(name),
                             cover_table=list(cloud_types.cover_table(name)))) for name in TYPE_NAMES)
    return ("RENDER_PRESETS = " + repr(RENDER_PRESETS) + "\n"
            "k = nuke.thisKnob()\n"
            "n = nuke.thisNode()\n"
            "layers = []\n"
            "if k.name() in ('l1_type', 'l2_type', 'l3_type'):\n"
            "    p = k.name()[:3]\n"
            "    t = %r\n"
            "    box = n.input(%d + int(p[1]))\n"
            "    box = box if box is not None and box.knob('scaling') else None\n"
            "    for key, v in t[k.value()].items():\n"
            "        if key == 'vol_size' and box is not None:\n"
            "            # A box plugged in: size the box instead.\n"
            "            s = n['scene_scale'].value() or 1.0\n"
            "            box['uniform_scale'].setValue(1)\n"
            "            box['scaling'].setValue([v[0] / s, v[1] / s, v[2] / s])\n"
            "        elif n.knob(p + key) is not None:\n"
            "            n[p + key].setValue(list(v) if isinstance(v, tuple) else v)\n"
            "    # A PyScript button can't be executed from inside knobChanged ('already executing'), so\n"
            "    # its code runs here. Every volume type re-places (base and distance come with the type),\n"
            "    # unless the position is animated or linked.\n"
            "    if n[p + 'volume'].value() > 0.5 and (box is not None or not n[p + 'vol_position'].isAnimated()):\n"
            "        exec(n[p + 'place'].value(), {'nuke': nuke})\n"
            "    layers = [p]\n"
            "elif k.name() == 'depth_channel':\n"
            "    # The knob gives short names; a Copy reads 'depth' as cutout.depth, not depth.Z.\n"
            "    c = {'depth': 'depth.Z'}.get(k.value(), k.value())\n"
            "    n.node('DepthEnsure')['channels'].setValue(c)\n"
            "    n.node('DepthSource')['from0'].setValue(c)\n"
            "elif k.name() == 'render_preset' and k.value() != 'custom':\n"
            "    for key, v in RENDER_PRESETS[k.value()].items():\n"
            "        n[key].setValue(v)\n"
            "elif k.name() in ('resolution', 'quality', 'edge_steps', 'sampling'):\n"
            "    pr = n['render_preset'].value()\n"
            "    if pr != 'custom' and n[k.name()].value() != RENDER_PRESETS[pr][k.name()]:\n"
            "        n['render_preset'].setValue('custom')\n"
            "if k.name() in ('sampling', 'showPanel'):\n"
            "    n['samples'].setEnabled(n['sampling'].value() == 'Manual')\n"
            "if k.name() in ('debug', 'showPanel'):\n"
            "    n['print_debug'].setVisible(bool(n['debug'].value()))\n"
            "    n['position_pass'].setVisible(bool(n['debug'].value()))\n"
            "# The ramp graphs' range isn't saved with the script: fit it to the values when the panel\n"
            "# opens or a ramp changes.\n"
            "if k.name() in ('showPanel', 'l1_depth_ramp', 'l2_depth_ramp', 'l3_depth_ramp'):\n"
            "    for i in (1, 2, 3):\n"
            "        kr = n.node('L%%d_DepthRamp' %% i)\n"
            "        if kr is not None:\n"
            "            top = max(kr['range'].value(3) * 1.25, 1000.0)\n"
            "            if k.name() == 'showPanel' or not (0.5 * kr['range'].max() < top <= kr['range'].max()):\n"
            "                kr['range'].setRange(0, top)\n"
            "if k.name() == 'showPanel':\n"
            "    layers = ['l1_', 'l2_', 'l3_']\n"
            "for p in layers:\n"
            "    vol = n[p + 'volume'].value() > 0.5\n"
            "    for name in %r:\n"
            "        n[p + name].setVisible(not vol)\n"
            "    for name in %r:\n"
            "        n[p + name].setVisible(vol)\n" % (table, BOX_INPUT, DECK_ONLY, VOL_ONLY) + EASY_DISPATCH)


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
            "pos = [m.getValue(3) + fx / l * d, n['ground_height'].value() + n['%sbase'].value() / s, "
            "m.getValue(11) + fz / l * d]\n"
            "box = n.input(%d)\n"
            "if box is not None and box.knob('translate') and box.knob('scaling'):\n"
            "    # A box plugged in: move the box (its centre is half its height above the base).\n"
            "    h = box['scaling'].value(1) * box['uniform_scale'].value()\n"
            "    box['translate'].setValue([pos[0], pos[1] + h / 2.0, pos[2]])\n"
            "else:\n"
            "    n['%svol_position'].setValue(pos)\n" % (p, p, BOX_INPUT + int(p[1]), p))


def make_box_script(p, layer):
    """'make 3D box': a Cube beside the node, placed and sized like the volume, plugged into the
    layer's box input. Move, rotate and scale it in the 3D viewer and the cloud follows."""
    return ("n = nuke.thisNode()\n"
            "p = '%s'\n"
            "idx = %d\n"
            "s = n['scene_scale'].value() or 1.0\n"
            "if n.input(idx) is None:\n"
            "    path = n.fullName().split('.')\n"
            "    ctx = nuke.toNode('.'.join(path[:-1])) if len(path) > 1 else nuke.root()\n"
            "    ctx.begin()\n"
            "    c = nuke.nodes.Cube(name=n.name() + '_L%d_Box')\n"
            "    ctx.end()\n"
            "    c.setXYpos(n.xpos() - 150, n.ypos() - 60 * %d)\n"
            "    pos = n[p + 'vol_position'].value()\n"
            "    size = n[p + 'vol_size'].value()\n"
            "    # The kernel turns the volume Y, then X, then Z.\n"
            "    c['rot_order'].setValue('YXZ')\n"
            "    c['translate'].setValue([pos[0], pos[1] + size[1] / s / 2.0, pos[2]])\n"
            "    c['rotate'].setValue(n[p + 'vol_rotate'].value())\n"
            "    c['scaling'].setValue([size[0] / s, size[1] / s, size[2] / s])\n"
            "    c['display'].setValue('wireframe')\n"
            "    c['render_mode'].setValue('off')\n"
            "    c['label'].setValue('cloud volume: ' + n.name() + ' layer %d')\n"
            "    c['tile_color'].setValue(0x8fb3d9ff)\n"
            "    n.setInput(idx, c)\n"
            % (p, BOX_INPUT + layer, layer, layer - 1, layer))


def release_box_script(p, layer):
    """'release box': unplugs the box; the volume keeps where the box put it."""
    return ("n = nuke.thisNode()\n"
            "p = '%s'\n"
            "import math\n"
            "if n[p + 'box_found'].value() > 0.5:\n"
            "    s = n['scene_scale'].value() or 1.0\n"
            "    c = n[p + 'box_center'].value()\n"
            "    size = n[p + 'box_size'].value()\n"
            "    ax = n[p + 'box_axis_x'].value()\n"
            "    ay = n[p + 'box_axis_y'].value()\n"
            "    az = n[p + 'box_axis_z'].value()\n"
            "    # The kernel's R = Rz Rx Ry: axis_y = (-sin z cos x, cos z cos x, sin x), and so on.\n"
            "    rx = math.degrees(math.asin(max(-1.0, min(1.0, ay[2]))))\n"
            "    rz = math.degrees(math.atan2(-ay[0], ay[1]))\n"
            "    ry = math.degrees(math.atan2(-ax[2], az[2]))\n"
            "    n[p + 'vol_rotate'].setValue([rx, ry, rz])\n"
            "    n[p + 'vol_size'].setValue(list(size))\n"
            "    n[p + 'vol_position'].setValue([c[0], c[1] - size[1] / s / 2.0, c[2]])\n"
            "n.setInput(%d, None)\n" % (p, BOX_INPUT + layer))


# The variations buttons: the layer is 'variations of'.
VARIATIONS_LAYER = ("n = nuke.thisNode()\n"
                    "p = 'l%d_' % (int(n['variations_of'].getValue()) + 1)\n")
VARIATIONS_SHOW = VARIATIONS_LAYER + "n[p + 'enable'].setValue(True)\nn['view'].setValue('Variations')\n"
VARIATIONS_NEXT = (VARIATIONS_LAYER + "n[p + 'seed'].setValue(n[p + 'seed'].value() + 9)\n"
                   "n['view'].setValue('Variations')\n")
VARIATIONS_USE = (VARIATIONS_LAYER + "k = min(max(int(n['variation_pick'].value()), 1), 9)\n"
                  "n[p + 'seed'].setValue(n[p + 'seed'].value() + k - 1)\n"
                  "n['view'].setValue('Comp')\n")
VARIATIONS_AIM = (
    "import math\n"
    "n = nuke.thisNode()\n"
    "M = [n['cam_world_matrix'].getValue(i) for i in range(16)]\n"
    "R = [M[0], M[1], M[2], M[4], M[5], M[6], M[8], M[9], M[10]]\n"
    "p = 'l%d_' % (int(n['variations_of'].getValue()) + 1)\n"
    "if not n[p + 'volume'].value():\n"
    "    b = n.input(0)\n"
    "    fm = b.format() if b is not None else nuke.root().format()\n"
    "    vap = n['cam_haperture'].value() * fm.height() / (fm.width() * (fm.pixelAspect() or 1.0))\n"
    "    t = 0.3 * vap / max(n['cam_focal'].value(), 1e-6)\n"
    "    alt = (M[7] - n['ground_height'].value()) * (n['scene_scale'].value() or 0.1)\n"
    "    lo = n[p + 'base'].value()\n"
    "    hi = lo + n[p + 'thickness'].value()\n"
    "    a = math.atan(t) if alt < lo else (-math.atan(t) if alt > hi else 0.0)\n"
    "    hx, hz = -M[2], -M[10]\n"
    "    l = math.hypot(hx, hz)\n"
    "    hx, hz = (hx / l, hz / l) if l > 1e-6 else (0.0, -1.0)\n"
    "    fw = [hx * math.cos(a), math.sin(a), hz * math.cos(a)]\n"
    "    rt = [-hz, 0.0, hx]\n"
    "    up = [rt[1] * fw[2] - rt[2] * fw[1], rt[2] * fw[0] - rt[0] * fw[2], rt[0] * fw[1] - rt[1] * fw[0]]\n"
    "    R = [rt[0], up[0], -fw[0], rt[1], up[1], -fw[1], rt[2], up[2], -fw[2]]\n")


# ---- Knobs --------------------------------------------------------------------------------

def add(g, knob, tooltip=None, flags=()):
    if tooltip:
        knob.setTooltip(tooltip)
    for f in flags:
        knob.setFlag(f)
    g.addKnob(knob)
    return knob


# The Easy tab (python/easy_mode.py does the work): (knob, label, min, max, neutral, tooltip).
EASY = [
    ("easy_cover", "cover", -1, 1, 0.0, "More or less of the sky covered (adds to the layer's 'cover')."),
    ("easy_size", "size", 0.25, 4, 1.0, "Bigger or smaller clouds: the shapes, cells and lumps, and a little the billows."),
    ("easy_softness", "softness", -1, 1, 0.0, "Softer, thinner, more veil-like edges (up) or harder, denser ones (down)."),
    ("easy_wisps", "wisps", -1, 1, 0.0, "More fine wisps eating into the edges, combed along the wind (up), or fewer."),
    ("easy_underside", "underside", -1, 1, 0.0, "Darker, deeper undersides and folds (up), or lighter, glowing ones (down)."),
    ("easy_lit", "lit", -2, 2, 0.0, "Brightness of the sunlit side, in stops (the node's 'sun intensity', every layer)."),
]


def easy_code():
    """python/easy_mode.py, base64-encoded for the hidden tool_code knob."""
    import base64
    with open(os.path.join(ROOT, "python", "easy_mode.py")) as f:
        return base64.b64encode(f.read().encode()).decode()


def add_easy_tab(g):
    add(g, nuke.Tab_Knob("easy_tab", "Easy"))
    add(g, nuke.Text_Knob("easy_intro", "", "A few big sliders over one layer's knobs. They start from the layer as it is; "
                                            "the layer tab shows what they changed. Editing a layer knob by hand starts "
                                            "them again from there."))
    add(g, nuke.Enumeration_Knob("easy_layer", "easy layer", ["Layer 1", "Layer 2", "Layer 3", "Cirrus sheet"]),
        "The layer the sliders work on. Each layer keeps its own slider settings. On the cirrus sheet: cover, "
        "size (patches and fibres), softness (softer, fainter edges and a thinner sheet), wisps (more fibre) "
        "and underside (a darker sky-lit side).")
    for name, label, lo, hi, neutral, tip in EASY:
        k = add(g, nuke.Double_Knob(name, label), tip)
        k.setRange(lo, hi)
        k.setValue(neutral)
    add(g, nuke.Enumeration_Knob("easy_look", "starting look", ["Aerial Day", "Aerial Sunset"]),
        "A starting point for a kind of shot, on layer 1. Aerial Sunset: a camera high above the valleys "
        "toward a low sun; layer 1 off (no cloud), its base moved 1900 m above the camera for when you turn it on. "
        "Aerial Day: a fair-weather day from high above; layer 1 on, its base 1700 m above the camera. Pair it with EzAtmosScatter's "
        "and EzDepthHaze's Aerial Sunset looks (EzMatch's 'apply starting look' sets all three), then match all.")
    add(g, nuke.PyScript_Knob("apply_easy_look", "apply look",
                              "_n = nuke.thisNode()\n_ez = {}\n"
                              "exec(__import__('base64').b64decode(_n['tool_code'].value()).decode(), _ez)\n"
                              "_ez['apply_look'](_n)\n"),
        "Sets the starting look's layer 1 knobs and centres the Easy sliders on layer 1.")
    hidden(g, nuke.String_Knob("easy_base", "easy base"))
    hidden(g, nuke.String_Knob("tool_code", "tool code")).setValue(easy_code())


# knobChanged, last: hand the Easy knobs and the layer knobs they write to python/easy_mode.py.
EASY_DISPATCH = ("if n.knob('tool_code') is not None and not getattr(nuke, '_ezcloudgen_busy', False):\n"
                 "    _kn = k.name()\n"
                 "    if _kn.startswith('easy_') or _kn == 'sun_intensity' or _kn[:3] in ('l1_', 'l2_', 'l3_') or _kn.startswith('sheet_'):\n"
                 "        _ez = {}\n"
                 "        exec(__import__('base64').b64decode(n['tool_code'].value()).decode(), _ez)\n"
                 "        _ez['on_knob'](n, _kn)\n")


# The cirrus sheet (blink/EzCirrusSheet.blink): (name, label, default, lo, hi, tooltip).
SHEET = [
    ("height", "height", 9000.0, 4000, 14000, "The sheet's height above the ground, in metres."),
    ("cover", "cover", 0.5, 0, 1, "How much of the sky the sheet covers: 0 none, 0.5 about half, 1 all of it."),
    ("scale_km", "patch size", 4.0, 0.5, 30, "The size of the sheet's patches and gaps, in km."),
    ("edge", "edge softness", 0.6, 0, 2, "How softly the patches fade out at their edges."),
    ("opacity", "opacity", 0.5, 0, 2, "How much the sheet hides looking straight up (it thickens towards the horizon)."),
    ("fibres", "fibres", 0.8, 0, 1, "How much of the sheet is long strands rather than an even veil."),
    ("fibre_size", "fibre width", 150.0, 20, 1000, "The width of the strands, in metres."),
    ("fibre_length", "fibre length", 20.0, 2, 80, "How many times longer the strands are than they are wide."),
    ("direction", "direction", 35.0, -180, 180, "The way the strands and patches run, in degrees from north (-z) towards +x."),
    ("wind_speed", "wind speed", 15.0, 0, 80, "How fast the sheet drifts along its strands, in m/s."),
    ("forward", "forward scatter", 0.35, 0, 0.95, "How much light the sheet throws forward: its glow around the sun."),
    ("ambient", "sky light", 1.0, 0, 3, "How much sky light the sheet takes: its brightness on the side away from the sun."),
    ("seed", "seed", 0.0, 0, 100, "Another sheet of the same kind."),
]


def add_sheet_tab(g):
    add(g, nuke.Tab_Knob("sheet_tab", "Cirrus sheet"))
    add(g, nuke.Text_Knob("sheet_intro", "", "A thin sheet of fibrous high cloud: one quick pass of its own, drawn "
                                             "behind the layers. For cirrus and cirrostratus veils."))
    add(g, nuke.Boolean_Knob("sheet_enable", "enable"), "Draw the cirrus sheet.").setValue(False)
    for name, label, val, lo, hi, tip in SHEET:
        k = add(g, nuke.Double_Knob("sheet_" + name, label), tip)
        k.setRange(lo, hi)
        k.setValue(val)
    k = hidden(g, nuke.Color_Knob("sheet_sun_tint", "sun tint"))
    for j, ch in enumerate(("red", "green", "blue")):
        k.setExpression(layer_sun_tint(0, ch), j)


def hidden(g, knob):
    knob.setFlag(nuke.INVISIBLE)
    g.addKnob(knob)
    return knob


# 'analyze scene': python/analyze_lib.py, stored in the hidden 'analyze_lib' knob.
ANALYZE_LIB = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "analyze_lib.py")).read()
DEBUG_BUTTON = ("g = {'nuke': nuke}\n"
                "exec(nuke.thisNode()['analyze_lib'].getText(), g)\n"
                "g['debug_report'](nuke.thisNode())\n")
ANALYZE_BUTTON = ("g = {'nuke': nuke}\n"
                  "exec(nuke.thisNode()['analyze_lib'].getText(), g)\n"
                  "g['analyze'](nuke.thisNode())\n")


def build_knobs(g):
    add(g, nuke.Tab_Knob("ezcloudgen", "EzCloudGen"))
    add(g, nuke.PyScript_Knob("analyze", "analyze scene", ANALYZE_BUTTON),
        "Sets the node up from its inputs at this frame: finds the bg's depth channel and whether it is "
        "Planar Z or 1/Z, where the sky starts in it ('sky beyond'), the ground height under the camera "
        "(the lowest ground the depth shows), turns on 'hide behind bg', raises 'max distance' to reach "
        "the terrain, and moves any placed volume that is behind the camera, out of frame or behind the "
        "terrain to in front of the camera. It reads the depth as numbers on a 32 x 18 grid; no picture "
        "leaves the node. Then it lists what it found and changed, and what to check by hand (units, "
        "the sun). One undo reverts it. Press it again after changing the camera or 'units to metres'.")
    add(g, nuke.Text_Knob("analysis", "", "Plug in bg (with depth), camera and sun, then press 'analyze scene'."))
    v = add(g, nuke.Enumeration_Knob("view", "view", VIEWS),
            "Comp: the clouds over 'bg' (or alone without it). Clouds: the clouds alone, premultiplied. "
            "Sun share: the direct sunlight part of the clouds. Depth: Planar Z of the clouds, scene units. "
            "Variations: nine seeds of one layer side by side over a plain sky, numbered (see 'variations'). "
            "Shadow: the clouds' shadows on the bg (needs its depth), white is shaded.")
    v.setValue("Comp")
    add(g, nuke.Boolean_Knob("preview", "preview"),
        "Fast look-dev: half the resolution and the ray march steps, one sample, and only the passes the "
        "view needs (no sun share, shadows or motion vectors, so those layers are black). Turn it off for "
        "the real thing; the node's label says PREVIEW while it is on.")
    add(g, nuke.Boolean_Knob("breakout", "breakout layers"),
        "Adds the layers cloud (rgba), cloud_sun and cloud_sky (rgb), for re-grading the clouds over the "
        "plate, and cloud_shadow (rgb, the shadows on the bg; needs its depth). Takes extra passes per "
        "layer.").setValue(True)
    add(g, nuke.Boolean_Knob("motion_vectors", "motion vectors"),
        "Adds forward (u, v) and backward (u, v) motion vectors of the clouds, in pixels, for VectorBlur "
        "or a motion blur in comp. They follow the camera, the wind drift and moving 3D boxes. Takes two "
        "more (cheap) passes per layer.")
    g["motion_vectors"].clearFlag(nuke.STARTLINE)
    add(g, nuke.Boolean_Knob("motion_blur", "motion blur"),
        "True 3D motion blur, rendered in: each sample sees the shot at its own moment inside the shutter, "
        "with the camera moved and turned and every layer drifted on the wind (or moved with its box) that "
        "far, so parallax, a turning camera and clouds at different depths blur correctly, which a 2D "
        "VectorBlur can't do. It needs samples to be smooth: use 'sampling' High or Ultra (or Manual 8 to "
        "16); with few it is grainy. Motion comes from the next frame, so a move that changes direction "
        "within a frame is straightened. The lighting is the frame's own.")
    add(g, nuke.Double_Knob("shutter", "shutter"),
        "How long the shutter is open, in frames, centred on the frame (0.5 = a 180 degree shutter).").setValue(0.5)
    g["shutter"].setRange(0, 1)
    g["shutter"].clearFlag(nuke.STARTLINE)
    add(g, nuke.Enumeration_Knob("render_preset", "render preset", ["custom", "draft", "shot", "hero"]),
        "Sets resolution, quality, edge steps and samples together. draft: half resolution, half the steps, "
        "one sample (fast look-dev, grainy edges; about a sixth of hero's time). shot: full resolution, two "
        "samples (clean surfaces, a little grain on thin edges; about 70% of hero's time). hero: four "
        "samples (clean edges; for close-ups and stills). Changing any of the four by hand makes it custom. "
        "custom: as set below.").setValue("shot")
    r = add(g, nuke.Enumeration_Knob("resolution", "resolution", ["Full", "Half", "Quarter"]),
            "Render the clouds smaller and scale them back up: much faster, softer.")
    r.setValue("Full")
    add(g, nuke.Double_Knob("quality", "quality"),
        "Ray march step count: higher is smoother and slower.").setValue(1.0)
    g["quality"].setRange(0.25, 4)
    add(g, nuke.Double_Knob("edge_steps", "edge steps"),
        "Finer ray steps where a ray meets cloud (this many to a normal step): clean, grain-free "
        "surfaces and edges. 1: off (faster, grainy). The preview uses 1.").setValue(3)
    g["edge_steps"].setRange(1, 6)
    s = add(g, nuke.Enumeration_Knob("sampling", "sampling", SAMPLING),
            "How many jittered samples each pixel takes (anti-aliasing and less grain), worked out from the "
            "plate's resolution so it needn't be guessed: Low, Medium, High and Ultra take 1, 2, 4 and 8 on an "
            "HD-wide plate (1920), fewer on a bigger plate and more on a smaller one, where each pixel is a "
            "bigger share of the frame (2 to 16 on a 960 preview; on a 4K plate Medium is 1). The cost is "
            "about proportional: High takes twice Medium's time. Manual: takes 'samples' per pixel, as many "
            "as you set, whatever the plate.")
    s.setValue("Medium")
    k = add(g, nuke.Int_Knob("samples", "samples"),
            "With sampling on Manual: the samples per pixel, as many as you like (the cost grows with them).")
    k.setValue(8)
    k.setEnabled(False)
    k.clearFlag(nuke.STARTLINE)
    add(g, nuke.Double_Knob("max_distance", "max distance"),
        "Clouds fade out towards this distance (km). The default reaches past the horizon from high up.").setValue(400)
    g["max_distance"].setRange(5, 500)


    add(g, nuke.Text_Knob("scene_divider", "scene"))
    add(g, nuke.Double_Knob("scene_scale", "units to metres"),
        "Scene units to metres: 0.1 for decimetres.").setValue(0.1)
    add(g, nuke.Double_Knob("ground_height", "ground height"),
        "Height of the ground in scene units; the camera's height above it places it under the clouds."
        ).setValue(0)
    g["ground_height"].setRange(-10000, 10000)
    add(g, nuke.Enumeration_Knob("earth", "earth", ["Flat", "Curved"]),
        "Flat: the ground is a plane pinned to the world, so a moving camera can climb, dive and fly "
        "through the decks and the clouds keep their shape out to the horizon. Curved: the real earth, "
        "its top at the scene origin; from high up the far decks sink behind the true horizon.")

    add(g, nuke.Text_Knob("bg_depth_divider", "bg depth"))
    add(g, nuke.Boolean_Knob("occlude", "hide behind bg"),
        "Uses the bg's depth so the clouds go behind mountains and buildings, and casts their shadows "
        "onto it (cloud_shadow, and the Shadow view). Without a depth channel on the bg, nothing is "
        "hidden.").setValue(True)
    k = add(g, nuke.Double_Knob("bg_edge_softness", "edge softness"),
            "Feathers where the clouds meet the bg's outline (a ridge, a tree line, a building), in pixels of "
            "the plate: each pixel reads the bg's depth at 12 points over a disc this wide, and the clouds fade "
            "by how much of it is in front of them, a smooth, anti-aliased holdout (no grain). With motion blur "
            "each sample jitters its lookup over the disc instead. 0: the pixel's own depth, a hard cut.")
    k.setRange(0, 20)
    k.clearFlag(nuke.STARTLINE)
    k = add(g, nuke.Double_Knob("ground_softness", "ground softness"),
            "Where the clouds meet the bg's surface (fog lying on a valley floor, a deck crossing a "
            "mountainside), they thin out over this many metres of height above it, so they settle onto "
            "the terrain instead of stopping in a hard line, near or far. Needs the bg's depth and "
            "'hide behind bg'. 0: a hard cut.")
    k.setRange(0, 500)
    k.setValue(50)
    c = add(g, nuke.Channel_Knob("depth_channel", "depth"), "The bg channel holding its depth.")
    c.setValue("depth.Z")
    add(g, nuke.Enumeration_Knob("depth_out", "depth out", ["comp", "clouds only"]),
        "What the output's depth.Z holds. comp: the clouds' depth where they are solid (alpha 0.5 and "
        "over), the bg's depth everywhere else, so land under clear sky keeps its depth for the tools "
        "after this one. clouds only: the clouds' depth alone, 0 elsewhere (as before 0.54). The clouds' "
        "depth is Planar Z in scene units; with 'comp' the bg's depth passes as it came in.").setValue(0)
    m = add(g, nuke.Enumeration_Knob("depth_mode", "depth is", DEPTH_MODES),
            "Planar Z: distance along the camera's view axis (Arnold, Karma, V-Ray Z). "
            "1/Z: Nuke's ScanlineRender. Distance: from the camera to the point.")
    m.clearFlag(nuke.STARTLINE)
    add(g, nuke.Double_Knob("sky_depth", "sky beyond"),
        "Depth beyond this (km) is sky, like a far sky dome, so it hides nothing. A depth of 0 is "
        "always sky.").setValue(50)
    g["sky_depth"].setRange(1, 500)
    add(g, nuke.Double_Knob("shadow_amount", "shadow amount"),
        "How much the shadows darken the bg in the Comp view. The cloud_shadow layer is always the "
        "full shadow, for grading the plate yourself.").setValue(0.6)
    add(g, nuke.Boolean_Knob("layer_shadows", "layers shadow each other"),
        "A layer shades the sunlit side of the clouds below it in the other layers (a map of its "
        "shadow seen from the sun, one small pass per layer).").setValue(True)
    add(g, nuke.Boolean_Knob("sun_map_out", "sun shadow layer"),
        "Adds the cloud_sunmap layer (with 'breakout layers'): all the layers' shadow seen from the sun. "
        "EzCloudShafts reads it from its clouds input and casts its rays and ground shadows from the real "
        "cloud volumes, tall ones and ones outside the frame included.").setValue(True)
    hidden(g, nuke.Double_Knob("sun_map_size")).setValue(SUN_MAP_SIZE)

    add(g, nuke.Tab_Knob("light_tab", "Light"))
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
    c.setValue([9.0, 8.5, 7.6])
    c = add(g, nuke.Color_Knob("sky_color", "sky color"), "Sky light (radiance) when the light is Manual.")
    c.setValue([0.2, 0.32, 0.6])
    c = add(g, nuke.Color_Knob("ground_color", "ground bounce"), "Light bounced up from the ground onto the cloud bases.")
    c.setValue([0.08, 0.07, 0.06])
    add(g, nuke.Double_Knob("sun_intensity", "sun intensity"), "Multiplies the sunlight.").setValue(1.0)
    add(g, nuke.Double_Knob("sky_intensity", "sky intensity"), "Multiplies the sky light.").setValue(1.0)
    add(g, nuke.Double_Knob("exposure", "exposure"),
        "Brightens or darkens the clouds, in stops (rgba and the cloud layers; not the bg).").setValue(0)
    g["exposure"].setRange(-4, 4)
    add(g, nuke.Double_Knob("highlight_rolloff", "highlight rolloff"),
        "Rolls the clouds' highlights off towards 1 instead of letting them run past it: sunlit tops seen "
        "towards the sun are several times brighter than the bodies and blow out in a plain sRGB view. "
        "0: off (linear, as rendered). 0.5: the top half of the range is compressed. The hue is kept.").setValue(0)
    g["highlight_rolloff"].setRange(0, 1)
    add(g, nuke.Double_Knob("sun_glow", "sun glow"),
        "The blaze of thin cloud in front of the sun: adds the narrow forward peak real cloud droplets "
        "have, so backlit edges and veils near the sun glow hot while the thick cores stay dark. "
        "0: off. 0.3 to 1 for shots into the sun (use 'highlight rolloff' with it).").setValue(0)
    g["sun_glow"].setRange(0, 2)
    add(g, nuke.Double_Knob("diffusion", "light diffusion"),
        "How the sunlight spreads inside the clouds. 0: the older, darker look. 1: as in thick real "
        "cloud, where light scattered many times fades slowly with depth: sunlit sides go bright white, "
        "billows shade off gradually round their sides and cores stay luminous grey instead of dead. "
        "Use 'highlight rolloff' with it.").setValue(0)
    g["diffusion"].setRange(0, 1)
    add(g, nuke.Double_Knob("wrap_light", "wrap light"),
        "With 'light diffusion': the light scattered inside a cloud keeps going mostly forward, so looking "
        "towards the sun the edges and thinner cloud within about 30 degrees of it glow and the light wraps "
        "round the outline, as in a backlit photo; side on and from behind the sun, a cloud is a touch "
        "darker. 0: as before.").setValue(1)
    g["wrap_light"].setRange(0, 1.5)
    c = add(g, nuke.Color_Knob("forward_warmth", "forward warmth"),
            "Tints only the light the clouds send forward towards the camera near the sun (the glow of lit "
            "undersides and edges, from 'forward scatter', 'sun glow' and 'wrap light'), not the evenly spread "
            "light of the shaded tops, so at sunset the undersides can glow warm while the tops stay neutral "
            "grey. White: as before.")
    c.setValue([1.0, 1.0, 1.0])
    add(g, nuke.Boolean_Knob("forward_warmth_from_atmos", "warmth from atmos"),
        "Multiplies 'forward warmth' by the colour the atmos's white balance took out of its sun (its "
        "'sun color' over 'sun color in use', at the same brightness): the lit undersides keep the sun's "
        "real colour while the rest of the cloud is white balanced. Needs a self-lit EzAtmosScatter.").setValue(False)
    k = hidden(g, nuke.Color_Knob("forward_warmth_in_use"))
    for i, ch in enumerate("rgb"):
        k.setExpression(py(FIND_ATMOS +
                           "f = nuke.thisNode()\n"
                           "ret = f['forward_warmth'].value(%d)\n"
                           "if f['forward_warmth_from_atmos'].value() and a is not None and a.knob('sun_color_in_use') is not None:\n"
                           "    raw = a['sun_color']\n"
                           "    bal = a['sun_color_in_use']\n"
                           "    r0 = raw.value(0) / max(bal.value(0), 1e-6)\n"
                           "    r1 = raw.value(1) / max(bal.value(1), 1e-6)\n"
                           "    r2 = raw.value(2) / max(bal.value(2), 1e-6)\n"
                           "    lum = 0.2126 * r0 + 0.7152 * r1 + 0.0722 * r2\n"
                           "    ret = ret * (r0, r1, r2)[%d] / max(lum, 1e-6)\n" % (i, i)), i)
    add(g, nuke.Text_Knob("look_divider", "look"))
    add(g, nuke.Double_Knob("detail_sharpness", "detail sharpness"),
        "Crisper billows: keeps more of the finer detail octaves and hardens the cloud's surface, for the "
        "sharp cauliflower edges of a sunlit cumulus. 0: softer. Raise 'quality' or 'edge steps' if it "
        "starts to sparkle.").setValue(0.6)
    g["detail_sharpness"].setRange(0, 1)
    add(g, nuke.Double_Knob("billow_light", "billow light"),
        "Lights each billow on its own: the light march looks a billow towards the sun with all the fine "
        "detail, so every cauliflower lobe gets a bright sunlit side and a shaded far side, and the creases "
        "between lobes go dark, as in a photographed cumulus. 0: billows light flat (it takes one more "
        "detailed cloud lookup per lit step, about 3% of the render time).").setValue(1)
    g["billow_light"].setRange(0, 1)
    add(g, nuke.Double_Knob("billow_shrink", "billow shrink"),
        "Big, soft lobes low in the cloud and smaller, tighter cauliflower towards the top, as real cumulus "
        "grow. 0: the same billow size all the way up (as before).").setValue(0)
    g["billow_shrink"].setRange(0, 1)
    add(g, nuke.Boolean_Knob("light_grid", "light grid"),
        "Bakes every layer's shadow from the sun once, on a grid fitted to the camera's view, and lights the "
        "clouds from it: smooth, noise-free self-shadowing through the whole mass and between the layers. "
        "The fine detail still shades itself close up. Off: each sample marches towards the sun on its own "
        "(as before).").setValue(True)
    add(g, nuke.Double_Knob("even_detail", "even detail"),
        "Makes the billows, wisps and edges the same depth all over a cloud: they are scaled by how steeply "
        "the cloud's shape rises at each point, so the shape acts as a distance to its surface. Without it, "
        "gently sloping faces (a big swell, a painted mass's front, a deck's broad tops) come out smooth and "
        "steep ones crumbled. Costs up to about 70% more render time. 0: as before.").setValue(1)
    g["even_detail"].setRange(0, 1)
    add(g, nuke.Int_Knob("horizon_samples", "horizon samples"),
        "Near the horizon a deck is seen edge on and its clouds shrink below a pixel, so they shimmer and crawl "
        "on a camera move. This takes that many times the samples in the band within a few degrees of level "
        "(only there, so it costs little). 1: as before.").setValue(4)
    add(g, nuke.Double_Knob("sky_shading", "sky shading"),
        "Lights the clouds with the sky from all round, not only from overhead: a lobe's open face takes the "
        "full sky and the folds between lobes little, so the shadow side of a cloud keeps its form and takes "
        "the sky's colour instead of going one flat grey. 0: as before.").setValue(1)
    g["sky_shading"].setRange(0, 1)
    add(g, nuke.Double_Knob("round_lobes", "round lobes"),
        "Rounds the big lobes ('lumps'): their cells are bent and their seams softened, so a cloud is a pile "
        "of rounded heads with soft folds between them instead of domes meeting along straight, faceted "
        "seams. 0: as before.").setValue(1)
    g["round_lobes"].setRange(0, 1)

    add(g, nuke.Tab_Knob("more_tab", "Air, time & map"))
    add(g, nuke.Text_Knob("haze_divider", "air"))
    add(g, nuke.Double_Knob("haze_distance", "haze distance"),
        "Distance (km) over which far clouds fade into the haze colour. 0: off.").setValue(60)
    g["haze_distance"].setRange(0, 200)
    add(g, nuke.Double_Knob("horizon_haze", "horizon haze"),
        "Lays the haze over the far ground too (thick at the horizon, thinning towards the camera), so the "
        "decks sink into haze there instead of ending on a straight line when the plate has no ground. "
        "Where the bg has depth, its terrain is the ground and this does nothing there. "
        "0: off (for a plate with its own ground and no depth).").setValue(1)
    g["horizon_haze"].setRange(0, 1)
    c = add(g, nuke.Color_Knob("haze_color", "haze color"),
            "Colour far clouds fade to. With the light from an atmos it multiplies the atmos's sky colour; "
            "with Manual light it's tinted half way towards the sky colour's hue.")
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

    add(g, nuke.Text_Knob("shapes_divider", "shapes"))
    add(g, nuke.Text_Knob("shapes_help", "", "Plug a Scene of Spheres, Cubes and Cylinders (or one) into "
        "<b>holdout</b> to carve cloud away, or into <b>add</b> to grow it. Up to 32 shapes."))
    k = add(g, nuke.Double_Knob("shape_softness", "shape softness"),
            "How far the shapes' edges feather into the cloud, in metres, either side of their surface. "
            "The cloud's own detail then breaks the edge up.")
    k.setValue(50)
    k.setRange(1, 1000)
    k = add(g, nuke.Double_Knob("holdout_amount", "holdout"), "How completely the holdout shapes clear the cloud.")
    k.setValue(1)
    k.setRange(0, 1)
    k = add(g, nuke.Double_Knob("add_amount", "add"), "How much cloud the add shapes grow (up to solid at 1).")
    k.setValue(1)
    k.setRange(0, 2)
    k.clearFlag(nuke.STARTLINE)
    k = add(g, nuke.Int_Knob("shape_count", "shapes found"), "Shapes read from the holdout and add inputs.")
    k.setExpression(shape_expr(0, "count"))
    k.setEnabled(False)
    k.clearFlag(nuke.STARTLINE)
    for slot in range(32):
        for row in range(3):
            k = hidden(g, nuke.Array_Knob("shape%d_r%d" % (slot, row), "", 4))
            for j in range(4):
                k.setExpression(shape_expr(slot, "r%d:%d" % (row, j)), j)
        k = hidden(g, nuke.Array_Knob("shape%d_info" % slot, "", 3))
        for j in range(3):
            k.setExpression(shape_expr(slot, "info:%d" % j), j)
    add(g, nuke.Text_Knob("map_divider", "coverage map"))
    add(g, nuke.Text_Knob("map_help", "",
                          "Plug a picture into 'map' to say where the decks have clouds, as seen\n"
                          "through the camera on 'map frame': white piles up clouds, mid grey keeps\n"
                          "the layer's coverage, black clears it. It marks where the clouds stand on the\n"
                          "layer (at its middle height), and white heaps them into domes. Paint it with\n"
                          "a Roto over the plate, soft and blurred. It stays put in the world and drifts\n"
                          "with the wind."))
    k = add(g, nuke.Int_Knob("map_frame", "map frame"), "The frame the map is painted on.")
    k.setValue(int(nuke.root()["first_frame"].value()))
    add(g, nuke.PyScript_Knob("map_frame_here", "use this frame",
                              "nuke.thisNode()['map_frame'].setValue(nuke.frame())"),
        "Sets 'map frame' to the current frame.")
    g["map_frame_here"].clearFlag(nuke.STARTLINE)
    add(g, nuke.Double_Knob("map_softness", "map softness"),
        "Blurs the map over a share of the cloud size, so a hard edge in the paint comes out as a slope of "
        "thinning cloud instead of a straight wall through a tall deck. 0: the map as painted.").setValue(0.5)
    g["map_softness"].setRange(0, 2)

    add_easy_tab(g)

    for i, (tname, on) in enumerate(LAYER_DEFAULTS):
        p = "l%d_" % (i + 1)
        add(g, nuke.Tab_Knob(p + "tab", "Layer %d" % (i + 1)))
        add(g, nuke.Boolean_Knob(p + "enable", "enable"),
            "Draw this layer. Layers sort themselves by depth.").setValue(on)
        t = add(g, nuke.Enumeration_Knob(p + "type", "type", TYPE_NAMES),
                "Sets this layer's shape knobs to the type's values (they can be tuned after).")
        t.setValue(tname)
        vals = cloud_types.full(tname)
        vals["cover"] = cloud_types.preset_cover(tname)
        for name, label, tip, lo, hi in MAIN:
            k = add(g, nuke.Double_Knob(p + name, label), tip)
            k.setRange(lo, hi)
            k.setValue(vals[name])
        # The type's cover table: the kernel's coverage at cover 0, .25, .5, .75 and 1.
        k = hidden(g, nuke.Array_Knob(p + "cover_table", "cover table", 5))
        for j, v in enumerate(cloud_types.cover_table(tname)):
            k.setValue(v, j)
        # The sun at this layer's height against the camera's (atmos light only).
        k = hidden(g, nuke.Color_Knob(p + "sun_tint", "sun tint"))
        for j, ch in enumerate(("red", "green", "blue")):
            k.setExpression(layer_sun_tint(int(p[1]), ch), j)
        k = add(g, nuke.Double_Knob(p + "map_amount", "follow map"),
                "How much this deck follows the coverage map (when 'map' is plugged in).")
        k.setValue(1.0)
        k = add(g, nuke.Enumeration_Knob(p + "map_channel", "map channel", MAP_CHANNELS),
                "Which channel of the map this deck reads: paint each deck in its own channel to place "
                "them separately.")
        k.clearFlag(nuke.STARTLINE)
        k = add(g, nuke.Enumeration_Knob(p + "detail_model", "detail model", ["soft billows", "classic"]),
                "soft billows: the fine detail is Perlin-Worley billow noise (rounded, soft-edged billows that "
                "run into each other) and it thins the cloud rather than only pushing a surface in and out, so "
                "the outer cloud is soft, see-through puffs and wisps over a dense core; 'swirl' and "
                "'turbulence' curl it with curl noise, so wisps roll instead of smearing. Best on clouds seen "
                "close up. classic: cauliflower billows with a crisp skin, which hold up better on far "
                "stratiform and mackerel decks. Each type sets the one that suits it.")
        k.setValue(vals["detail_model"])
        k = add(g, nuke.Enumeration_Knob(p + "map_use", "map use", ["footprint", "silhouette"]),
                "footprint: the map marks where clouds stand on the layer, seen from above (they rise "
                "from it in heaps). silhouette: the painted shape is the cloud mass's outline as the "
                "camera on 'map frame' sees it, so you can draw towers, a shelf or a wall of cloud "
                "where you want it; set how far away it stands and how deep it is. Black is clear "
                "sky, white is cloud, and the layer's noise tears the edges.")
        k = add(g, nuke.Double_Knob(p + "sil_distance", "silhouette distance"),
                "How far from the camera the painted mass stands, in km ('map use' silhouette).")
        k.setRange(1, 60)
        k.setValue(10)
        k = add(g, nuke.Double_Knob(p + "sil_depth", "silhouette depth"),
                "How deep the painted mass is, front to back, in km ('map use' silhouette).")
        k.setRange(0.2, 20)
        k.setValue(5)
        k = add(g, nuke.Boolean_Knob(p + "depth_ramp_on", "depth ramp"),
                "Shows this deck only over a band of depth from the camera, in scene units of Planar Z: the "
                "same numbers as the bg's depth pass (Planar Z), so you can type what you read from it. "
                "Clear before A, fading in to full at B, full to C, gone at D. Decks only, not volumes. By "
                "itself it changes only what the camera sees: clouds outside the band still cast their "
                "shadows and light (see 'hide shadows too').")
        k = add(g, nuke.Boolean_Knob(p + "depth_ramp_shadows", "hide shadows too"),
                "With 'depth ramp': the clouds outside the band also stop casting shadows and light: on the "
                "bg (cloud_shadow), on the other layers, in this layer's own shading and in the light grid. "
                "Off: they are only hidden from the camera.")
        k.clearFlag(nuke.STARTLINE)
        k = add(g, nuke.Enumeration_Knob(p + "depth_ramp_falloff", "falloff", ["linear", "smooth"]),
                "How the ramp fades from A to B and from C to D. linear: straight lines, as the graph draws "
                "them. smooth: eases in and out at each handle (smoothstep), so there is no crease where a fade "
                "starts or ends. Hard cuts (A = B, C = D) stay hard.")
        k.clearFlag(nuke.STARTLINE)
        # The ramp's graph is a Keyer's 'range' (a hidden Keyer inside the group, L<n>_DepthRamp),
        # shown here through a link: a user knob of that class draws no graph.
        k = nuke.Link_Knob(p + "depth_ramp", "")
        k.makeLink("L%d_DepthRamp" % (i + 1), "range")
        k.setTooltip("A, B, C, D: Planar Z from the camera in scene units, as in the bg's depth pass. Clear "
                     "before A, full from B to C, clear past D. Drag the handles in the graph or type the values.")
        g.addKnob(k)
        add(g, nuke.Text_Knob(p + "vol_divider", "volume"))
        k = add(g, nuke.Enumeration_Knob(p + "vol_shape", "shape", VOL_SHAPES),
                "The volume's overall shape, before lumps and erosion break it up.")
        k.setValue(int(vals["vol_shape"]))
        add(g, nuke.XYZ_Knob(p + "vol_position", "position"),
            "Centre of the volume's base, in scene units. Not used while a 3D node is plugged into the "
            "layer's box input ('make 3D box').")
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
        add(g, nuke.PyScript_Knob(p + "make_box", "make 3D box", make_box_script(p, i + 1)),
            "Makes a Cube beside this node, placed and sized like the volume, and plugs it into this "
            "layer's box input (box%d): move, rotate and scale the Cube in the 3D viewer (view it with "
            "your camera) and the cloud follows. Any 3D node works in that input (a Cube, an Axis, a "
            "TransformGeo, parented or tracked), and the volume fills its box." % (i + 1))
        add(g, nuke.PyScript_Knob(p + "release_box", "release box", release_box_script(p, i + 1)),
            "Unplugs the box; the volume stays where it is.")
        g[p + "release_box"].clearFlag(nuke.STARTLINE)
        # The 3D node in the box input, read through BOX_LIB.
        k = hidden(g, nuke.Int_Knob(p + "box_found"))
        k.setExpression(box_expr(i + 1, "found"))
        for name, what, step in (("box_center", "center", 0), ("box_center_next", "center", 1),
                                 ("box_center_prev", "center", -1), ("box_axis_x", "axis_x", 0),
                                 ("box_axis_y", "axis_y", 0), ("box_axis_z", "axis_z", 0),
                                 ("box_size", "size", 0)):
            k = hidden(g, nuke.XYZ_Knob(p + name))
            for j in range(3):
                k.setExpression("%sbox_found ? %s : 0" % (p, box_expr(i + 1, "%s:%d" % (what, j), step)), j)
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

    add_sheet_tab(g)

    k = hidden(g, nuke.Multiline_Eval_String_Knob("box_lib", "box lib"))
    k.setValue(BOX_LIB)
    k = hidden(g, nuke.Multiline_Eval_String_Knob("shape_lib", "shape lib"))
    k.setValue(SHAPE_LIB)
    k = hidden(g, nuke.Multiline_Eval_String_Knob("analyze_lib", "analyze lib"))
    k.setValue(ANALYZE_LIB)
    add(g, nuke.Tab_Knob("about", "About"))
    add(g, nuke.Text_Knob("version", "", "EzCloudGen v%s" % VERSION))
    add(g, nuke.Boolean_Knob("debug", "debug report"),
        "Prints a plain-text report of what the node sees to the Script Editor: the inputs, the bg's format, "
        "bbox and layers, the camera (and settings EzCloudGen ignores, such as win_translate), the depth "
        "(statistics, a histogram and coarse maps of distance and height), a position pass compared with the "
        "depth and camera, each layer against the terrain, and the sun and light. Numbers only: no picture "
        "leaves the node, so it is safe to share for a studio plate. While on, 'analyze scene' prints it too.")
    k = add(g, nuke.PyScript_Knob("print_debug", "print debug report", DEBUG_BUTTON),
            "Prints the debug report for this frame to the Script Editor.")
    k.clearFlag(nuke.STARTLINE)
    k.setVisible(False)
    k = add(g, nuke.Channel_Knob("position_pass", "position pass", 3),
            "The bg's world-position layer for the debug report, when it isn't found by name (Pworld, "
            "P_world, a custom AOV...). none: look for P, Pworld, P_world, position and similar. The "
            "report compares it with the world positions from the depth and camera.")
    k.setValue("none")
    k.setVisible(False)

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
    # The camera one frame later and one frame earlier, for motion vectors.
    for which, step in (("next", 1), ("prev", -1)):
        m = hidden(g, nuke.Array_Knob("cam_%s_matrix" % which, "camera matrix", 16))
        for i in range(16):
            m.setExpression(py(FIND_CAMERA + "ret = c['world_matrix'].getValueAt(nuke.frame() + (%d), %d) "
                                             "if c is not None else %g" % (step, i, identity[i])), i)
        for name, default in (("focal", 24), ("haperture", 36)):
            k = hidden(g, nuke.Double_Knob("cam_%s_%s" % (which, name)))
            k.setExpression(py(FIND_CAMERA + "ret = c['%s'].getValueAt(nuke.frame() + (%d)) if c is not None else %g"
                               % (name, step, default)))
    # The camera on the map frame.
    m = hidden(g, nuke.Array_Knob("map_cam_matrix", "map camera matrix", 16))
    for i in range(16):
        m.setExpression(py(FIND_CAMERA + "ret = c['world_matrix'].getValueAt(nuke.thisNode()['map_frame'].value(), %d) "
                                         "if c is not None else %g" % (i, identity[i])), i)
    for name, default in (("focal", 24), ("haperture", 36)):
        k = hidden(g, nuke.Double_Knob("map_cam_" + name))
        k.setExpression(py(FIND_CAMERA + "ret = c['%s'].getValueAt(nuke.thisNode()['map_frame'].value()) "
                                         "if c is not None else %g" % (name, default)))
    # The bg's pixel aspect (2 for a 2x anamorphic plate): the vertical aperture is
    # haperture x height / (width x pixel aspect), as Nuke's own renderers do.
    k = hidden(g, nuke.Double_Knob("bg_pixel_aspect"))
    k.setExpression(py("b = nuke.thisNode().input(0)\n"
                       "ret = b.format().pixelAspect() if b is not None else nuke.root().format().pixelAspect()"))
    # The variations sheet's camera: the shot camera turned (same place, same heading) to frame
    # the layer shown. A deck above the camera puts the horizon low in each tile, one below it
    # puts it high, so every tile is mostly cloud even when the shot looks down at a valley and
    # the deck is only a strip at the top of its frame. A volume keeps the shot's framing.
    m = hidden(g, nuke.Array_Knob("var_cam_rot", "variations camera", 9))
    for i in range(9):
        m.setExpression(py(VARIATIONS_AIM + "ret = R[%d]" % i), i)
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
        # Manual: tinted half way towards the sky colour's hue, so far clouds fade cool into the
        # air rather than into flat grey.
        k3.setExpression("light_source ? atm_sky_color.%s * haze_color.%s : haze_color.%s * 0.43 * "
                         "(0.5 + 0.5 * sky_color.%s / max(sky_color.r, sky_color.g, sky_color.b, 1e-4))"
                         % (c, c, c, c), i)
    k = hidden(g, nuke.Double_Knob("work_scale"))
    k.setExpression("(resolution==0 ? 1 : resolution==1 ? 0.5 : 0.25) * (preview ? 0.5 : 1)")
    k = hidden(g, nuke.Double_Knob("time_s"))
    k.setExpression("frame / max(root.fps, 1)")

    g["knobChanged"].setValue(knob_changed())


# ---- The nodes inside --------------------------------------------------------------------

# The sun maps: SUN_MAP_RES square, covering the ground out to about SUN_MAP_SIZE metres at
# full detail (coarser further out, see sunMapUV in the kernel).
SUN_MAP_RES = 1536
SUN_MAP_SIZE = 10000.0

# The light grid: GRID_W x GRID_H cells across the view, GRID_T x GRID_T slices in distance.
GRID_W, GRID_H, GRID_T = 192, 108, 8

# A layer is off when disabled, and in the Variations view unless it is the one shown.
DISABLE = "!parent.l%d_enable || (parent.view==4 && parent.variations_of!=%d)"


def layer_on(layer):
    """Expression: layer (1..3) is on."""
    return "!(%s)" % (DISABLE % (layer, layer - 1))


def blink(name, output, src, cmap, zin, smaps, source_file, step=1, only=-1, lgrid=None):
    """One kernel for all three layers (their settings are 3-element arrays): it marches them
    together, so overlapping layers interleave. smaps: the three layers' sun maps (each layer is
    shadowed by the other two's). only: the sun map pass marches that layer (0..2) alone."""
    n = compiled(name, source_file)
    n.setInput(0, src)
    n.setInput(1, cmap)
    n.setInput(2, zin)
    for j, sm in enumerate(smaps):
        n.setInput(3 + j, sm)
    # The light grid (only the colour and sun passes read it; the others get a stand-in).
    n.setInput(6, lgrid if lgrid is not None else smaps[0])
    k = KERNEL + "_"
    n[k + "output"].setValue(output)
    n[k + "only_layer"].setValue(only)
    rows = ((0, 1, 2), (4, 5, 6), (8, 9, 10))
    for r, idx in enumerate(rows):
        for j, m in enumerate(idx):
            n[k + "cam_row%d" % r].setExpression("parent.view==4 ? parent.var_cam_rot.%d : "
                                                 "parent.cam_world_matrix.%d" % (r * 3 + j, m), j)
    for j, m in enumerate((3, 7, 11)):
        n[k + "cam_position"].setExpression("parent.cam_world_matrix.%d" % m, j)
    n[k + "focal"].setExpression("parent.cam_focal")
    n[k + "haperture"].setExpression("parent.cam_haperture")
    # The camera frame is the work format.
    n[k + "frame_size"].setExpression("width", 0)
    n[k + "frame_size"].setExpression("height", 1)
    n[k + "pixel_aspect"].setExpression("parent.bg_pixel_aspect")
    n[k + "scene_scale"].setExpression("parent.scene_scale")
    n[k + "ground_height"].setExpression("parent.ground_height")
    n[k + "earth_curvature"].setExpression("parent.earth")
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
    # The kernel lays the horizon haze once, under the decks that are on.
    n[k + "horizon_haze"].setExpression("parent.horizon_haze")
    n[k + "quality"].setExpression("parent.quality * (parent.preview ? 0.5 : 1)")
    n[k + "edge_steps"].setExpression("parent.preview ? 1 : parent.edge_steps")
    n[k + "samples"].setExpression(SAMPLES_EXPR)
    # The global seed jitters the steps; each layer's own seed shapes its clouds.
    n[k + "seed"].setExpression("parent.seed")
    n[k + "evolve"].setExpression("parent.evolve_speed * parent.time_s")
    n[k + "gap_amount"].setExpression("parent.gap_amount")
    n[k + "gap_size"].setExpression("parent.gap_size * 1000")
    # The coverage map camera, the motion vectors' other camera.
    n[k + "use_map"].setExpression("parent.map_found")
    for r, idx in enumerate(rows):
        for j, m in enumerate(idx):
            n[k + "map_row%d" % r].setExpression("parent.map_cam_matrix.%d" % m, j)
    for j, m in enumerate((3, 7, 11)):
        n[k + "map_position"].setExpression("parent.map_cam_matrix.%d" % m, j)
    n[k + "map_focal"].setExpression("parent.map_cam_focal")
    n[k + "map_haperture"].setExpression("parent.map_cam_haperture")
    # The variations sheet (only the layer shown is on in that view).
    n[k + "tiles"].setExpression("parent.view==4 ? 3 : 1")
    which = "next" if step > 0 else "prev"
    for r, idx in enumerate(rows):
        for j, m in enumerate(idx):
            n[k + "other_row%d" % r].setExpression("parent.cam_%s_matrix.%d" % (which, m), j)
    for j, m in enumerate((3, 7, 11)):
        n[k + "other_position"].setExpression("parent.cam_%s_matrix.%d" % (which, m), j)
    n[k + "other_focal"].setExpression("parent.cam_%s_focal" % which)
    n[k + "other_haperture"].setExpression("parent.cam_%s_haperture" % which)
    n[k + "occlude"].setExpression("parent.occlude && parent.bg_found")
    n[k + "depth_mode"].setExpression("parent.depth_mode")
    n[k + "sky_depth"].setExpression("parent.sky_depth * 1000 / max(parent.scene_scale, 1e-6)")
    # The shadows of the other layers, from their sun maps (only the colour and sun passes read them).
    n[k + "use_sun_map"].setExpression("parent.layer_shadows && %d < 2" % output)
    n[k + "sun_map_size"].setValue(SUN_MAP_SIZE)
    n[k + "sun_glow"].setExpression("parent.sun_glow")
    n[k + "diffusion"].setExpression("parent.diffusion")
    n[k + "wrap_light"].setExpression("parent.wrap_light")
    for j, ch in enumerate("rgb"):
        n[k + "forward_warmth"].setExpression("parent.forward_warmth_in_use.%s" % ch, j)
    n[k + "detail_sharpness"].setExpression("parent.detail_sharpness")
    n[k + "billow_light"].setExpression("parent.billow_light")
    n[k + "billow_shrink"].setExpression("parent.billow_shrink")

    n[k + "use_grid"].setExpression("parent.light_grid && %d < 2" % output if lgrid is not None else "0")
    n[k + "grid_w"].setValue(GRID_W)
    n[k + "grid_h"].setValue(GRID_H)
    n[k + "grid_tx"].setValue(GRID_T)
    n[k + "grid_ty"].setValue(GRID_T)
    n[k + "grid_far"].setExpression("min(parent.max_distance * 1000, 80000)")
    n[k + "even_detail"].setExpression("parent.even_detail")
    n[k + "horizon_samples"].setExpression("parent.horizon_samples")
    n[k + "shape_count"].setExpression("parent.shape_count")
    n[k + "shape_softness"].setExpression("parent.shape_softness")
    n[k + "holdout_amount"].setExpression("parent.holdout_amount")
    n[k + "add_amount"].setExpression("parent.add_amount")
    for slot in range(32):
        for row in range(3):
            for j in range(4):
                n[k + "shape_r%d" % row].setExpression("parent.shape%d_r%d.%d" % (slot, row, j), slot * 4 + j)
        for j in range(3):
            n[k + "shape_info"].setExpression("parent.shape%d_info.%d" % (slot, j), slot * 3 + j)
    n[k + "bg_edge_softness"].setExpression("parent.bg_edge_softness * parent.work_scale")
    n[k + "ground_softness"].setExpression("parent.ground_softness")
    n[k + "motion_blur"].setExpression("parent.motion_blur && !parent.preview")
    n[k + "shutter"].setExpression("parent.shutter")
    n[k + "sky_shading"].setExpression("parent.sky_shading")
    n[k + "round_lobes"].setExpression("parent.round_lobes")
    n[k + "map_softness"].setExpression("parent.map_softness")

    # Per layer: element i of each array (a float3 setting takes three elements per layer).
    for layer in (1, 2, 3):
        i = layer - 1
        p = "parent.l%d_" % layer

        def one(knob, expr):
            n[k + knob].setExpression(expr, i)

        def vec(knob, exprs):
            for c, e in enumerate(exprs):
                n[k + knob].setExpression(e, i * len(exprs) + c)

        one("layer_on", layer_on(layer))
        # The ramp's knob is in scene units (the depth pass's numbers); the kernel works in metres.
        r = "L%d_DepthRamp.range" % layer
        one("depth_ramp_a", "%sdepth_ramp_on ? %s.0 * parent.scene_scale : -1" % (p, r))
        one("depth_ramp_b", "%s.1 * parent.scene_scale" % r)
        one("depth_ramp_c", "%s.2 * parent.scene_scale" % r)
        one("depth_ramp_d", "%s.3 * parent.scene_scale" % r)
        one("depth_ramp_sh", "%sdepth_ramp_shadows" % p)
        one("depth_ramp_smooth", "%sdepth_ramp_falloff" % p)
        one("layer_seed", "parent.seed + %sseed" % p)
        # Drift with the wind: the field is sampled upwind.
        vec("offset", ("-%swind_speed * parent.time_s * sin(radians(%swind_deg))" % (p, p),
                       "%swind_speed * parent.time_s * cos(radians(%swind_deg))" % (p, p)))
        for name, _, _, _, _ in MAIN + SHAPE + EROSION + VOLUME:
            if name != "cover":
                one(name, p + name)
        # Visible cover through the type's table (piecewise linear, so it animates).
        tb, c4 = p + "cover_table", "clamp(%scover, 0, 1) * 4" % p
        one("coverage", "%s.0" % tb + "".join(" + (%s.%d - %s.%d) * clamp(%s - %d, 0, 1)" % (tb, j + 1, tb, j, c4, j)
                                             for j in range(4)))
        # The preview drops the small lumps: they cost a second lobe lookup at every step.
        one("small_lumps", "parent.preview ? 0 : %ssmall_lumps" % p)
        one("volume", p + "volume")
        one("vol_shape", p + "vol_shape")
        # A 3D node in the layer's box input sets the centre, axes and size; else the knobs do.
        bf = p + "box_found"
        vec("vol_center", ("%s ? %sbox_center.x : %svol_position.x" % (bf, p, p),
                           "%s ? %sbox_center.y : %svol_position.y + %svol_size.y / 2 / "
                           "max(parent.scene_scale, 1e-6)" % (bf, p, p, p),
                           "%s ? %sbox_center.z : %svol_position.z" % (bf, p, p)))
        one("vol_axes", bf)
        vec("vol_rotate", ["%svol_rotate.%s" % (p, c) for c in "xyz"])
        vec("vol_size", ["%s ? %sbox_size.%s : %svol_size.%s" % (bf, p, c, p, c) for c in "xyz"])
        for a in "xyz":
            vec("vol_axis_" + a, ["%sbox_axis_%s.%s" % (p, a, c) for c in "xyz"])
        vec("sun_tint", ["%ssun_tint.%s" % (p, c) for c in "rgb"])
        one("density", p + "density")
        # The coverage map, drifting with the wind since the map frame.
        one("map_amount", p + "map_amount")
        one("map_channel", p + "map_channel")
        one("map_mode", p + "map_use")
        one("detail_model", "%sdetail_model == 0 ? 1 : 0" % p)
        one("sil_distance", "%ssil_distance * 1000" % p)
        one("sil_depth", "%ssil_depth * 1000" % p)
        since = "(parent.time_s - parent.map_frame / max(root.fps, 1))"
        vec("map_drift", ("-%swind_speed * %s * sin(radians(%swind_deg))" % (p, since, p),
                          "%swind_speed * %s * cos(radians(%swind_deg))" % (p, since, p)))
        # Motion vectors: the wind and the volume on the other frame (step frames away).
        t_other = "(parent.time_s + (%d) / max(root.fps, 1))" % step
        vec("other_offset", ("-%swind_speed * %s * sin(radians(%swind_deg))" % (p, t_other, p),
                             "%swind_speed * %s * cos(radians(%swind_deg))" % (p, t_other, p)))
        f_other = "(frame + (%d))" % step
        bc = "%sbox_center_%s" % (p, which)
        vec("other_vol_center", ("%s ? %s.x : %svol_position.x%s" % (bf, bc, p, f_other),
                                 "%s ? %s.y : %svol_position.y%s + %svol_size.y / 2 / "
                                 "max(parent.scene_scale, 1e-6)" % (bf, bc, p, f_other, p),
                                 "%s ? %s.z : %svol_position.z%s" % (bf, bc, p, f_other)))
    n["disable"].setExpression("!(%s)" % " || ".join(layer_on(j) for j in (1, 2, 3)))
    return n




SHEET_KERNEL = "EzCirrusSheet"
SHEET_ON = "parent.sheet_enable && parent.view!=4"


def sheet_copy():
    """An LF-only copy of the cirrus sheet kernel in the temp folder."""
    import tempfile
    with open(os.path.join(ROOT, "blink", SHEET_KERNEL + ".blink")) as f:
        text = f.read().replace("\r\n", "\n")
    path = os.path.join(tempfile.gettempdir(), SHEET_KERNEL + ".blink").replace("\\", "/")
    with open(path, "w", newline="\n") as f:
        f.write(text)
    return path


def sheet_blink(name, output, src, zin, source_file):
    """The cirrus sheet pass (output 0 colour, 1 its sun share), lit and placed like the layers."""
    n = compiled(name, source_file)
    n.setInput(0, src)
    n.setInput(1, zin)
    k = SHEET_KERNEL + "_"
    n[k + "output"].setValue(output)
    rows = ((0, 1, 2), (4, 5, 6), (8, 9, 10))
    for r, idx in enumerate(rows):
        for j, m in enumerate(idx):
            n[k + "cam_row%d" % r].setExpression("parent.cam_world_matrix.%d" % m, j)
    for j, m in enumerate((3, 7, 11)):
        n[k + "cam_position"].setExpression("parent.cam_world_matrix.%d" % m, j)
    n[k + "focal"].setExpression("parent.cam_focal")
    n[k + "haperture"].setExpression("parent.cam_haperture")
    n[k + "frame_size"].setExpression("width", 0)
    n[k + "frame_size"].setExpression("height", 1)
    n[k + "pixel_aspect"].setExpression("parent.bg_pixel_aspect")
    n[k + "scene_scale"].setExpression("parent.scene_scale")
    n[k + "ground_height"].setExpression("parent.ground_height")
    n[k + "earth_curvature"].setExpression("parent.earth")
    for j, c in enumerate("xyz"):
        n[k + "sun_direction"].setExpression("parent.sun_in_use.%s" % c, j)
    n[k + "sun_rotation"].setExpression("parent.sun_rotation_in_use")
    for j, c in enumerate("rgb"):
        n[k + "sun_color"].setExpression("parent.sun_color_in_use.%s * parent.sheet_sun_tint.%s" % (c, c), j)
        n[k + "sky_color"].setExpression("parent.sky_color_in_use.%s" % c, j)
        n[k + "haze_color"].setExpression("parent.haze_color_in_use.%s" % c, j)
    n[k + "haze_distance"].setExpression("parent.haze_distance * 1000")
    n[k + "max_distance"].setExpression("parent.max_distance * 1000")
    n[k + "sun_glow"].setExpression("parent.sun_glow")
    n[k + "occlude"].setExpression("parent.occlude && parent.bg_found")
    n[k + "depth_mode"].setExpression("parent.depth_mode")
    n[k + "sky_depth"].setExpression("parent.sky_depth * 1000 / max(parent.scene_scale, 1e-6)")
    for name in ("height", "cover", "edge", "scale_km", "fibre_size", "fibre_length", "fibres", "opacity",
                 "forward", "ambient"):
        n[k + name].setExpression("parent.sheet_" + name)
    n[k + "direction_deg"].setExpression("parent.sheet_direction")
    n[k + "seed"].setExpression("parent.seed + parent.sheet_seed")
    # Drift along the strands with the wind: the texture is sampled upwind.
    n[k + "drift"].setExpression("-parent.sheet_wind_speed * parent.time_s * sin(radians(parent.sheet_direction))", 0)
    n[k + "drift"].setExpression("parent.sheet_wind_speed * parent.time_s * cos(radians(parent.sheet_direction))", 1)
    n["disable"].setExpression("!(%s)" % SHEET_ON)
    return n


# The kernel's three cloud() calls, one per kind of pass. Blink inlines cloud() at every call site,
# and the CPU (LLVM) compile time grows much faster than their number (one: about 11 minutes, two:
# 51, four: well over an hour), so each pass gets a copy of the kernel with only its own call; in
# it the others read no cloud (that pass never runs them).
CLOUD_CALLS = {
    "march": ("          float dn = cloud(q, fq, cheap, sdL[L], L, bd);", "          float dn = 0.0f;"),
    "shadow": ("      od += cloud(p + sun * t, max(dt * 0.5f, 20.0f), true, sd, lyr, bd) * dt;", "      od += 0.0f;"),
    "grid": ("        odL[L] += cloud(p + sun * t, max(cell, t * 0.02f), true, layer_seed[L], L, bd) * len * sig0;",
             "        odL[L] += 0.0f;"),
}


def lf_copy(kernel):
    """LF-only copies of a kernel in the temp folder (a Windows checkout may have CRLF), one per kind
    of pass (CLOUD_CALLS): {kind: path}."""
    import tempfile
    with open(os.path.join(ROOT, "blink", kernel + ".blink")) as f:
        text = f.read().replace("\r\n", "\n")
    paths = {}
    for kind in CLOUD_CALLS:
        t = text
        for other, (call, none) in CLOUD_CALLS.items():
            assert t.count(call) == 1, "the kernel's %s cloud() call has changed: update CLOUD_CALLS" % other
            if other != kind:
                t = t.replace(call, none)
        path = os.path.join(tempfile.gettempdir(), "%s_%s.blink" % (kernel, kind)).replace("\\", "/")
        with open(path, "w", newline="\n") as f:
            f.write(t)
        paths[kind] = path
    return paths


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
    sources = lf_copy(KERNEL)
    source = sources["march"]

    g = nuke.nodes.Group(name="EzCloudGen")
    build_knobs(g)
    g["tile_color"].setValue(0x8fb3d9ff)
    # The node says when it is a quick preview.
    g["label"].setValue('[expr {[value preview] ? "PREVIEW" : ""}]')
    with g:
        bg = nuke.nodes.Input(name="bg")
        cam = nuke.nodes.Input(name="camera")
        atm = nuke.nodes.Input(name="atmos")
        sun = nuke.nodes.Input(name="sun")
        mp = nuke.nodes.Input(name="map")
        boxes = [nuke.nodes.Input(name="box%d" % i) for i in (1, 2, 3)]
        # Shapes (Scenes of Spheres, Cubes, Cylinders) that carve cloud away, and that grow it.
        nuke.nodes.Input(name="holdout")
        nuke.nodes.Input(name="add")
        for n in [cam, atm, sun, mp] + boxes:
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
        # The area to render: the format, and the bg's bbox where it is bigger (overscan), so the
        # clouds carry on past the frame edge with the camera's view.
        fmt_box = nuke.nodes.Crop(name="FormatBox", reformat=False, crop=True)
        for j, e in enumerate(("0", "0", "input.width", "input.height")):
            fmt_box["box"].setExpression(e, j)
        fmt_box.setInput(0, black)
        area = nuke.nodes.Merge2(name="WorkArea", operation="plus", bbox="union", output="rgba")
        area.setInput(0, black)
        area.setInput(1, fmt_box)
        work = nuke.nodes.Reformat(name="WorkFormat", type="scale", filter="Impulse", black_outside=False, pbb=True)
        work["scale"].setExpression("parent.work_scale")
        work.setInput(0, area)
        # The map, or a black stand-in without one (the kernels need input 1 connected; use_map
        # is 0 then, so they never read it).
        nomap = nuke.nodes.Constant(name="MapNone", channels="rgba", color=0)
        # 'depth ramp' graphs: one Keyer per layer, never rendered, only for its range knob (linked
        # onto the Layer tabs). The kernels read the values from them.
        for layer in (1, 2, 3):
            kr = nuke.nodes.Keyer(name="L%d_DepthRamp" % layer,
                                  label="depth ramp of layer %d (UI only, not rendered)" % layer)
            kr["range"].setValue([0, 5000, 50000, 80000])
            kr["range"].setRange(0, 100000)
        mapsrc = nuke.nodes.Switch(name="MapSource")
        mapsrc.setInput(0, nomap)
        mapsrc.setInput(1, mp)
        mapsrc["which"].setExpression("parent.map_found")
        mp = mapsrc
        # The bg's depth in red, in the work format (black without one: all sky).
        zsrc = nuke.nodes.Copy(name="DepthSource", from0="depth.Z", to0="rgba.red")
        zsrc.setInput(0, nuke.toNode("WorkBlack"))
        # A Copy errors on a channel its input lacks: add it (black) when the bg has none.
        zadd = nuke.nodes.AddChannels(name="DepthEnsure", channels="depth.Z")
        zadd.setInput(0, bg)
        zsrc.setInput(1, zadd)
        zwork = nuke.nodes.Reformat(name="DepthWork", type="scale", filter="Impulse", black_outside=False, pbb=True)
        zwork["scale"].setExpression("parent.work_scale")
        zwork.setInput(0, zsrc)

        # Inter-layer shadows: each layer renders its optical depth towards the sun from the
        # ground up, with its altitude moments (a small square map); a layer adds up the other
        # layers' maps into its smap (the kernel keeps only the part above each point). A
        # disabled layer's map is black: no shadow.
        smfmt = nuke.nodes.Reformat(name="SunMapFormat", type="to box", box_fixed=True, resize="distort",
                                    filter="Impulse", black_outside=True)
        smfmt["box_width"].setValue(SUN_MAP_RES)
        smfmt["box_height"].setValue(SUN_MAP_RES)
        smfmt.setInput(0, nuke.toNode("WorkBlack"))
        sunmaps = []
        for i in range(1, 4):
            sm = blink("L%d_SunMap" % i, 5, smfmt, mp, smfmt, [smfmt] * 3, source, only=i - 1)
            k = KERNEL + "_"
            sm[k + "samples"].setExpression("1")
            sm[k + "tiles"].setExpression("1")
            sm["disable"].setExpression("!(%s) || !(parent.layer_shadows || (parent.sun_map_out && parent.breakout))"
                                        % layer_on(i))
            sunmaps.append(sm)

        # The passes: one kernel each, marching all the layers together (each is shadowed by the
        # other layers' sun maps).
        none_on = "!(%s)" % " || ".join(layer_on(j) for j in (1, 2, 3))
        # The light grid: every layer's optical depth towards the sun, baked once over the view
        # and read back by the colour and sun passes (smooth, noise-free self-shadowing).
        gridfmt = nuke.nodes.Reformat(name="LightGridFormat", type="to box", box_fixed=True, resize="distort",
                                      filter="Impulse", black_outside=True)
        gridfmt["box_width"].setValue(GRID_W * GRID_T)
        gridfmt["box_height"].setValue(GRID_H * GRID_T)
        gridfmt.setInput(0, nuke.toNode("WorkBlack"))
        lgrid = blink("Clouds_LightGrid", 6, gridfmt, mp, gridfmt, sunmaps, sources["grid"])
        lgrid[KERNEL + "_samples"].setExpression("1")
        lgrid[KERNEL + "_tiles"].setExpression("1")
        # The grid is laid out over the camera's frame, not its own image's.
        lgrid[KERNEL + "_frame_size"].setExpression("WorkFormat.width", 0)
        lgrid[KERNEL + "_frame_size"].setExpression("WorkFormat.height", 1)
        lgrid["disable"].setExpression("%s || !parent.light_grid" % none_on)
        col = blink("Clouds_Color", 0, work, mp, zwork, sunmaps, source, lgrid=lgrid)
        sunm = blink("Clouds_Sun", 1, work, mp, zwork, sunmaps, source, lgrid=lgrid)
        sunm["disable"].setExpression("%s || !((parent.breakout && !parent.preview) || parent.view==2)" % none_on)
        shadow = blink("Clouds_Shadow", 3, work, mp, zwork, [smfmt] * 3, sources["shadow"])
        shadow["disable"].setExpression("%s || !(parent.occlude && parent.bg_found) || "
                                        "!(((parent.breakout || parent.view==0) && !parent.preview) || parent.view==5)"
                                        % none_on)
        dep = blink("Clouds_Depth", 2, work, mp, zwork, [smfmt] * 3, source)
        motion = {}
        for step, nm in ((1, "Fwd"), (-1, "Bwd")):
            mvn = blink("Clouds_%s" % nm, 4, work, mp, zwork, [smfmt] * 3, source, step)
            mvn["disable"].setExpression("%s || !parent.motion_vectors || parent.preview" % none_on)
            motion[step] = mvn

        def up(name, src, frame=True):
            # Back to the bg's format. A pass of the frame keeps its bbox (the overscan), cut to
            # the work area first: a kernel's own bbox also takes in its sun map inputs.
            if frame:
                fit = nuke.nodes.CopyBBox(name=name + "Area")
                fit.setInput(0, src)
                fit.setInput(1, work)
                src = fit
            r = nuke.nodes.Reformat(name=name, type="to box", box_fixed=True, resize="distort",
                                    filter="Cubic", black_outside=not frame, pbb=frame)
            r["box_width"].setExpression("FormatSource.width")
            r["box_height"].setExpression("FormatSource.height")
            r.setInput(0, src)
            return r

        # The cirrus sheet, behind the layers: they go over it ('under' with the layers as B, so
        # the merge passes the layers through when the sheet is off).
        sheet_src = sheet_copy()
        sheet_col = sheet_blink("Sheet_Color", 0, work, zwork, sheet_src)
        sheet_sun = sheet_blink("Sheet_Sun", 1, work, zwork, sheet_src)
        sheet_sun["disable"].setExpression("!(%s) || !((parent.breakout && !parent.preview) || parent.view==2)"
                                           % SHEET_ON)
        merged = []
        for nm, layers_pass, sheet_pass in (("Sheet_UnderColor", col, sheet_col), ("Sheet_UnderSun", sunm, sheet_sun)):
            m = nuke.nodes.Merge2(name=nm, operation="under", bbox="B")
            m.setInput(0, layers_pass)
            m.setInput(1, sheet_pass)
            m["disable"].setExpression("!(%s)" % SHEET_ON)
            merged.append(m)
        col, sunm = merged
        col_up = up("ColorUp", col)
        sun_up = up("SunUp", sunm)
        # Exposure and highlight rolloff: one scale per pixel, from the cloud colour's brightest
        # channel (unpremultiplied), applied to the colour and to its sun share alike, so the
        # layers still add up and the hue is kept.
        tone = nuke.nodes.Expression(name="ToneScale", temp_name0="gain", temp_expr0="pow(2, parent.exposure)",
                                     temp_name1="m", temp_expr1="max(r, g, b) / max(a, 1e-6) * gain",
                                     temp_name2="k", temp_expr2="1 - clamp(parent.highlight_rolloff, 0, 0.999)",
                                     channel0="rgb",
                                     expr0="parent.highlight_rolloff <= 0 || m <= k ? gain : "
                                           "gain * (k + (1 - k) * ((m - k) / (1 - k)) / (1 + (m - k) / (1 - k))) / m",
                                     channel1="none", channel2="none", channel3="none")
        tone.setInput(0, col_up)
        toned = []
        for nm, src in (("ToneColor", col_up), ("ToneSun", sun_up)):
            t = nuke.nodes.Merge2(name=nm, operation="multiply", output="rgb")
            t.setInput(0, src)
            t.setInput(1, tone)
            t["disable"].setExpression("parent.exposure == 0 && parent.highlight_rolloff <= 0")
            toned.append(t)
        col_up, sun_up = toned
        dep_fit = nuke.nodes.CopyBBox(name="DepthUpArea")
        dep_fit.setInput(0, dep)
        dep_fit.setInput(1, work)
        dep_up = nuke.nodes.Reformat(name="DepthUp", type="to box", box_fixed=True, resize="distort",
                                     filter="Impulse", black_outside=False, pbb=True)
        dep_up["box_width"].setExpression("FormatSource.width")
        dep_up["box_height"].setExpression("FormatSource.height")
        dep_up.setInput(0, dep_fit)

        # Motion vectors: back to full size and full-size pixels.
        mv_up = {}
        for step, nm in ((1, "Fwd"), (-1, "Bwd")):
            mfit = nuke.nodes.CopyBBox(name="%sUpArea" % nm)
            mfit.setInput(0, motion[step])
            mfit.setInput(1, work)
            mr = nuke.nodes.Reformat(name="%sUp" % nm, type="to box", box_fixed=True, resize="distort",
                                     filter="Impulse", black_outside=False, pbb=True)
            mr["box_width"].setExpression("FormatSource.width")
            mr["box_height"].setExpression("FormatSource.height")
            mr.setInput(0, mfit)
            mx = nuke.nodes.Multiply(name="%sScale" % nm, channels="rgb")
            mx["value"].setExpression("1 / max(parent.work_scale, 1e-6)")
            mx.setInput(0, mr)
            mv_up[step] = mx

        # Shadows: what all the layers together keep from the bg (the kernel multiplies the
        # sun each layer lets through).
        shadow_up = up("ShadowUp", shadow)
        # Darken the bg by shadow_amount for the Comp view.
        lit = nuke.nodes.Expression(name="Shadow_Light", channel0="rgb",
                                    expr0="1 - parent.shadow_amount * r",
                                    channel1="none", channel2="none", channel3="none")
        lit.setInput(0, shadow_up)
        shaded = nuke.nodes.Merge2(name="Shadow_OnBg", operation="multiply", output="rgb")
        shaded.setInput(0, bg)
        shaded.setInput(1, lit)
        shaded["disable"].setExpression("!(parent.occlude && parent.bg_found) || parent.shadow_amount==0")

        # Comp: the clouds over the bg (or alone).
        over = nuke.nodes.Merge2(name="CompOver", operation="over")
        over.setInput(0, shaded)
        over.setInput(1, col_up)
        comp = nuke.nodes.Switch(name="CompOrClouds")
        comp.setInput(0, col_up)
        comp.setInput(1, over)
        comp["which"].setExpression("parent.bg_found")

        # The layers.
        # depth.Z: the clouds' depth where they are solid (alpha 0.5 and over), the bg's depth
        # elsewhere ('depth out' comp), so land keeps its depth under clear sky; or the clouds'
        # depth alone ('depth out' clouds only, as before 0.54).
        zc = nuke.nodes.Copy(name="DepthClouds", from0="rgba.red", to0="depth.Z")
        zc.setInput(0, comp)
        zc.setInput(1, dep_up)
        zmask = nuke.nodes.Expression(name="DepthCloudMask", channel0="none", channel1="none", channel2="none",
                                      channel3="alpha", expr3="a >= 0.5 ? 1 : 0")
        zmask.setInput(0, col_up)
        zmix = nuke.nodes.Keymix(name="DepthOverBg", channels="depth", maskChannel="rgba.alpha")
        zmix.setInput(0, comp)
        zmix.setInput(1, zc)
        zmix.setInput(2, zmask)
        z = nuke.nodes.Switch(name="Layer_DepthZ")
        z.setInput(0, zmix)
        z.setInput(1, zc)
        z["which"].setExpression("parent.depth_out")
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
        cw = nuke.nodes.Copy(name="Layer_CloudShadow")
        for j, c in enumerate(("red", "green", "blue")):
            cw["from%d" % j].setValue("rgba." + c)
            cw["to%d" % j].setValue("cloud_shadow." + c)
        cw.setInput(0, ck)
        cw.setInput(1, shadow_up)
        # The sun map of all the layers together (cloud_sunmap), stretched over the frame: the
        # clouds' optical depth towards the sun from the ground up, with its altitude moments.
        # EzCloudShafts reads it to cast rays and ground shadows from the real volumes.
        sm_all = nuke.nodes.Merge2(name="SunMap_All12", operation="plus")
        sm_all.setInput(0, sunmaps[0])
        sm_all.setInput(1, sunmaps[1])
        sm_all3 = nuke.nodes.Merge2(name="SunMap_All3", operation="plus")
        sm_all3.setInput(0, sm_all)
        sm_all3.setInput(1, sunmaps[2])
        sm_up = up("SunMapUp", sm_all3, frame=False)
        cm = nuke.nodes.Copy(name="Layer_CloudSunMap")
        for j, c in enumerate(("red", "green", "blue")):
            cm["from%d" % j].setValue("rgba." + c)
            cm["to%d" % j].setValue("cloud_sunmap." + c)
        cm.setInput(0, cw)
        cm.setInput(1, sm_up)
        cm["disable"].setExpression("!parent.sun_map_out")
        layers = nuke.nodes.Switch(name="BreakoutOrNot")
        layers.setInput(0, z)
        layers.setInput(1, cm)
        layers["which"].setExpression("parent.breakout")
        fw = nuke.nodes.Copy(name="Layer_Forward", from0="rgba.red", to0="forward.u",
                             from1="rgba.green", to1="forward.v")
        fw.setInput(0, layers)
        fw.setInput(1, mv_up[1])
        bw = nuke.nodes.Copy(name="Layer_Backward", from0="rgba.red", to0="backward.u",
                             from1="rgba.green", to1="backward.v")
        bw.setInput(0, fw)
        bw.setInput(1, mv_up[-1])
        mvs = nuke.nodes.Switch(name="MotionOrNot")
        mvs.setInput(0, layers)
        mvs.setInput(1, bw)
        mvs["which"].setExpression("parent.motion_vectors")
        layers = mvs

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
        shadow_view = nuke.nodes.Copy(name="View_Shadow", channels="rgba")
        shadow_view.setInput(0, layers)
        shadow_view.setInput(1, shadow_up)
        # Variations: the layer shown, tiled (by the kernels), over a plain sky blue rather than
        # the bg (the plate showing through made the tiles hard to judge), each tile numbered as
        # 'use number' counts them (1 top left, reading order).
        var_view = nuke.nodes.Expression(name="View_VariationsSky", label="clouds over a plain sky")
        for j, (e, sky) in enumerate((("r", 0.14), ("g", 0.22), ("b", 0.42))):
            var_view["expr%d" % j].setValue("%s+(1-a)*%g" % (e, sky))
        var_view["expr3"].setValue("1")
        var_view.setInput(0, clouds_view)
        for k in range(1, 10):
            col, row = (k - 1) % 3, (k - 1) // 3
            t = nuke.nodes.Text2(name="View_VariationNumber%d" % k)
            t["message"].setValue(str(k))
            for j, e in enumerate(("width*%d/3+height/60" % col, "height*(1-%d/3)" % (row + 1),
                                   "width*%d/3" % (col + 1), "height*(1-%d/3)-height/60" % row)):
                t["box"].setExpression(e, j)
            t["xjustify"].setValue("left")
            t["yjustify"].setValue("top")
            # Big enough to read on a 4K plate at a fit-to-viewer zoom, and as wide as tall on
            # an anamorphic plate once the viewer unsqueezes it.
            t["font_size"].setExpression("height/9")
            t["global_font_scale"].setValue(1)
            if t.knob("font_width") is not None:
                t["font_width"].setExpression("font_size / max(parent.bg_pixel_aspect, 0.01)")
            t["color"].setValue([1, 0.85, 0.3, 1])
            t.setInput(0, var_view)
            var_view = t
        view = nuke.nodes.Switch(name="ViewOutput")
        for j, n in enumerate((layers, clouds_view, sun_view, depth_view, var_view, shadow_view)):
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
    ("Inputs", 0x4a5a6aff, r"(bg|camera|atmos|sun|map|box\d|holdout|add|RootFormat|FormatSource|MapNone|MapSource|WorkClear|WorkBlack|FormatBox|WorkArea|WorkFormat|DepthEnsure|DepthSource|DepthWork|SunMapFormat|LightGridFormat)"),
    ("Sun maps", 0x3a5a4aff, r"(L\d_SunMap)"),
    ("Depth ramp graphs (UI only)", 0x444444ff, r"(L\d_DepthRamp)"),
    ("Clouds (all layers in one march)", 0x4a5a6aff, r"(Clouds_.*)"),
    ("Cirrus sheet", 0x5a6a7aff, r"(Sheet_.*)"),
    ("Back to full size", 0x444444ff, r"(ColorUp.*|SunUp.*|DepthUp.*|ShadowUp.*|FwdUp.*|BwdUp.*|FwdScale|BwdScale|ToneScale|ToneColor|ToneSun|SunMapUp)"),
    ("Shadows", 0x4a4a3aff, r"(Shadow_.*|SunMap_All.*)"),
    ("Comp", 0x3a4a6aff, r"(CompOver|CompOrClouds)"),
    ("Layers", 0x6a4a4aff, r"(Layer_.*|SkyPart|BreakoutOrNot|MotionOrNot)"),
    ("Views", 0x5a4a6aff, r"(View_.*|ViewOutput)"),
    ("Output", 0x6a4a4aff, r"(Output\d*)"),
]
LABELS = {"FormatSource": "bg plugged in", "CompOrClouds": "bg plugged in", "BreakoutOrNot": "breakout", "MotionOrNot": "motion vectors",
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
