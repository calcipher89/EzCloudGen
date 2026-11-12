# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

EzCloudGen is a volumetric, art-directable cloud generator for Nuke (NukeX 15.1 now, Nuke 17
later). It is a Blink ray marcher wrapped in a self-contained Group and gizmo. It is a sibling
of the ezTools EzAtmosScatter, EzDepthHaze and EzCloudShafts, which it reads from or feeds. See
README.md for the user-facing knobs and inputs.

## Commands

The Nuke steps must run inside real NukeX. There is no CI.

    Nuke15.1.exe --nukex -t python/build_group.py          # writes groups/EzCloudGen_group.nk + gizmos/EzCloudGen.gizmo
    set EZCLOUDGEN_TEST_WIDTH=960
    Nuke15.1.exe --nukex -i --gpu -t python/test_render.py  # renders tests/out/*.png, raises on failed/cancelled renders
    python3 python/build_demo_nk.py                         # rebuilds examples/EzCloudGen_demo.nk from the built group (no Nuke)

To check a kernel edit without Nuke, compile it on the CPU with g++ against a small Blink stand-in
(`reference/blink_check/blink_shim.h`) and render one frame. Parameters are the kernel's
`defineParam` names. `map=` feeds the coverage map and `depth=` (a .npy) feeds the bg depth:

    python3 reference/blink_check/run_kernel.py out.png 480 volume=1 vol_shape=2 ...

`reference/sheet.py` renders contact sheets from the older numpy prototype (`reference/clouds.py`).
That prototype has no volumes or erosion stack, so the kernel is the source of truth.

## Architecture

- `blink/EzCloudGen.blink` is one cloud layer. The same kernel serves every pass, picked by its
  `output` param: 0 colour, 1 sun share, 2 Planar Z, 3 ground shadow on the bg, 4 motion
  vector to the other frame, and 5 the layer's sun map (optical depth towards the sun from the
  ground plus its altitude moments, 768 square). Each layer reads the sum of the other layers'
  maps as `smap` and keeps the part above each point, so layers shadow what is below them. A layer is either a deck (a curved-earth shell driven by a 2D
  weather field, the `weather()`, `profile()` and `cloud()` functions) or a placed volume
  (`volume=1`, `volumeShape()` in a box's local frame). Both share the erosion stack: billows,
  wisps, grain, swirl and shear. Lighting is a short sun march (`sunDepth()`) with
  multiple-scattering octaves, sky and ground ambient, and haze.
- `blink/EzCloudGenStack.blink` depth-sorts up to three layers, nearest first, per pixel.
- `python/build_group.py` builds the whole Group inside Nuke:
  - one BlinkScript per layer per pass;
  - the stack;
  - the depth, shadow, motion-vector and preview chains;
  - all knobs.
  Kernel params are driven by knob expressions. The camera matrix, EzAtmosScatter light and the
  box inputs are Python expressions, and the box-matrix code is stored as text in the hidden
  `box_lib` knob.
- `python/cloud_types.py` is the single table of cloud-type presets. `DEFAULTS` + `TYPES` are
  keyed by short names, and `KERNEL` maps those names to the kernel param names. Both the Nuke
  build and the prototype use it.
- `python/build_demo_nk.py` does text surgery on the built group .nk: it copies the group per
  setup and overrides knob values, so re-run it after every group rebuild.
- `reference/sheets/nuke/*.png` are the NukeX test references. Refresh them only when the look
  legitimately changes.

## Constraints that bite

- **Never hand-edit or hand-write the BlinkScript kernel hash, or patch the generated
  `.nk`/`.gizmo` by hand.** If the hash is wrong, Nuke loads the node fine but silently cancels
  every render ("stuck computing"). Always regenerate them with `build_group.py` inside NukeX.
- **Self-contained node:** no init.py or menu.py. All code, presets and paths live in the
  node's knobs. Studio paths use TCL like `[getenv JOB]`. Ship both the Group and the gizmo.
- **Blink inlines every call to `cloud()`.** Each extra call site multiplies the CPU (LLVM)
  compile time; two extra calls took it past 10 minutes. Add new density samples to an existing
  loop (see the sky-occlusion probes in `sunDepth()`), not as new calls. A cold CPU compile of
  the kernel takes about 5 minutes per machine even on main. A warm build or a GPU compile takes
  seconds.
- When `build_group.py` runs from the terminal, Nuke only compiles Blink via
  `kernelSourceFile` + `reloadKernelSourceFile` + recompile.
- Nuke API quirks met so far:
  - A Copy errors "Missing input channel" if the channel is absent, so add it with AddChannels
    first.
  - Channel_Knob returns `depth` for depth.Z.
  - `Multiline_Eval_String_Knob.value()` runs TCL, so read code with `getText()`.
  - In 15.1, Cube has no axis input; parent it via TransformGeo.
  - Cube has no world_matrix.
  - Camera3's default haperture is 24.576.
  - `Constant(color=[...])` in the constructor fails silently.
- Units: scenes are in decimetres (`scene_scale` 0.1, scene units to metres). Depth out is
  Planar Z in scene units.
- Test and demo images must be synthetic. Studio plates are sensitive.
- One change per PR, each PR against main. Bump `VERSION` in `build_group.py` and the README
  status line for each release.
