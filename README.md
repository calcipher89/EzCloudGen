# EzCloudGen

A procedural, volumetric cloud generator for Nuke, built to sit alongside the ezTools
(EzAtmosScatter, EzDepthHaze, EzCloudShafts). It will ship as a self-contained Group and a gizmo,
with all code and settings in the node's knobs (no init.py or menu.py).

## Status

Prototype stage. `reference/` holds a Python (NumPy + numba) prototype of the renderer, written as
scalar per-pixel code so it ports line for line to a BlinkScript kernel. The Nuke tool comes next.

## Planned v1

- Cloud types menu: Cumulus, Cumulus Congestus, Stratocumulus, Stratus, Altocumulus, Altostratus,
  Cirrus, Cirrocumulus.
- Coverage control, plus an option to open a gap toward the sun so shafts land in frame.
- Up to 3 layers at different heights, each with its own type, coverage and wind.
- Lit by EzAtmosScatter (sun direction, sun colour, sky colour), with aerial perspective.
- Rendered through the shot camera: premultiplied rgba and Planar Z depth in scene units, ready
  for EzCloudShafts, plus a sun-view opacity pass for its sun-view clouds input.
- Breakout layers (sun light, sky light, alpha, depth) for re-grading over the plate.

## The renderer (reference/clouds.py)

- Curved earth: each layer is a spherical shell, so decks converge on the horizon.
- Shape: a 2D weather field (warped fbm, ridged streaks for cirrus, Worley cells for
  altocumulus/cirrocumulus) thresholded by coverage, shrunk with height by a profile (flat bases,
  rounded tops, domes via `taper`), then the surface is displaced by 3D detail noise
  (inverted Worley for billows, value noise for wisps). Detail octaves drop with distance so far
  clouds don't sparkle.
- Light: a short march toward the sun, 4 multiple-scattering octaves with a dual
  Henyey-Greenstein phase (silver linings when backlit), a powder term for dark edges, sky light
  from above and ground bounce from below, energy-conserving integration, aerial perspective.

Preview sheets (synthetic, no plates):

    cd reference
    python sheet.py out.jpg 480 1.0 4 day        # all types; lighting: day, golden, back

`reference/sheets/` has the current day, backlit and golden-hour sheets. The prototype's own sun
and sky colours are simple stand-ins; in Nuke they come from EzAtmosScatter.

## Known gaps

- Layers don't shadow each other yet.
- Stratus and Altostratus are too flat; Cirrus needs finer fibres; Congestus is grainy up close.
