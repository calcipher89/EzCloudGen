"""Easy tab: a few artist-language sliders over one layer's knobs (the 'easy layer').

build_group.py stores this file base64-encoded in the hidden tool_code knob; knobChanged runs
it from there, so the node needs no Python module at the studio. EzMatch runs it the same way
and calls apply_easy / rebase (and match_begin / match_end around a match), so it only ever
moves these sliders.

The sliders are relative to a base: the layer's knob values when the sliders were last centred,
kept per layer in the hidden easy_base knob (JSON) with the sliders' own values, so switching
'easy layer' brings each layer's sliders back. Every slider change rewrites the layer's knobs
from its base, so the layer tab always shows exactly what Easy did. Editing one of those knobs by
hand, or changing the layer's type, makes the new values the base and centres the sliders.
'lit' is global (the sun intensity) and stays where it is. The fourth 'easy layer' is the cirrus
sheet (knobs sheet_*), with its own mapping (apply_sheet).
"""
import json
import math

import nuke

# (knob, neutral)
SLIDERS = [("easy_cover", 0.0), ("easy_size", 1.0), ("easy_softness", 0.0), ("easy_wisps", 0.0),
           ("easy_underside", 0.0), ("easy_lit", 0.0)]
EASY_KNOBS = [name for name, _ in SLIDERS] + ["easy_layer"]
LAYER_SLIDERS = [name for name, _ in SLIDERS if name != "easy_lit"]
# The layer knobs (without the lN_ prefix) the sliders write.
LOOK = ["cover", "scale_km", "cell_km", "lump_size", "detail_size", "edge", "sigma", "wisp_amount",
        "wisp_stretch", "sky_occlusion", "shadow_depth", "ambient"]
# The cirrus sheet's knobs (without sheet_) the sliders write.
SHEET_LOOK = ["cover", "scale_km", "fibre_size", "edge", "opacity", "fibres", "ambient"]
PREFIXES = ("l1_", "l2_", "l3_", "sheet_")
GLOBAL = ["sun_intensity"]


class _Busy(object):
    """While the sliders set knobs, knobChanged leaves them alone."""

    def __enter__(self):
        self.was = getattr(nuke, "_ezcloudgen_busy", False)
        nuke._ezcloudgen_busy = True

    def __exit__(self, *args):
        nuke._ezcloudgen_busy = self.was


def busy():
    return getattr(nuke, "_ezcloudgen_busy", False)


def layer(n):
    """The easy layer's knob prefix, 'l1_' .. 'l3_', or 'sheet_' for the cirrus sheet."""
    return PREFIXES[min(int(n["easy_layer"].getValue()), 3)]


def look(p):
    return SHEET_LOOK if p == "sheet_" else LOOK


def _all(n):
    try:
        return json.loads(n["easy_base"].value() or "{}")
    except ValueError:
        return {}


def _save(n, d):
    with _Busy():
        n["easy_base"].setValue(json.dumps(d))


def _lit_base(n, d):
    if "sun_intensity" not in d:
        d["sun_intensity"] = n["sun_intensity"].value() / 2.0 ** n["easy_lit"].value()
    return d["sun_intensity"]


def rebase(n, centre=True, p=None):
    """Make the easy layer's knob values its base and centre its sliders ('lit' stays)."""
    p = p or layer(n)
    d = _all(n)
    d[p] = {"base": dict((k, n[p + k].value()) for k in look(p) if n.knob(p + k) is not None),
            "sliders": dict((name, neutral) for name, neutral in SLIDERS if name != "easy_lit")}
    d["sun_intensity"] = n["sun_intensity"].value() / 2.0 ** n["easy_lit"].value()
    _save(n, d)
    if centre:
        with _Busy():
            for name, neutral in SLIDERS:
                if name != "easy_lit":
                    n[name].setValue(neutral)


def show_layer(n):
    """'easy layer' changed: bring that layer's sliders back (or start it from its knobs)."""
    p = layer(n)
    d = _all(n)
    if p not in d:
        rebase(n, p=p)
        return
    with _Busy():
        for name, neutral in SLIDERS:
            if name != "easy_lit":
                n[name].setValue(d[p]["sliders"].get(name, neutral))


def apply_easy(n):
    """Rewrite the easy layer's knobs (and the sun intensity) from the base and the sliders."""
    p = layer(n)
    d = _all(n)
    if p not in d:
        # Never set up: the knobs still hold the look the slider just moved away from.
        keep = dict((name, n[name].value()) for name in LAYER_SLIDERS)
        rebase(n, centre=False, p=p)
        d = _all(n)
        d[p]["sliders"] = keep
    e = dict((name, n[name].value()) for name, _ in SLIDERS)
    d[p]["sliders"] = dict((name, e[name]) for name in LAYER_SLIDERS)
    b = d[p]["base"]
    lit = _lit_base(n, d)
    _save(n, d)

    def put(k, v, lo=None, hi=None):
        if n.knob(p + k) is None or k not in b:
            return
        if lo is not None:
            v = max(lo, v)
        if hi is not None:
            v = min(hi, v)
        n[p + k].setValue(v)

    size = max(e["easy_size"], 1e-3)
    s = max(-1.0, min(1.0, e["easy_softness"]))
    w = max(-1.0, min(1.0, e["easy_wisps"]))
    u = max(-1.0, min(1.0, e["easy_underside"]))
    if p == "sheet_":
        with _Busy():
            apply_sheet(put, b, e["easy_cover"], size, s, w, u)
            n["sun_intensity"].setValue(lit * 2.0 ** e["easy_lit"])
        return
    with _Busy():
        # Cover: more or less of the sky hidden, in the type's visible-cover units.
        put("cover", b.get("cover", 0.5) + e["easy_cover"], 0.0, 1.0)
        # Size: the cloud shapes and their cells and lumps; the billows grow more slowly.
        for k in ("scale_km", "cell_km", "lump_size"):
            put(k, b.get(k, 1.0) * size)
        put("detail_size", b.get("detail_size", 100.0) * math.sqrt(size))
        # Softness: softer, thinner edges (or harder, denser ones).
        put("edge", b.get("edge", 0.1) * 4.0 ** s, 0.01, 0.5)
        put("sigma", b.get("sigma", 0.04) * 2.0 ** -s, 0.0005, 0.1)
        # Wisps: fine wisps eating the edges, combed along the wind as it goes up.
        put("wisp_amount", b.get("wisp_amount", 0.0) + 0.6 * w, 0.0, 1.0)
        put("wisp_stretch", b.get("wisp_stretch", 1.0) * 4.0 ** max(w, 0.0), 1.0, 12.0)
        # Underside: darker, deeper undersides and folds (or lighter, glowing ones).
        put("sky_occlusion", b.get("sky_occlusion", 1.0) + 0.8 * u, 0.0, 2.0)
        put("shadow_depth", b.get("shadow_depth", 0.0) + 0.5 * u, 0.0, 1.0)
        put("ambient", b.get("ambient", 1.0) * 2.0 ** (-0.5 * u), 0.0, 3.0)
        # Lit: the sunlit side's brightness, in stops (the whole node's sun).
        n["sun_intensity"].setValue(lit * 2.0 ** e["easy_lit"])


def apply_sheet(put, b, cover, size, s, w, u):
    """The sliders on the cirrus sheet."""
    put("cover", b.get("cover", 0.5) + cover, 0.0, 1.0)
    put("scale_km", b.get("scale_km", 4.0) * size)
    put("fibre_size", b.get("fibre_size", 150.0) * math.sqrt(size))
    # Softness: softer patch edges and a thinner, more veil-like sheet (or crisper, denser).
    put("edge", b.get("edge", 0.6) * 2.0 ** s, 0.0, 2.0)
    put("opacity", b.get("opacity", 0.5) * 2.0 ** (-0.7 * s), 0.0, 2.0)
    # Wisps: more of the sheet in strands.
    put("fibres", b.get("fibres", 0.8) + 0.4 * w, 0.0, 1.0)
    # Underside: a darker side away from the sun (less sky light).
    put("ambient", b.get("ambient", 1.0) * 2.0 ** (-0.7 * u), 0.0, 3.0)


# Starting looks: layer 1 knobs set before a match ('apply look' on the Easy tab, or EzMatch's
# 'apply starting look'). "base_above_camera" puts the deck's base that many metres above the
# camera, so an aerial camera never sees a flat strip of cloud tops along the horizon. Aerial
# Sunset adds no cloud (layer 1 off): turning layer 1 on by hand starts from a deck above the camera.
LOOKS = {"Aerial Sunset": {"enable": False, "base_above_camera": 1900.0},
         # A fair-weather day from high above: layer 1 (Cumulus by default; its type is kept) on,
         # its base 1.7 km above the camera so the cumulus show in the sky, not as a strip of tops
         # along the horizon (planner r19, our demo fair-weather render: camera 4300 m, base 6000 m).
         "Aerial Day": {"enable": True, "base_above_camera": 1200.0}}   # r19 pass 3 (was 1700)
LOOK_NAMES = sorted(LOOKS)


def camera_height(n):
    """The camera's height above the ground in metres (300 m without a camera matrix)."""
    try:
        y = n["cam_world_matrix"].getValue(7)
        h = (y - n["ground_height"].value()) * (n["scene_scale"].value() or 0.1)
    except Exception:
        return 300.0
    return h if h > 0.0 else 300.0


def apply_look(n, name=None):
    """Set a starting look's layer 1 knobs, then centre the Easy sliders on it (layer 1)."""
    name = name or (n["easy_look"].value() if n.knob("easy_look") is not None else None)
    if name not in LOOKS:
        return None
    p = "l1_"
    with _Busy():
        if n.knob("easy_layer") is not None:
            n["easy_layer"].setValue(0)
        for k, v in LOOKS[name].items():
            if k == "base_above_camera":
                n[p + "base"].setValue(max(0.0, min(12000.0, camera_height(n) + v)))
            elif n.knob(p + k) is not None:
                n[p + k].setValue(v)
    rebase(n, p=p)
    return name


def match_begin(n):
    """Before a match: draft quality at Quarter resolution, so each try renders fast."""
    keep = dict((k, n[k].value()) for k in ("render_preset", "resolution", "quality", "edge_steps", "sampling"))
    d = _all(n)
    d["_match_keep"] = keep
    _save(n, d)
    with _Busy():
        # The draft preset's values, at Quarter (the render preset menu then reads 'custom';
        # match_end puts it back).
        n["quality"].setValue(0.5)
        n["edge_steps"].setValue(2.0)
        n["sampling"].setValue("Low")
        n["resolution"].setValue("Quarter")


def match_end(n):
    """After a match: the render settings as they were."""
    d = _all(n)
    keep = d.pop("_match_keep", None)
    _save(n, d)
    if keep:
        with _Busy():
            for k in ("resolution", "quality", "edge_steps", "sampling", "render_preset"):
                n[k].setValue(keep[k])


def on_knob(n, k):
    """knobChanged, for a knob the Easy tab looks after."""
    if busy():
        return
    if k == "easy_layer":
        show_layer(n)
    elif k in EASY_KNOBS:
        apply_easy(n)
    elif any(k.startswith(q) and q == layer(n) and (k[len(q):] in look(q) or k[len(q):] == "type") for q in PREFIXES):
        # Tuned by hand, or a new type: that becomes the sliders' starting point.
        rebase(n)
    elif k == "sun_intensity":
        d = _all(n)
        d["sun_intensity"] = n["sun_intensity"].value() / 2.0 ** n["easy_lit"].value()
        _save(n, d)
