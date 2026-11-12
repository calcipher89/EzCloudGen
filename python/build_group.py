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

VERSION = "0.11.0"
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
    ("sky_occlusion", "sky occlusion", "How much the cloud above darkens the sky light below it: deeper "
                                       "undersides and folds. Lower it for tall storms and thick overcast, "
                                       "which go flat grey under their own mass.", 0, 2),
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
VOL_ONLY = ["vol_divider", "vol_shape", "vol_position", "vol_rotate", "vol_size", "place", "place_km", "make_box",
            "release_box", "lumps",
            "lump_size"]

LAYERS = {"cloud": ["red", "green", "blue", "alpha"],
          "cloud_sun": ["red", "green", "blue"],
          "cloud_sky": ["red", "green", "blue"],
          "cloud_shadow": ["red", "green", "blue"]}


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
    """Python expression: one channel of a pixel of the EzAtmosScatter's measured HDRI light."""
    return py(FIND_ATMOS +
              "l = nuke.toNode(a.fullName() + '.Light') if a is not None else None\n"
              "ret = l.sample('%s', %g, 0.5) if l is not None else %s\n" % (channel, pixel + 0.5, fallback))


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


# ---- Bake ---------------------------------------------------------------------------------

# A fingerprint of the settings that change the picture (every knob but the bake's own, the view
# and the panel's), to tell when a bake is out of date. Inputs (camera moves, bg) aren't in it.
BAKE_SKIP = ("bake_", "view", "preview", "use_bake", "variation", "show_variations", "next_variations",
             "selected", "xpos", "ypos", "label", "note_font", "tile_color", "gl_color", "hide_input",
             "postage_stamp", "cached", "dope_sheet", "help", "onCreate", "knobChanged", "updateUI",
             "icon", "indicators", "panel", "box_lib", "version")
BAKE_HASH = ("import hashlib\n"
             "n = nuke.thisNode()\n"
             "parts = []\n"
             "for name in sorted(n.knobs()):\n"
             "    if name.startswith(%r):\n"
             "        continue\n"
             "    k = n[name]\n"
             "    if k.Class() in ('Tab_Knob', 'Text_Knob', 'PyScript_Knob'):\n"
             "        continue\n"
             "    parts.append(name + '=' + k.toScript())\n"
             "h = hashlib.md5('\\n'.join(parts).encode()).hexdigest()\n" % (BAKE_SKIP,))
BAKE_NOW = (BAKE_HASH +
            "import os\n"
            "w = n.node('BakeWrite')\n"
            "path = w['file'].evaluate()\n"
            "if path:\n"
            "    d = os.path.dirname(path)\n"
            "    if not os.path.isdir(d):\n"
            "        os.makedirs(d)\n"
            "view = n['view'].value()\n"
            "n['view'].setValue('Comp')\n"
            "n['use_bake'].setValue(False)\n"
            "try:\n"
            "    nuke.execute(w, int(n['bake_first'].value()), int(n['bake_last'].value()))\n"
            "finally:\n"
            "    n['view'].setValue(view)\n"
            "n['bake_hash'].setValue(h)\n"
            "n.node('BakeRead')['reload'].execute()\n"
            "n['use_bake'].setValue(True)\n")
# A String_Knob can't hold an expression (and would show TCL as text), so knobChanged writes the
# status after every change (setting bake_hash after a bake counts too).
# Its own namespace: knob scripts share one, and its n, k, s... would clobber a running button's.
BAKE_STATUS_UPDATE = ("if k.name() != 'bake_status':\n    exec(%r, {'nuke': nuke})\n" % (
    BAKE_HASH + "s = 'no bake yet' if not n['bake_hash'].value() else "
                "('up to date' if h == n['bake_hash'].value() else "
                "'OUT OF DATE: settings changed since the bake, bake again')\n"
                "if n['bake_status'].value() != s:\n"
                "    n['bake_status'].setValue(s)\n"))


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
            "elif k.name() == 'showPanel':\n"
            "    layers = ['l1_', 'l2_', 'l3_']\n"
            "for p in layers:\n"
            "    vol = n[p + 'volume'].value() > 0.5\n"
            "    for name in %r:\n"
            "        n[p + name].setVisible(not vol)\n"
            "    for name in %r:\n"
            "        n[p + name].setVisible(vol)\n" % (table, BOX_INPUT, DECK_ONLY, VOL_ONLY)) + BAKE_STATUS_UPDATE


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
            "Variations: nine seeds of one layer side by side (see 'variations'). "
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

    add(g, nuke.Text_Knob("bake_divider", "bake"))
    k = add(g, nuke.File_Knob("bake_folder", "bake folder"),
            "Where 'bake now' writes the frames: <folder>/<script>/<node>/<script>_<node>.####.exr. TCL works, "
            "e.g. [getenv JOB].")
    k.setValue("/data/jobs/[getenv JOB]/sequences/[getenv SEQ]/shots/[getenv SHOT]/nuke/comp/ezCloudGen/cache")
    k = add(g, nuke.Int_Knob("bake_first", "frames"), "First frame to bake.")
    k.setValue(int(nuke.root()["first_frame"].value()))
    k = add(g, nuke.Int_Knob("bake_last", ""), "Last frame to bake.")
    k.setValue(int(nuke.root()["last_frame"].value()))
    k.clearFlag(nuke.STARTLINE)
    add(g, nuke.PyScript_Knob("bake_range_here", "script range",
                              "n = nuke.thisNode()\n"
                              "n['bake_first'].setValue(int(nuke.root()['first_frame'].value()))\n"
                              "n['bake_last'].setValue(int(nuke.root()['last_frame'].value()))\n"),
        "Sets the frames to the script's frame range.")
    g["bake_range_here"].clearFlag(nuke.STARTLINE)
    add(g, nuke.PyScript_Knob("bake_now", "bake now", BAKE_NOW),
        "Renders the Comp (with every layer the node outputs) to the bake folder, then plays it back from "
        "disk ('use bake' on): fast playback, and no Blink on the farm.")
    k = add(g, nuke.Boolean_Knob("use_bake", "use bake"),
            "Plays the Comp view back from the baked frames instead of rendering. The other views still render.")
    k.clearFlag(nuke.STARTLINE)
    k = add(g, nuke.String_Knob("bake_status", "status"), "Whether the settings changed since the bake.")
    k.setValue("no bake yet")  # kept current by knobChanged (BAKE_STATUS_UPDATE)
    k.setEnabled(False)
    hidden(g, nuke.String_Knob("bake_hash"))

    add(g, nuke.Text_Knob("scene_divider", "scene"))
    add(g, nuke.Double_Knob("scene_scale", "units to metres"),
        "Scene units to metres: 0.1 for decimetres.").setValue(0.1)
    add(g, nuke.Double_Knob("ground_height", "ground height"),
        "Height of the ground in scene units; the camera's height above it places it under the clouds."
        ).setValue(0)
    g["ground_height"].setRange(-10000, 10000)

    add(g, nuke.Text_Knob("bg_depth_divider", "bg depth"))
    add(g, nuke.Boolean_Knob("occlude", "hide behind bg"),
        "Uses the bg's depth so the clouds go behind mountains and buildings, and casts their shadows "
        "onto it (cloud_shadow, and the Shadow view). Without a depth channel on the bg, nothing is "
        "hidden.").setValue(True)
    c = add(g, nuke.Channel_Knob("depth_channel", "depth"), "The bg channel holding its depth.")
    c.setValue("depth.Z")
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

    k = hidden(g, nuke.Multiline_Eval_String_Knob("box_lib", "box lib"))
    k.setValue(BOX_LIB)
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
    k.setExpression("(resolution==0 ? 1 : resolution==1 ? 0.5 : 0.25) * (preview ? 0.5 : 1)")
    k = hidden(g, nuke.Double_Knob("time_s"))
    k.setExpression("frame / max(root.fps, 1)")

    g["knobChanged"].setValue(knob_changed())


# ---- The nodes inside --------------------------------------------------------------------

def blink(name, output, src, cmap, zin, smap, layer, source_file, step=1):
    n = compiled(name, source_file)
    n.setInput(0, src)
    n.setInput(1, cmap)
    n.setInput(2, zin)
    n.setInput(3, smap)
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
    n[k + "quality"].setExpression("parent.quality * (parent.preview ? 0.5 : 1)")
    n[k + "samples"].setExpression("parent.preview ? 1 : parent.samples")
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
    # A 3D node in the layer's box input sets the centre, axes and size; else the knobs do.
    bf = p + "box_found"
    n[k + "vol_center"].setExpression("%s ? %sbox_center.x : %svol_position.x" % (bf, p, p), 0)
    n[k + "vol_center"].setExpression("%s ? %sbox_center.y : %svol_position.y + %svol_size.y / 2 / "
                                      "max(parent.scene_scale, 1e-6)" % (bf, p, p, p), 1)
    n[k + "vol_center"].setExpression("%s ? %sbox_center.z : %svol_position.z" % (bf, p, p), 2)
    n[k + "vol_axes"].setExpression(bf)
    for j, c in enumerate("xyz"):
        n[k + "vol_rotate"].setExpression("%svol_rotate.%s" % (p, c), j)
        n[k + "vol_size"].setExpression("%s ? %sbox_size.%s : %svol_size.%s" % (bf, p, c, p, c), j)
        for a in "xyz":
            n[k + "vol_axis_" + a].setExpression("%sbox_axis_%s.%s" % (p, a, c), j)
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
    # Motion vectors: the camera, wind and volume on the other frame (step frames away).
    which = "next" if step > 0 else "prev"
    for r, idx in enumerate(rows):
        for j, m in enumerate(idx):
            n[k + "other_row%d" % r].setExpression("parent.cam_%s_matrix.%d" % (which, m), j)
    for j, m in enumerate((3, 7, 11)):
        n[k + "other_position"].setExpression("parent.cam_%s_matrix.%d" % (which, m), j)
    n[k + "other_focal"].setExpression("parent.cam_%s_focal" % which)
    n[k + "other_haperture"].setExpression("parent.cam_%s_haperture" % which)
    t_other = "(parent.time_s + (%d) / max(root.fps, 1))" % step
    n[k + "other_offset"].setExpression("-%swind_speed * %s * sin(radians(%swind_deg))" % (p, t_other, p), 0)
    n[k + "other_offset"].setExpression("%swind_speed * %s * cos(radians(%swind_deg))" % (p, t_other, p), 1)
    f_other = "(frame + (%d))" % step
    bc = "%sbox_center_%s" % (p, which)
    n[k + "other_vol_center"].setExpression("%s ? %s.x : %svol_position.x%s" % (bf, bc, p, f_other), 0)
    n[k + "other_vol_center"].setExpression("%s ? %s.y : %svol_position.y%s + %svol_size.y / 2 / "
                                            "max(parent.scene_scale, 1e-6)" % (bf, bc, p, f_other, p), 1)
    n[k + "other_vol_center"].setExpression("%s ? %s.z : %svol_position.z%s" % (bf, bc, p, f_other), 2)
    n[k + "occlude"].setExpression("parent.occlude && parent.bg_found")
    n[k + "depth_mode"].setExpression("parent.depth_mode")
    n[k + "sky_depth"].setExpression("parent.sky_depth * 1000 / max(parent.scene_scale, 1e-6)")
    # The shadows of the layers above, from the sun (only the colour and sun passes read them).
    n[k + "use_sun_map"].setExpression("parent.layer_shadows && %d < 2" % output)
    n[k + "sun_map_size"].setValue(SUN_MAP_SIZE)
    n["disable"].setExpression(DISABLE % (layer, layer - 1))
    return n


# The sun maps: SUN_MAP_RES square, covering the ground out to about SUN_MAP_SIZE metres at
# full detail (coarser further out, see sunMapUV in the kernel).
SUN_MAP_RES = 768
SUN_MAP_SIZE = 10000.0

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
    # The node says when it is a quick preview or played back from a bake.
    g["label"].setValue('[expr {[value preview] ? "PREVIEW" : ""}] [expr {[value use_bake] ? "(baked)" : ""}]')
    with g:
        bg = nuke.nodes.Input(name="bg")
        cam = nuke.nodes.Input(name="camera")
        atm = nuke.nodes.Input(name="atmos")
        sun = nuke.nodes.Input(name="sun")
        mp = nuke.nodes.Input(name="map")
        boxes = [nuke.nodes.Input(name="box%d" % i) for i in (1, 2, 3)]
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
        work = nuke.nodes.Reformat(name="WorkFormat", type="scale", filter="Impulse", black_outside=True)
        work["scale"].setExpression("parent.work_scale")
        work.setInput(0, black)
        # The map, or a black stand-in without one (the kernels need input 1 connected; use_map
        # is 0 then, so they never read it).
        nomap = nuke.nodes.Constant(name="MapNone", channels="rgba", color=0)
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
        zwork = nuke.nodes.Reformat(name="DepthWork", type="scale", filter="Impulse", black_outside=True)
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
            sm = blink("L%d_SunMap" % i, 5, smfmt, mp, smfmt, smfmt, i, source)
            k = KERNEL + "_"
            sm[k + "samples"].setExpression("1")
            sm[k + "tiles"].setExpression("1")
            sm["disable"].setExpression("(%s) || !parent.layer_shadows" % (DISABLE % (i, i - 1)))
            sunmaps.append(sm)
        above = []
        for i in range(1, 4):
            others = [sunmaps[j - 1] for j in range(1, 4) if j != i]
            m = nuke.nodes.Merge2(name="L%d_SunOthers" % i, operation="plus")
            m.setInput(0, others[0])
            m.setInput(1, others[1])
            above.append(m)

        colour, sunpart, depth, zkeys, shadows = [], [], [], [], []
        motion = {1: [], -1: []}
        for i in range(1, 4):
            sa = above[i - 1]
            colour.append(blink("L%d_Color" % i, 0, work, mp, zwork, sa, i, source))
            sp = blink("L%d_Sun" % i, 1, work, mp, zwork, sa, i, source)
            sp["disable"].setExpression("(%s) || !((parent.breakout && !parent.preview) || parent.view==2)"
                                        % (DISABLE % (i, i - 1)))
            sunpart.append(sp)
            sh = blink("L%d_Shadow" % i, 3, work, mp, zwork, smfmt, i, source)
            sh["disable"].setExpression("(%s) || !(parent.occlude && parent.bg_found) || "
                                        "!(((parent.breakout || parent.view==0) && !parent.preview) || parent.view==5)"
                                        % (DISABLE % (i, i - 1)))
            shadows.append(sh)
            for step, nm in ((1, "Fwd"), (-1, "Bwd")):
                mvn = blink("L%d_%s" % (i, nm), 4, work, mp, zwork, smfmt, i, source, step)
                mvn["disable"].setExpression("(%s) || !parent.motion_vectors || parent.preview" % (DISABLE % (i, i - 1)))
                mpm = nuke.nodes.Premult(name="L%d_%sPremult" % (i, nm), channels="rgb")
                mpm.setInput(0, mvn)
                motion[step].append(mpm)
            d = blink("L%d_Depth" % i, 2, work, mp, zwork, smfmt, i, source)
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

        # Motion vectors: stacked like depth (nearest layer wins), back to full size and full-size
        # pixels.
        mv_up = {}
        for step, nm in ((1, "Fwd"), (-1, "Bwd")):
            ms = stack(nm, motion[step])
            mu = nuke.nodes.Unpremult(name="%sUnpremult" % nm, channels="rgb")
            mu.setInput(0, ms)
            mr = nuke.nodes.Reformat(name="%sUp" % nm, type="to box", box_fixed=True, resize="distort",
                                     filter="Impulse", black_outside=True)
            mr["box_width"].setExpression("FormatSource.width")
            mr["box_height"].setExpression("FormatSource.height")
            mr.setInput(0, mu)
            mx = nuke.nodes.Multiply(name="%sScale" % nm, channels="rgb")
            mx["value"].setExpression("1 / max(parent.work_scale, 1e-6)")
            mx.setInput(0, mr)
            mv_up[step] = mx

        # Shadows: each layer lets 1 - s of the sun through, so together they block
        # 1 - (1 - a)(1 - b)(1 - c): a screen. A disabled layer passes black (no shadow).
        shm = nuke.nodes.Merge2(name="Shadow_Screen12", operation="screen", output="rgb")
        shm.setInput(0, shadows[0])
        shm.setInput(1, shadows[1])
        shm2 = nuke.nodes.Merge2(name="Shadow_Screen3", operation="screen", output="rgb")
        shm2.setInput(0, shm)
        shm2.setInput(1, shadows[2])
        shadow_up = up("ShadowUp", shm2)
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
        cw = nuke.nodes.Copy(name="Layer_CloudShadow")
        for j, c in enumerate(("red", "green", "blue")):
            cw["from%d" % j].setValue("rgba." + c)
            cw["to%d" % j].setValue("cloud_shadow." + c)
        cw.setInput(0, ck)
        cw.setInput(1, shadow_up)
        layers = nuke.nodes.Switch(name="BreakoutOrNot")
        layers.setInput(0, z)
        layers.setInput(1, cw)
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
        view = nuke.nodes.Switch(name="ViewOutput")
        # Variations: the comp, with only the layer shown, tiled (by the kernels).
        for j, n in enumerate((layers, clouds_view, sun_view, depth_view, layers, shadow_view)):
            view.setInput(j, n)
        view["which"].setExpression("parent.view")

        # Bake: the Comp to disk ('bake now' runs the Write), and played back from there.
        bake_file = ("[value parent.bake_folder]/[file rootname [file tail [value root.name]]]/[value parent.name]/"
                     "[file rootname [file tail [value root.name]]]_[value parent.name].####.exr")
        bw = nuke.nodes.Write(name="BakeWrite", file_type="exr", channels="all")
        bw["file"].setValue(bake_file)
        bw["datatype"].setValue("32 bit float")
        if bw.knob("create_directories"):
            bw["create_directories"].setValue(True)
        bw.setInput(0, view)
        br = nuke.nodes.Read(name="BakeRead")
        br["file"].setValue(bake_file)
        br["first"].setExpression("parent.bake_first")
        br["last"].setExpression("parent.bake_last")
        br["origfirst"].setExpression("parent.bake_first")
        br["origlast"].setExpression("parent.bake_last")
        br["on_error"].setValue("black")
        bs = nuke.nodes.Switch(name="BakeOrLive")
        bs.setInput(0, view)
        bs.setInput(1, br)
        bs["which"].setExpression("parent.use_bake && parent.view==0")
        out = nuke.nodes.Output(name="Output1")
        out.setInput(0, bs)

    # Inputs in the order nuke numbers them: by creation, bg 0, camera 1, atmos 2, sun 3, map 4.
    problems = node_layout.apply_nuke(g, modules=MODULES, labels=LABELS)
    for p in problems:
        print("layout: " + p)
    return g


MODULES = [
    ("Inputs", 0x4a5a6aff, r"(bg|camera|atmos|sun|map|box\d|RootFormat|FormatSource|MapNone|MapSource|WorkClear|WorkBlack|WorkFormat|DepthEnsure|DepthSource|DepthWork|SunMapFormat)"),
    ("Cloud layers", 0x3a5a4aff, r"(L\d_.*)"),
    ("Stack the layers", 0x4a5a6aff, r"(Color_Stack|Sun_Stack|Depth_Stack|DepthUnpremult|Fwd_Stack|Bwd_Stack|FwdUnpremult|BwdUnpremult)"),
    ("Back to full size", 0x444444ff, r"(ColorUp|SunUp|DepthUp|ShadowUp|FwdUp|BwdUp|FwdScale|BwdScale)"),
    ("Shadows", 0x4a4a3aff, r"(Shadow_.*)"),
    ("Comp", 0x3a4a6aff, r"(CompOver|CompOrClouds)"),
    ("Layers", 0x6a4a4aff, r"(Layer_.*|SkyPart|BreakoutOrNot|MotionOrNot)"),
    ("Views", 0x5a4a6aff, r"(View_.*|ViewOutput)"),
    ("Bake", 0x5a5a3aff, r"(BakeWrite|BakeRead|BakeOrLive)"),
    ("Output", 0x6a4a4aff, r"(Output\d*)"),
]
LABELS = {"FormatSource": "bg plugged in", "CompOrClouds": "bg plugged in", "BreakoutOrNot": "breakout", "MotionOrNot": "motion vectors",
          "ViewOutput": "view", "BakeOrLive": "use bake"}


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
