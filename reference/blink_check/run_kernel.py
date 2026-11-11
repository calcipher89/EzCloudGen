"""Compile blink/EzCloudGen.blink on the CPU with blink_shim.h and render a test frame.

    python3 reference/blink_check/run_kernel.py out.exr_or_png [width] [k=v ...]

Parameters are the kernel's define() names (cam_position=0,3000,0 ...); map=picture.png feeds the
coverage map input (and sets use_map=1). Writes rgba as a
tone-mapped PNG (and a .npy of the raw floats beside it).
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
    for var, name in params:
        t = types[var]
        val = {"int": "int(v[0])", "float": "v[0]", "float2": "float2(v[0], v[1])",
               "float3": "float3(v[0], v[1], v[2])", "float4": "float4(v[0], v[1], v[2], v[3])"}[t]
        setters.append('  if (!strcmp(name, "%s")) { k.%s = %s; return; }' % (name, var, val))
    os.makedirs(BUILD, exist_ok=True)
    cpp = os.path.join(BUILD, "kernel.cpp")
    with open(cpp, "w") as f:
        f.write(MAIN % {"kernel": src, "setters": "\n".join(setters)})
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
