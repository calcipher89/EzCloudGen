"""Write examples/EzCloudGen_demo.nk: eight cloud setups showing every feature (placed volumes, a 3D box, a depth plate with motion vectors, a coverage map) through a moving shot camera.

Plain Python, no Nuke needed: each setup is a copy of the Nuke-built
groups/EzCloudGen_group.nk with its own knob values added to the group's knobs.

    python3 python/build_demo_nk.py
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))
import cloud_types  # noqa: E402

GROUP = os.path.join(ROOT, "groups", "EzCloudGen_group.nk")
OUT = os.path.join(ROOT, "examples", "EzCloudGen_demo.nk")


def sun(elev, az):
    import math
    e, a = math.radians(elev), math.radians(az)
    return "%.4f %.4f %.4f" % (math.cos(e) * math.sin(a), math.sin(e), -math.cos(e) * math.cos(a))


# (node name, Backdrop label, layers [(type, extra knobs)], group knobs)
SETUPS = [
    ("FairWeather", "Fair weather: cumulus + cirrus, sun high to the right",
     [("Cumulus", {}), None, ("Cirrus", {})],
     {"sun_direction": sun(35, 50)}),
    ("GoldenHour", "Golden hour, backlit: stratocumulus + altocumulus, gap toward the sun",
     [("Stratocumulus", {"coverage": 0.6}), ("Altocumulus", {}), None],
     {"sun_direction": sun(6, 8), "light_from": "Manual", "sun_color": "14 7 2.6",
      "sky_color": "0.22 0.16 0.2", "ground_color": "0.1 0.05 0.02", "haze_color": "1.8 0.95 0.45",
      "gap_amount": 0.7, "gap_size": 3}),
    ("Overcast", "Overcast: stratus under altostratus",
     [("Stratus", {"coverage": 0.85, "erosion": 0.55, "billow": 0.6, "sigma": 0.03, "vary": 0.4}), ("Altostratus", {}), None],
     {"sun_direction": sun(25, -30), "sun_intensity": 0.2, "sky_color": "0.3 0.31 0.33",
      "sky_intensity": 0.7, "haze_color": "0.7 0.71 0.73", "haze_distance": 30}),
    ("Towering", "Towering cumulus + cirrocumulus, afternoon",
     [("Cumulus Congestus", {}), None, ("Cirrocumulus", {})],
     {"sun_direction": sun(22, -60)}),
    ("HeroVolume", "Placed hero cumulus over a light cumulus deck, with a puff close by",
     [("Cumulus", {"coverage": 0.3}), ("Hero Cumulus", {"across": -1.5, "wisp_amount": 0.5}),
      ("Puff", {"across": 0.75, "place_km": 2.5})],
     {"sun_direction": sun(30, 40), "_box": 2}),
    ("StormFront", "Storm anvil far off, fog bank rolling in low, cirrus above",
     [("Storm Anvil", {"across": -3, "place_km": 30}), ("Fog Bank", {"place_km": 7}), ("Cirrus", {})],
     {"sun_direction": sun(18, -45), "sun_intensity": 0.8}),
    ("Mountains", "Mountains with depth: clouds go behind the ridge and shadow it",
     [("Cumulus", {"coverage": 0.5}), ("Hero Cumulus", {"across": 1.5, "place_km": 6}), ("Altocumulus", {})],
     {"sun_direction": sun(32, 75), "_bg": "Nridge", "motion_vectors": "true", "_vectorblur": True}),
    ("PaintedSky", "Coverage map: clouds only where the map is painted white (a disc left, a band right)",
     [("Cumulus", {"coverage": 0.35}), None, ("Cirrus", {"coverage": 0.3})],
     {"sun_direction": sun(28, 30), "map_frame": 1001, "_map": True}),
]


VOL_SHAPES = ["Ellipsoid", "Dome", "Anvil", "Box"]
BOXES = []  # (setup, layer, position, size, scene scale) of volumes linked to a Cube


def knob_value(k, v):
    """A cloud_types value as .nk text: menus by label, XYZ knobs as {x y z}."""
    if k == "vol_shape":
        return VOL_SHAPES[int(v)]
    if isinstance(v, (tuple, list)):
        return "{%s}" % " ".join("%g" % c for c in v)
    return v


def group_text():
    with open(GROUP) as f:
        text = f.read()
    start = text.index("Group {")
    end = text.index("end_group", start) + len("end_group")
    return text[start:end]


def box_links(name, layer):
    """Group knob lines that link a volume layer to its Cube, as 'make 3D box' does."""
    b = "%s_L%d_Box" % (name, layer)
    p = "l%d_" % layer
    return ['%sbox "%s"' % (p, b),
            "%svol_position {{%s.translate.x} {%s.translate.y-%s.scaling.y*%s.uniform_scale/2} {%s.translate.z}}"
            % (p, b, b, b, b, b),
            "%svol_rotate {{%s.rotate.x} {%s.rotate.y} {%s.rotate.z}}" % (p, b, b, b),
            "%svol_size {%s}" % (p, " ".join("{%s.scaling.%s*%s.uniform_scale*scene_scale}" % (b, a, b)
                                             for a in "xyz"))]


def box_node(name, layer, pos, size, scale, x, y):
    """The Cube the volume follows: translate is the volume's centre, scaling its size."""
    return "\n".join(["Cube {", " inputs 0", " display wireframe", " render_mode off", " rot_order YXZ",
                      " translate {%g %g %g}" % (pos[0], pos[1] + size[1] / scale / 2.0, pos[2]),
                      " scaling {%g %g %g}" % tuple(v / scale for v in size),
                      " name %s_L%d_Box" % (name, layer),
                      ' label "cloud volume: %s layer %d\\nmove, turn and scale me in 3D"' % (name, layer),
                      " tile_color 0x8fb3d9ff", " xpos %d" % x, " ypos %d" % y, "}"])


def instance(body, name, layers, knobs, x, y, inputs=4):
    lines = ["xpos %d" % x, "ypos %d" % y, "resolution Half", "samples 2"]
    for k, v in knobs.items():
        if k.startswith("_"):
            continue
        lines.append("%s %s" % (k, ("{%s}" % v) if isinstance(v, str) and " " in v else v))
    for i, layer in enumerate(layers):
        p = "l%d_" % (i + 1)
        if layer is None:
            lines.append(p + "enable false")
            continue
        tname, extra = layer
        lines.append(p + "enable true")
        lines.append('%stype "%s"' % (p, tname))
        vals = cloud_types.full(tname)
        vals.update(extra)
        across = vals.pop("across", 0.0)
        for k, v in vals.items():
            lines.append("%s%s %s" % (p, k, knob_value(k, v)))
        if vals["volume"]:
            # What 'place in front of camera' does for the camera at frame 1001 (at 0, 3000, 0,
            # looking down -Z), plus 'across' km to the side so the pan carries it over the frame.
            s = float(knobs.get("scene_scale", 0.1))
            pos = (across * 1000.0 / s, vals["base"] / s, -vals["place_km"] * 1000.0 / s)
            lines.append("%svol_position {%g %g %g}" % ((p,) + pos))
            if knobs.get("_box") == i + 1:
                # Linked to a Cube (written by main()), as 'make 3D box' leaves it.
                lines += box_links(name, i + 1)
                BOXES.append((name, i + 1, pos, vals["vol_size"], s))
    # The group's own knobs end at the first line that is just "}"; later values win.
    head_end = body.index("\n}\n")
    body = re.sub(r"^ name EzCloudGen\n", "", body, count=1, flags=re.M)
    body = re.sub(r"^ selected true\n", "", body, count=1, flags=re.M)
    body = body.replace("Group {\n", "Group {\n inputs %d\n name %s\n" % (inputs, name), 1)
    head_end = body.index("\n}\n")
    return body[:head_end] + "\n" + "\n".join(" " + l for l in lines) + body[head_end:]


def main():
    body = group_text()
    out = ["#! Nuke15.1 -nx", "version 15.1 v3",
           "define_window_layout_xml {}" if False else "",
           "Root {",
           " inputs 0",
           ' name "[file dirname [value root.name]]/EzCloudGen_demo.nk"',
           " frame 1001", " first_frame 1001", " last_frame 1100", " lock_range true",
           " fps 24",
           ' format "1920 1080 0 0 1920 1080 1 HD_1080"',
           "}"]
    for layer in ("cloud cloud.red cloud.green cloud.blue cloud.alpha", "cloud_sun cloud_sun.red cloud_sun.green cloud_sun.blue",
                  "cloud_sky cloud_sky.red cloud_sky.green cloud_sky.blue",
                  "cloud_shadow cloud_shadow.red cloud_shadow.green cloud_shadow.blue"):
        out.append("add_layer {%s}" % layer)
    out += ["StickyNote {", " inputs 0", " name ReadMe",
            ' label "EzCloudGen demo: synthetic, no files read. The scene is in decimetres (units to metres 0.1).\\n'
            'The shot camera is 300 m up and pans 12 degrees over 1001-1100; the clouds drift with the wind.\\n'
            'Viewer inputs: 1-4 sky decks. 5 HeroVolume: layer 2 follows the wireframe Cube beside it (move it in 3D).\\n'
            '6 StormFront. 7 Mountains: a ridge plate with depth.Z, so the clouds go behind it and shadow it (view Shadow),\\n'
            'with motion vectors on; 8 is its VectorBlur. 9 PaintedSky: a coverage map says where the clouds go.\\n'
            'Each EzCloudGen: Layer tabs have the type menu,\\n'
            'view shows Comp / Clouds / Sun share / Depth / Variations / Shadow, resolution Half (Full for finals).\\n'
            'Outputs: rgba, depth.Z (Planar Z, scene units, for EzCloudShafts), cloud, cloud_sun, cloud_sky, cloud_shadow,\\n'
            'forward/backward (with motion vectors on)."',
            " note_font_size 18", " xpos 0", " ypos -420", "}",
            "Camera2 {", " inputs 0",
            " translate {0 3000 0}",
            " rotate {18 {curve x1001 0 x1100 12} 0}",
            " focal 24", " haperture 36", " vaperture 20.25",
            " name ShotCamera", " label \"300 m up, pitched 18 deg\"", " xpos 0", " ypos -200", "}",
            "set Ncam [stack 0]",
            "Constant {", " inputs 0", " channels rgba", " color {0.1 0.2 0.48 1}",
            " name SkyBackdrop", " label \"stand-in sky (your plate or HDRI goes here)\"", " xpos 200", " ypos -200", "}",
            "set Nsky [stack 0]",
            # A stand-in plate with depth: a ridge about 8 km away (Planar Z in decimetres), fixed in
            # the world by working out each pixel's elevation and azimuth from the camera's pan.
            "Expression {",
            " temp_name0 elev",
            " temp_expr0 {18 + degrees(atan((y / height - 0.5) * 20.25 / 24))}",
            " temp_name1 az",
            " temp_expr1 {ShotCamera.rotate.y - degrees(atan((x / width - 0.5) * 36 / 24))}",
            " temp_name2 top",
            " temp_expr2 {2.2 + 1.3 * sin(radians(az * 9)) + 0.5 * sin(radians(az * 23 + 40))}",
            " channel0 {rgba.red -rgba.green -rgba.blue none}",
            " expr0 {elev < top ? 0.05 : r}",
            " channel1 {-rgba.red rgba.green -rgba.blue none}",
            " expr1 {elev < top ? 0.065 : g}",
            " channel2 {-rgba.red -rgba.green rgba.blue none}",
            " expr2 {elev < top ? 0.06 : b}",
            " channel3 depth",
            " expr3 {elev < top ? 80000 : 0}",
            " name MountainRidge", " label \"stand-in plate with depth.Z (a ridge 8 km away)\"",
            " xpos 2600", " ypos -200", "}",
            "set Nridge [stack 0]"]
    viewer_inputs = []
    for i, (name, label, layers, knobs) in enumerate(SETUPS):
        x = 200 + i * 400
        out += ["BackdropNode {", " inputs 0", " name Backdrop_%s" % name, ' label "%s"' % label,
                " note_font_size 20", " tile_color 0x3a5a4aff", " xpos %d" % (x - 60), " ypos -40",
                " bdwidth 360", " bdheight 220", "}"]
        inputs = 4
        if knobs.get("_map"):
            # A painted coverage map (a Roto over the plate in a real shot): a white disc on the
            # left, a white band on the right, soft.
            out += ["Constant {", " inputs 0", " channels rgba", " color {0 0 0 0}",
                    " name %s_MapBlack" % name, " xpos %d" % (x + 150), " ypos -200", "}",
                    "Radial {", " area {96 324 864 918}", " softness 0.6",
                    " name %s_MapDisc" % name, " xpos %d" % (x + 150), " ypos -150", "}",
                    "Rectangle {", " area {1056 486 1880 648}", " softness 60",
                    " name %s_MapBand" % name, " xpos %d" % (x + 150), " ypos -110", "}",
                    "Blur {", " size 48", " name %s_Map" % name,
                    ' label "coverage map: white = clouds,\\nblack = clear (paint your own)"',
                    " xpos %d" % (x + 150), " ypos -70", "}",
                    "set N%s_Map [stack 0]" % name,
                    "push $N%s_Map" % name]
            inputs = 5
        # Inputs: (map), sun (none), atmos (none), camera, bg; the last pushed is input 0.
        out += ["push 0", "push 0", "push $Ncam", "push $%s" % knobs.get("_bg", "Nsky")]
        out.append(instance(body, name, layers, knobs, x, 60, inputs))
        out.append("set N%s [stack 0]" % name)
        viewer_inputs.append(name)
        for bname, layer, pos, size, scale in BOXES:
            if bname == name:
                out.append(box_node(name, layer, pos, size, scale, x + 150, 160))
        if knobs.get("_vectorblur"):
            # Motion blur from the clouds' forward vectors (the camera pans; the clouds drift).
            out += ["push $N%s" % name, "VectorBlur2 {", " uv forward", " scale 2",
                    " name %s_MotionBlur" % name,
                    ' label "motion blur from EzCloudGen\\nforward vectors (exaggerated x2)"',
                    " xpos %d" % x, " ypos 160", "}",
                    "set N%s_MotionBlur [stack 0]" % name]
            viewer_inputs.append(name + "_MotionBlur")
    for name in reversed(viewer_inputs):
        out.append("push $N%s" % name)
    out += ["Viewer {", " inputs %d" % len(viewer_inputs), " frame 1001", " frame_range 1001-1100",
            " name Viewer1", " xpos 800", " ypos 400", "}"]
    text = "\n".join(l for l in out if l != "") + "\n"
    if not os.path.isdir(os.path.dirname(OUT)):
        os.makedirs(os.path.dirname(OUT))
    with open(OUT, "w", newline="\n") as f:
        f.write(text)
    print("wrote " + OUT)


if __name__ == "__main__":
    main()
