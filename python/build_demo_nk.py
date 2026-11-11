"""Write examples/EzCloudGen_demo.nk: four cloud setups through a moving shot camera.

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
]


def group_text():
    with open(GROUP) as f:
        text = f.read()
    start = text.index("Group {")
    end = text.index("end_group", start) + len("end_group")
    return text[start:end]


def instance(body, name, layers, knobs, x, y):
    lines = ["xpos %d" % x, "ypos %d" % y, "resolution Half", "samples 2"]
    for k, v in knobs.items():
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
        for k, v in vals.items():
            lines.append("%s%s %s" % (p, k, v))
    # The group's own knobs end at the first line that is just "}"; later values win.
    head_end = body.index("\n}\n")
    body = re.sub(r"^ name EzCloudGen\n", "", body, count=1, flags=re.M)
    body = re.sub(r"^ selected true\n", "", body, count=1, flags=re.M)
    body = body.replace("Group {\n", "Group {\n inputs 4\n name %s\n" % name, 1)
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
                  "cloud_sky cloud_sky.red cloud_sky.green cloud_sky.blue"):
        out.append("add_layer {%s}" % layer)
    out += ["StickyNote {", " inputs 0", " name ReadMe",
            ' label "EzCloudGen demo: synthetic, no files read. The scene is in decimetres (units to metres 0.1).\\n'
            'The shot camera is 300 m up and pans 12 degrees over 1001-1100; the clouds drift with the wind.\\n'
            'View 1-4 in the Viewer for the four setups. Each EzCloudGen: Layer tabs have the type menu,\\n'
            'view shows Comp / Clouds / Sun share / Depth, resolution Half (Full for finals).\\n'
            'Outputs: rgba, depth.Z (Planar Z, scene units, for EzCloudShafts), cloud, cloud_sun, cloud_sky."',
            " note_font_size 18", " xpos 0", " ypos -420", "}",
            "Camera2 {", " inputs 0",
            " translate {0 3000 0}",
            " rotate {18 {curve x1001 0 x1100 12} 0}",
            " focal 24", " haperture 36", " vaperture 20.25",
            " name ShotCamera", " label \"300 m up, pitched 18 deg\"", " xpos 0", " ypos -200", "}",
            "set Ncam [stack 0]",
            "Constant {", " inputs 0", " channels rgba", " color {0.1 0.2 0.48 1}",
            " name SkyBackdrop", " label \"stand-in sky (your plate or HDRI goes here)\"", " xpos 200", " ypos -200", "}",
            "set Nsky [stack 0]"]
    viewer_inputs = []
    for i, (name, label, layers, knobs) in enumerate(SETUPS):
        x = 200 + i * 400
        out += ["BackdropNode {", " inputs 0", " name Backdrop_%s" % name, ' label "%s"' % label,
                " note_font_size 20", " tile_color 0x3a5a4aff", " xpos %d" % (x - 60), " ypos -40",
                " bdwidth 360", " bdheight 220", "}"]
        # Inputs: sun (none), atmos (none), camera, bg; the last pushed is input 0.
        out += ["push 0", "push 0", "push $Ncam", "push $Nsky"]
        out.append(instance(body, name, layers, knobs, x, 60))
        out.append("set N%s [stack 0]" % name)
        viewer_inputs.append(name)
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
