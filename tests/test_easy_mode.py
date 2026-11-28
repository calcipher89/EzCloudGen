"""The Easy tab without Nuke: python/easy_mode.py against a stand-in node.

    python3 tests/test_easy_mode.py
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python"))


class Knob(object):
    def __init__(self, v):
        self.v = v

    def value(self):
        return self.v

    def getValue(self):
        return self.v

    def setValue(self, v):
        self.v = v


class Node(dict):
    def knob(self, k):
        return self.get(k)


def main():
    sys.modules["nuke"] = types.ModuleType("nuke")
    import cloud_types
    ns = {}
    with open(os.path.join(HERE, "..", "python", "easy_mode.py")) as f:
        exec(f.read(), ns)
    n = Node()
    for i, t in ((1, "Cumulus"), (2, "Stratocumulus"), (3, "Cirrus")):
        v = cloud_types.full(t)
        v["cover"] = cloud_types.preset_cover(t)
        for k in ns["LOOK"]:
            n["l%d_%s" % (i, k)] = Knob(v.get(k, 1.0))
    for k, v in (("cover", 0.5), ("scale_km", 6.0), ("fibre_size", 150.0), ("edge", 0.6), ("opacity", 0.3),
                 ("fibres", 0.8), ("ambient", 1.0)):
        n["sheet_" + k] = Knob(v)
    n["sun_intensity"] = Knob(1.0)
    n["easy_base"] = Knob("")
    n["easy_layer"] = Knob(0)
    for k, v in ns["SLIDERS"]:
        n[k] = Knob(v)
    start = dict((k, kn.v) for k, kn in n.items() if k.startswith("l"))
    ok = True

    def check(what, got, want, tol=1e-6):
        good = all(abs(a - b) <= tol for a, b in zip(got, want))
        print("%-44s %s %s" % (what, [round(x, 4) for x in got], "ok" if good else "WANT %s" % (want,)))
        return good

    c0 = n["l1_cover"].v
    n["easy_cover"].v = 0.2
    ns["on_knob"](n, "easy_cover")
    ok &= check("cover +0.2 on layer 1", [n["l1_cover"].v], [c0 + 0.2])
    n["easy_size"].v = 2.0
    ns["on_knob"](n, "easy_size")
    ok &= check("size x2: scale, detail x sqrt2", [n["l1_scale_km"].v, n["l1_detail_size"].v],
                [start["l1_scale_km"] * 2, start["l1_detail_size"] * 2 ** 0.5])
    n["easy_lit"].v = 1.0
    ns["on_knob"](n, "easy_lit")
    ok &= check("lit +1 doubles sun intensity", [n["sun_intensity"].v], [2.0])
    # Switch to layer 2: its own sliders (neutral), layer 1 keeps its changes.
    n["easy_layer"].v = 1
    ns["on_knob"](n, "easy_layer")
    ok &= check("layer 2 sliders start neutral", [n["easy_cover"].v, n["easy_size"].v], [0.0, 1.0])
    n["easy_underside"].v = 1.0
    ns["on_knob"](n, "easy_underside")
    ok &= check("underside +1 on layer 2", [n["l2_sky_occlusion"].v, n["l2_ambient"].v],
                [min(start["l2_sky_occlusion"] + 0.8, 2.0), start["l2_ambient"] * 2 ** -0.5])
    ok &= check("layer 1 untouched by layer 2's sliders", [n["l1_cover"].v], [c0 + 0.2])
    n["easy_layer"].v = 0
    ns["on_knob"](n, "easy_layer")
    ok &= check("back on layer 1: its sliders return", [n["easy_cover"].v, n["easy_size"].v], [0.2, 2.0])
    # Everything neutral: every knob back to where it started.
    for k, v in ns["SLIDERS"]:
        n[k].v = v
        ns["on_knob"](n, k)
    n["easy_layer"].v = 1
    ns["on_knob"](n, "easy_layer")
    n["easy_underside"].v = 0.0
    ns["on_knob"](n, "easy_underside")
    now = dict((k, kn.v) for k, kn in n.items() if k.startswith("l"))
    ok &= check("all neutral: knobs as they started", [now[k] - start[k] for k in start], [0.0] * len(start), 1e-9)
    # A hand edit rebases and centres.
    n["easy_layer"].v = 0
    ns["on_knob"](n, "easy_layer")
    n["easy_softness"].v = 0.5
    ns["on_knob"](n, "easy_softness")
    n["l1_edge"].v = 0.3
    ns["on_knob"](n, "l1_edge")
    ok &= check("hand edit centres softness, keeps the edit", [n["easy_softness"].v, n["l1_edge"].v], [0.0, 0.3])
    # The cirrus sheet (4th entry): its own knobs, layer 1 left alone.
    l1 = dict((k, kn.v) for k, kn in n.items() if k.startswith("l1_"))
    n["easy_layer"].v = 3
    ns["on_knob"](n, "easy_layer")
    n["easy_cover"].v = -0.2
    ns["on_knob"](n, "easy_cover")
    n["easy_softness"].v = 1.0
    ns["on_knob"](n, "easy_softness")
    n["easy_wisps"].v = 0.5
    ns["on_knob"](n, "easy_wisps")
    ok &= check("sheet: cover -0.2, edge x2, opacity thinner, fibres +0.2",
                [n["sheet_cover"].v, n["sheet_edge"].v, n["sheet_opacity"].v, n["sheet_fibres"].v],
                [0.3, 1.2, 0.3 * 2 ** -0.7, 1.0])
    ok &= check("sheet sliders leave layer 1 alone", [n[k].v - v for k, v in l1.items()], [0.0] * len(l1), 1e-9)
    n["sheet_cover"].v = 0.7
    ns["on_knob"](n, "sheet_cover")
    ok &= check("sheet hand edit centres the sliders", [n["easy_cover"].v, n["easy_softness"].v], [0.0, 0.0])
    # Starting look: layer 1 deck 1900 m above the camera, cover 0.3, sliders centred on it.
    class Matrix(Knob):
        def getValue(self, i=None):
            return self.v[i] if i is not None else self.v
    m = [0.0] * 16
    m[7] = 41000.0  # 4100 m in decimetres
    n["cam_world_matrix"] = Matrix(m)
    n["ground_height"] = Knob(0.0)
    n["scene_scale"] = Knob(0.1)
    n["l1_base"] = Knob(1400.0)
    n["l1_enable"] = Knob(False)
    n["easy_look"] = Knob("Aerial Sunset")
    n["easy_layer"].v = 2
    n["easy_cover"].v = 0.4
    c1 = n["l1_cover"].v
    n["l1_enable"].v = True
    got = ns["apply_look"](n)
    ok &= check("look: base = camera + 1900, cover kept, layer 1 off", [n["l1_base"].v, n["l1_cover"].v, float(n["l1_enable"].v)],
                [6000.0, c1, 0.0])
    ok &= check("look: easy layer 1, sliders centred", [n["easy_layer"].v, n["easy_cover"].v], [0, 0.0])
    ok &= (got == "Aerial Sunset")
    n["easy_cover"].v = 0.1
    ns["on_knob"](n, "easy_cover")
    ok &= check("look: cover slider adds to the look", [n["l1_cover"].v], [c1 + 0.1])
    n["easy_cover"].v = 0.0
    ns["on_knob"](n, "easy_cover")
    ok &= check("look: sliders at neutral give the look exactly", [n["l1_cover"].v, n["l1_base"].v], [c1, 6000.0])
    m[7] = 0.0
    ns["apply_look"](n, "Aerial Sunset")
    ok &= check("look without a camera: base 300 + 1900", [n["l1_base"].v], [2200.0])
    n["l1_enable"].v = False
    ns["apply_look"](n, "Aerial Day")
    ok &= check("Aerial Day without a camera: on, base 300 + 1200", [float(n["l1_enable"].v), n["l1_base"].v], [1.0, 1500.0])
    ok &= (ns["apply_look"](n, "Nope") is None)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
