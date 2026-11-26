"""Compile blink/EzCirrusSheet.blink on the CPU with blink_shim.h and render a frame.

    python3 reference/blink_check/run_sheet.py out.png [width] [k=v ...]

Parameters are the kernel's knob names (height=9000 cover=0.5 ...). depth=z.npy feeds the bg
depth (and sets occlude=1). Writes the sheet over a plain blue sky as a tone-mapped PNG, and a
.npy of the raw premultiplied rgba beside it (rows going down, as a picture).
"""
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
KERNEL = os.path.join(ROOT, "blink", "EzCirrusSheet.blink")
BUILD = os.path.join(HERE, "build")

MAIN = r'''
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <thread>
#include "blink_shim.h"
#define kernel struct
#define param public
#define local public
%(kernel)s

static void set(EzCirrusSheet &k, const char *name, const char *val) {
  float v[4] = {0, 0, 0, 0};
  sscanf(val, "%%f,%%f,%%f,%%f", v, v + 1, v + 2, v + 3);
%(setters)s
  fprintf(stderr, "unknown param %%s\n", name);
}

int main(int argc, char **argv) {
  int w = atoi(argv[1]), h = atoi(argv[2]);
  EzCirrusSheet proto;
  proto.define();
  std::vector<float> zPix;
  for (int i = 3; i + 1 < argc; i += 2) {
    if (!strcmp(argv[i], "depth_file")) {
      FILE *f = fopen(argv[i + 1], "rb");
      zPix.resize(size_t(w) * h);
      if (!f || fread(zPix.data(), 4, zPix.size(), f) != zPix.size()) zPix.clear();
      if (f) fclose(f);
      continue;
    }
    set(proto, argv[i], argv[i + 1]);
  }
  proto.init();
  std::vector<float> out(size_t(w) * h * 4);
  int nt = std::thread::hardware_concurrency();
  std::vector<std::thread> th;
  for (int t = 0; t < nt; t++) th.emplace_back([&, t]() {
    EzCirrusSheet k = proto;
    for (int y = t; y < h; y += nt)
      for (int x = 0; x < w; x++) {
        int2 p = {x, y};
        k.zin.value = float4(zPix.empty() ? 0.0f : zPix[y * w + x], 0.0f, 0.0f, 0.0f);
        k.process(p);
        float4 c = k.dst();
        float *o = &out[(size_t(y) * w + x) * 4];
        o[0] = c.x; o[1] = c.y; o[2] = c.z; o[3] = c.w;
      }
  });
  for (auto &t : th) t.join();
  fwrite(out.data(), sizeof(float), out.size(), stdout);
}
'''


def build():
    src = open(KERNEL).read()
    head = src.split("local:")[0]
    params = re.findall(r'defineParam\((\w+), "(\w+)"', src)
    types = {v: t for t, v in re.findall(r"^\s+(int|float|float2|float3|float4)\s+(\w+);", head, re.M)}
    vals = {"int": "int(v[0])", "float": "v[0]", "float2": "float2(v[0], v[1])",
            "float3": "float3(v[0], v[1], v[2])", "float4": "float4(v[0], v[1], v[2], v[3])"}
    setters = ['  if (!strcmp(name, "%s")) { k.%s = %s; return; }' % (n, v, vals[types[v]]) for v, n in params]
    os.makedirs(BUILD, exist_ok=True)
    cpp = os.path.join(BUILD, "sheet.cpp")
    with open(cpp, "w") as f:
        f.write(MAIN % {"kernel": src, "setters": "\n".join(setters)})
    exe = os.path.join(BUILD, "sheet")
    subprocess.check_call(["g++", "-O2", "-std=c++17", "-pthread", "-I", HERE, "-Wall",
                           "-Wno-unused-variable", "-o", exe, cpp])
    return exe


def render(w, h, params, exe=None):
    exe = exe or build()
    params = dict(params)
    params.setdefault("frame_size", "%d,%d" % (w, h))
    if "depth" in params:
        z = np.load(params.pop("depth")).astype(np.float32)[::-1]
        raw = os.path.join(BUILD, "sheet_depth.raw")
        z.tofile(raw)
        params["depth_file"] = raw
        params.setdefault("occlude", "1")
    args = [exe, str(w), str(h)]
    for k, v in params.items():
        args += [k, str(v)]
    raw = subprocess.check_output(args)
    return np.frombuffer(raw, dtype=np.float32).reshape(h, w, 4)[::-1]


def main():
    out = sys.argv[1]
    w = int(sys.argv[2]) if len(sys.argv) > 2 else 480
    params = dict(a.split("=", 1) for a in sys.argv[3:])
    h = int(w * 9 / 16)
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
