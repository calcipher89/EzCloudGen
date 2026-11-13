"""Compile blink/EzCloudGen.blink on the CPU with blink_shim.h and render a test frame.

    python3 reference/blink_check/run_kernel.py out.exr_or_png [width] [k=v ...]

Parameters are the kernel's knob names (cam_position=0,3000,0 ...). The per-layer ones are
arrays in the kernel: base=2000 sets layer 1, base.2=5000 layer 2 (turn it on with layer_on.2=1).
Only layer 1 is on by default, and every layer starts from LAYER_DEFAULTS. map=picture.png feeds
the coverage map input (and sets use_map=1); smap=t.npy feeds a sun map as layer 2's, so it
shadows layer 1 (and sets use_sun_map=1); depth=z.npy feeds the bg depth (and sets occlude=1).
Writes rgba as a tone-mapped PNG (and a .npy of the raw floats beside it).
"""

import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
KERNEL = os.path.join(ROOT, "blink", "EzCloudGen.blink")
BUILD = os.path.join(HERE, "build")

# Each layer's settings before any are given (the kernel's arrays have no defaults of their own).
LAYER_DEFAULTS = {
    "offset": "0,0", "base": "1400", "thickness": "1300", "coverage": "0.42", "scale_km": "1.6",
    "stretch": "1", "wind_deg": "20", "edge": "0.06", "taper": "0.85", "bottom_round": "0.04",
    "top_round": "0.15", "detail_size": "220", "erosion": "0.45", "sigma": "0.06", "cells": "0",
    "cell_km": "0.5", "warp": "1.2", "forward": "0.8", "ambient": "1", "sky_occlusion": "1",
    "shadow_depth": "0", "octaves": "3.5", "billow": "1", "streaks": "0", "vary": "0", "density": "1",
    "volume": "0", "vol_shape": "1", "vol_center": "0,20000,-60000", "vol_rotate": "0,0,0",
    "vol_size": "3000,1800,3000", "lumps": "0.5", "lump_size": "600", "small_lumps": "0", "skirt": "0",
    "fade_top": "0", "fade_bottom": "0", "fade_left": "0", "fade_right": "0", "fade_front": "0",
    "fade_back": "0", "wisp_size": "60", "wisp_amount": "0", "grain_size": "15", "grain_amount": "0",
    "swirl": "0", "swirl_size": "400", "turbulence": "0", "crumble": "0", "crumble_size": "120",
    "shear": "0", "map_amount": "1", "map_channel": "0", "map_drift": "0,0", "other_offset": "0,0",
    "other_vol_center": "0,20000,-60000", "vol_axes": "0", "vol_axis_x": "1,0,0", "vol_axis_y": "0,1,0",
    "vol_axis_z": "0,0,1", "layer_seed": "0",
    "map_mode": "0", "detail_model": "0", "sil_distance": "10000", "sil_depth": "6000",
}

MAIN = r'''
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <thread>
#include "blink_shim.h"
#define kernel struct
#define param public
#define local public
%(kernel)s

static void set(EzCloudGen &k, const char *name, const char *val) {
  float v[4] = {0, 0, 0, 0};
  int n = sscanf(val, "%%f,%%f,%%f,%%f", v, v + 1, v + 2, v + 3);
  (void)n;
%(setters)s
  fprintf(stderr, "unknown param %%s\n", name);
}

int main(int argc, char **argv) {
  int w = atoi(argv[1]), h = atoi(argv[2]);
  EzCloudGen proto;
  proto.define();
  std::vector<float> mapPix;
  std::vector<float> zPix;
  std::vector<float> smapPix;
  std::vector<float> smapBlack;
%(defaults)s
  for (int i = 3; i + 1 < argc; i += 2) {
    if (!strcmp(argv[i], "map_file")) {
      // Raw: int w, int h, then w * h rgba floats, rows going up.
      FILE *f = fopen(argv[i + 1], "rb");
      int mw = 0, mh = 0;
      if (f && fread(&mw, 4, 1, f) == 1 && fread(&mh, 4, 1, f) == 1) {
        mapPix.resize(size_t(mw) * mh * 4);
        if (fread(mapPix.data(), 4, mapPix.size(), f) == mapPix.size()) {
          proto.cmap.pix = mapPix.data();
          proto.cmap.bounds.x2 = mw;
          proto.cmap.bounds.y2 = mh;
        }
      }
      if (f) fclose(f);
      continue;
    }
    if (!strcmp(argv[i], "smap_file")) {
      // Raw like map_file: a sun map, as layer 2's (layers 1 and 3 get black ones the same size).
      FILE *f = fopen(argv[i + 1], "rb");
      int mw = 0, mh = 0;
      if (f && fread(&mw, 4, 1, f) == 1 && fread(&mh, 4, 1, f) == 1) {
        smapPix.resize(size_t(mw) * mh * 4);
        smapBlack.assign(size_t(mw) * mh * 4, 0.0f);
        if (fread(smapPix.data(), 4, smapPix.size(), f) == smapPix.size()) {
          proto.smap2.pix = smapPix.data();
          proto.smap2.bounds.x2 = mw;
          proto.smap2.bounds.y2 = mh;
          proto.smap.pix = smapBlack.data();
          proto.smap.bounds.x2 = mw;
          proto.smap.bounds.y2 = mh;
          proto.smap3.pix = smapBlack.data();
          proto.smap3.bounds.x2 = mw;
          proto.smap3.bounds.y2 = mh;
        }
      }
      if (f) fclose(f);
      continue;
    }
    if (!strcmp(argv[i], "depth_file")) {
      // Raw: w * h floats (the bg depth), rows going up, the frame's size.
      FILE *f = fopen(argv[i + 1], "rb");
      zPix.resize(size_t(w) * h);
      if (!f || fread(zPix.data(), 4, zPix.size(), f) != zPix.size())
        zPix.clear();
      if (f) fclose(f);
      continue;
    }
    set(proto, argv[i], argv[i + 1]);
  }
  proto.init();
  std::vector<float> out(w * h * 4);
  int nt = std::thread::hardware_concurrency();
  std::vector<std::thread> th;
  for (int t = 0; t < nt; t++) th.emplace_back([&, t]() {
    EzCloudGen k = proto;
    for (int y = t; y < h; y += nt)
      for (int x = 0; x < w; x++) {
        int2 p = {x, y};
        k.zin.value = float4(zPix.empty() ? 0.0f : zPix[y * w + x], 0.0f, 0.0f, 0.0f);
        k.process(p);
        float4 c = k.dst();
        float *o = &out[(y * w + x) * 4];
        o[0] = c.x; o[1] = c.y; o[2] = c.z; o[3] = c.w;
      }
  });
  for (auto &t : th) t.join();
  fwrite(out.data(), sizeof(float), out.size(), stdout);
}
'''


def build():
    src = open(KERNEL).read()
    params = re.findall(r'defineParam\((\w+), "(\w+)"', src)
    types = dict(re.findall(r"^\s+(int|float|float2|float3|float4)\s+(\w+);", src.split("local:")[0], re.M)[::-1])
    types = {v: t for t, v in re.findall(r"^\s+(int|float|float2|float3|float4)\s+(\w+);",
                                         src.split("local:")[0], re.M)}
    setters = []
    vals = {"int": "int(v[0])", "float": "v[0]", "float2": "float2(v[0], v[1])",
            "float3": "float3(v[0], v[1], v[2])", "float4": "float4(v[0], v[1], v[2], v[3])"}
    for var, name in params:
        setters.append('  if (!strcmp(name, "%s")) { k.%s = %s; return; }' % (name, var, vals[types[var]]))
    # The per-layer arrays: the knob name sets layer 1, name.2 and name.3 the others.
    arrays = re.findall(r"^\s+(int|float|float2|float3)\s+(\w+)\[3\];", src.split("local:")[0], re.M)
    for t, var in arrays:
        for i in range(3):
            key = var if i == 0 else "%s.%d" % (var, i + 1)
            setters.append('  if (!strcmp(name, "%s")) { k.%s[%d] = %s; return; }' % (key, var, i, vals[t]))
    defaults = []
    for t, var in arrays:
        for i in range(3):
            val = "1" if var == "layer_on" and i == 0 else "0" if var == "layer_on" else LAYER_DEFAULTS[var]
            defaults.append('  set(proto, "%s", "%s");' % (var if i == 0 else "%s.%d" % (var, i + 1), val))
    os.makedirs(BUILD, exist_ok=True)
    cpp = os.path.join(BUILD, "kernel.cpp")
    with open(cpp, "w") as f:
        f.write(MAIN % {"kernel": src, "setters": "\n".join(setters), "defaults": "\n".join(defaults)})
    exe = os.path.join(BUILD, "kernel")
    subprocess.check_call(["g++", "-O2", "-std=c++17", "-pthread", "-I", HERE, "-Wall",
                           "-Wno-unused-variable", "-o", exe, cpp])
    return exe


def render(w, h, params):
    exe = build()
    args = [exe, str(w), str(h)]
    if "map" in params:
        # A picture for the coverage map input (cmap): any image PIL reads.
        from PIL import Image
        im = np.asarray(Image.open(params.pop("map")).convert("RGBA"), dtype=np.float32)[::-1] / 255.0
        raw = os.path.join(BUILD, "map.raw")
        with open(raw, "wb") as f:
            f.write(np.array(im.shape[1::-1], dtype=np.int32).tobytes())
            f.write(np.ascontiguousarray(im).tobytes())
        params["map_file"] = raw
        params.setdefault("use_map", "1")
    if "smap" in params:
        # The other layers' sun map: a .npy of h x w x 3 floats (output 5's optical depth and
        # altitude moments), rows going up (output 5 comes back from render() flipped, so flip it
        # back).
        sm = np.load(params.pop("smap")).astype(np.float32)
        im = np.concatenate([sm[..., :3], np.ones(sm.shape[:2] + (1,), np.float32)], axis=2)
        raw = os.path.join(BUILD, "smap.raw")
        with open(raw, "wb") as f:
            f.write(np.array(im.shape[1::-1], dtype=np.int32).tobytes())
            f.write(np.ascontiguousarray(im).tobytes())
        params["smap_file"] = raw
        params.setdefault("use_sun_map", "1")
    if "depth" in params:
        # The bg depth for occlusion: a .npy of h x w floats, rows going down (as a picture).
        z = np.load(params.pop("depth")).astype(np.float32)[::-1]
        raw = os.path.join(BUILD, "depth.raw")
        z.tofile(raw)
        params["depth_file"] = raw
        params.setdefault("occlude", "1")
    for k, v in params.items():
        args += [k, v]
    raw = subprocess.check_output(args)
    return np.frombuffer(raw, dtype=np.float32).reshape(h, w, 4)[::-1]  # Nuke rows go up


def main():
    out = sys.argv[1]
    w = int(sys.argv[2]) if len(sys.argv) > 2 else 480
    params = dict(a.split("=", 1) for a in sys.argv[3:])
    h = int(w * 9 / 16)
    params.setdefault("frame_size", "%d,%d" % (w, h))
    img = render(w, h, params)
    np.save(os.path.splitext(out)[0] + ".npy", img)
    from PIL import Image
    x = np.clip(img[..., :3] + (1 - img[..., 3:4]) * np.array([0.25, 0.4, 0.75]), 0, None)
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    y = np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0, 1) ** (1 / 2.2)
    Image.fromarray((y * 255).astype(np.uint8)).save(out)
    print("alpha mean %.3f  rgb max %.3f" % (img[..., 3].mean(), img[..., :3].max()))


if __name__ == "__main__":
    main()
