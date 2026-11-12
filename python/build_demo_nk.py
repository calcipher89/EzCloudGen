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
      "sky_color": "0.12 0.15 0.27", "ground_color": "0.1 0.05 0.02", "haze_color": "1.6 1.1 0.75",
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
    ("CanyonFog", "Overcast canyon from 450 m up: ground fog in the floor, torn low cloud, a wisp passing close",
     [("Ground Fog", {"base": -40, "place_km": 2.6, "across": 0.1, "vol_size": (4500, 550, 5000)}),
      ("Torn Low Cloud", {"base": 230, "place_km": 1.7, "across": -0.5}),
      ("Wispy Fog", {"base": -30, "place_km": 1.15, "across": 0.0, "vol_size": (1400, 320, 1400)})],
     {"sun_direction": sun(14, 20), "sun_intensity": 0.13, "sky_color": "0.24 0.3 0.42", "sky_intensity": 0.6,
      "haze_color": "0.2 0.23 0.28", "haze_distance": 8, "_bg": "Ncanyon", "_cam": "Ncanyoncam"}),
    ("HighCam", "Golden hour from 1130 m up: the decks run out to the horizon, ground below it",
     [("Stratocumulus", {"coverage": 0.6}), ("Altocumulus", {}), None],
     {"sun_direction": sun(6, 8), "light_from": "Manual", "sun_color": "14 7 2.6",
      "sky_color": "0.12 0.15 0.27", "ground_color": "0.1 0.05 0.02", "haze_color": "1.6 1.1 0.75",
      "gap_amount": 0.7, "gap_size": 3, "_bg": "Nhighsky", "_cam": "Nhighcam"}),
    ("SoftCloud", "Soft Cumulus alone: smooth billows, a wispy skirt, bright sky-lit shadows; sun high behind the camera",
     [None, ("Soft Cumulus", {}), None],
     {"sun_direction": sun(53, -149), "light_from": "Manual", "sun_color": "9 8.6 8",
      "sky_color": "0.3 0.48 0.9", "ground_color": "0.5 0.52 0.55", "samples": 4}),
]


VOL_SHAPES = ["Ellipsoid", "Dome", "Anvil", "Box"]


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
            'Viewer inputs: 1-4 sky decks. 5 HeroVolume: layer 2 fills the wireframe Cube in its box2 input (move it in 3D).\\n'
            '6 StormFront. 7 Mountains: a ridge plate with depth.Z, so the clouds go behind it and shadow it (view Shadow),\\n'
            'with motion vectors on; 8 is its VectorBlur. 9 PaintedSky: a coverage map says where the clouds go.\\n'
            '10 CanyonFog: overcast canyon (its own camera, CanyonCam): ground fog, torn low cloud, a close wisp.\\n'
            '11 HighCam: GoldenHour from 1130 m up (its own camera, HighCam): the decks reach the horizon.\\n'
            '12 SoftCloud: one Soft Cumulus, lit softly from behind the camera.\\n'
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
            "set Nridge [stack 0]",
            # The canyon setup: its own camera looking down into a canyon under an overcast sky,
            # with cliffs either side, a floor and a far ridge (all with depth.Z, decimetres).
            "Camera2 {", " inputs 0",
            " translate {0 4500 0}",
            " rotate {-12 {curve x1001 0 x1100 8} 0}",
            " focal 24", " haperture 36", " vaperture 20.25",
            " name CanyonCam", " label \"450 m up, looking 12 deg down\"", " xpos 3000", " ypos -300", "}",
            "set Ncanyoncam [stack 0]",
            "Constant {", " inputs 0", " channels rgba", " color {0.3 0.32 0.36 1}",
            " name OvercastSky", " label \"stand-in overcast sky\"", " xpos 3200", " ypos -300", "}",
            "Expression {",
            " temp_name0 elev",
            " temp_expr0 {-12 + degrees(atan((y / height - 0.5) * 20.25 / 24))}",
            " temp_name1 az",
            " temp_expr1 {CanyonCam.rotate.y - degrees(atan((x / width - 0.5) * 36 / 24))}",
            " temp_name2 wall",
            # A V-shaped canyon: the walls lean back with height, with a rough, broken edge.
            # wall: degrees inside the rock (> 0), used soft for the colour (anti-aliased edge).
            " temp_expr2 {min(abs(az) - 11 - 0.7 * (elev + 12) - 2.5 * noise(elev / 2.5, az / 4, 1) - "
            "1.2 * noise(elev * 1.3, az, 2), 9 + 2 * sin(radians(az * 11)) + noise(az / 2, 0, 3) - elev)}",
            " temp_name3 ridge",
            " temp_expr3 {elev < 1.2 + 0.8 * sin(radians(az * 9))}",
            " channel0 {rgba.red rgba.green rgba.blue none}",
            # Rock in layered strata, a darker floor, a hazy far ridge.
            # Rock: broad irregular bands broken by vertical cracks, a darker floor, a hazy far
            # ridge; the cliff's edge is blended over about 0.2 degrees.
            " expr0 {lerp(elev < -4.3 ? 0.04 + 0.012 * noise(az / 2, elev * 2, 3) : ridge ? 0.16 : r, "
            "0.025 + 0.02 * noise(az / 5, elev * 0.7, 0) + 0.015 * noise(az * 2.5, elev / 5, 7) * noise(az / 2, elev, 9), "
            "clamp(wall / 0.2 + 0.5, 0, 1))}",
            " channel3 depth",
            # Planar Z: the floor's range along the view axis (the camera looks 12 degrees down);
            # the walls recede with their angle from the view axis.
            " expr3 {wall > 0 ? 9000 + 300 * abs(az) : elev < -4.3 ? 4500 / tan(radians(-elev)) * cos(radians(12)) + "
            "4500 * sin(radians(12)) : ridge ? 60000 : 0}",
            " name CanyonPlate", " label \"stand-in canyon plate with depth.Z\"",
            " xpos 3200", " ypos -200", "}",
            "set Ncanyon [stack 0]",
            # The high setup: the GoldenHour decks from 1130 m up (the earth's horizon dips about
            # 1.1 degrees there). The plate has hazy ground below the horizon, since the clouds
            # stop where the view meets the ground.
            "Camera2 {", " inputs 0",
            " translate {0 11300 0}",
            " rotate {18 {curve x1001 0 x1100 12} 0}",
            " focal 24", " haperture 36", " vaperture 20.25",
            " name HighCam", " label \"1130 m up, pitched 18 deg\"", " xpos 4000", " ypos -300", "}",
            "set Nhighcam [stack 0]",
            "push $Nsky",
            "Expression {",
            " temp_name0 elev",
            " temp_expr0 {18 + degrees(atan((y / height - 0.5) * 20.25 / 24)) + 1.08}",
            " temp_name1 gnd",
            " temp_expr1 {clamp(-elev / 0.25 + 0.5, 0, 1)}",
            " temp_name2 far",
            " temp_expr2 {clamp(-elev / 2.5, 0, 1)}",
            " channel0 {rgba.red -rgba.green -rgba.blue none}",
            " expr0 {lerp(r, lerp(0.62, 0.07, far), gnd)}",
            " channel1 {-rgba.red rgba.green -rgba.blue none}",
            " expr1 {lerp(g, lerp(0.42, 0.055, far), gnd)}",
            " channel2 {-rgba.red -rgba.green rgba.blue none}",
            " expr2 {lerp(b, lerp(0.3, 0.045, far), gnd)}",
            " name HighPlate", " label \"stand-in plate: sky, hazy ground below the horizon\"",
            " xpos 4200", " ypos -200", "}",
            "set Nhighsky [stack 0]"]
    viewer_inputs = []
    for i, (name, label, layers, knobs) in enumerate(SETUPS):
        x = 200 + i * 400
        out += ["BackdropNode {", " inputs 0", " name Backdrop_%s" % name, ' label "%s"' % label,
                " note_font_size 20", " tile_color 0x3a5a4aff", " xpos %d" % (x - 60), " ypos -40",
                " bdwidth 360", " bdheight 220", "}"]
        # The node's inputs by number: bg 0, camera 1, atmos 2, sun 3, map 4, box1-3 5-7.
        srcs = {0: knobs.get("_bg", "Nsky"), 1: knobs.get("_cam", "Ncam")}
        box = knobs.get("_box")
        if box:
            # A Cube in the layer's box input, as 'make 3D box' leaves it: placed and sized like
            # the volume (its translate is the volume's centre).
            tname, extra = layers[box - 1]
            vals = cloud_types.full(tname)
            vals.update(extra)
            sc = float(knobs.get("scene_scale", 0.1))
            pos = (vals.get("across", 0.0) * 1000.0 / sc, vals["base"] / sc, -vals["place_km"] * 1000.0 / sc)
            out.append(box_node(name, box, pos, vals["vol_size"], sc, x + 150, -120))
            out.append("set N%s_Box [stack 0]" % name)
            srcs[4 + box] = "N%s_Box" % name
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
                    "set N%s_Map [stack 0]" % name]
            srcs[4] = "N%s_Map" % name
        # Pushed from the last input to the first: the last pushed is input 0.
        inputs = max(4, max(srcs) + 1)
        for j in range(inputs - 1, -1, -1):
            out.append("push $%s" % srcs[j] if j in srcs else "push 0")
        out.append(instance(body, name, layers, knobs, x, 60, inputs))
        out.append("set N%s [stack 0]" % name)
        viewer_inputs.append(name)
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
