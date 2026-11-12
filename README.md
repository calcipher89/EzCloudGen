# EzCloudGen

A procedural, volumetric cloud generator for Nuke, built to sit alongside the ezTools
(EzAtmosScatter, EzDepthHaze, EzCloudShafts). It will ship as a self-contained Group and a gizmo,
with all code and settings in the node's knobs (no init.py or menu.py).

## Status

v0.14.0: the Group (`groups/EzCloudGen_group.nk`) and gizmo (`gizmos/EzCloudGen.gizmo`) build and
render in NukeX 15.1. `reference/` holds the Python prototype the kernel was ported from.

## Using it

Paste `groups/EzCloudGen_group.nk` into a script (or put `gizmos/` on the plugin path and create
EzCloudGen). Inputs:

- **bg** (optional): the plate or sky to comp over; it also sets the format. With a depth
  channel (depth.Z by default; 'depth is' Planar Z, ScanlineRender's 1/Z or distance), the
  clouds go behind its mountains and buildings, and their shadows fall on it ('hide behind bg').
  Depth of 0, or beyond 'sky beyond' (km), is sky.
- **camera**: the shot camera. Without one the node looks level from 300 m up.
- **atmos** (optional): an EzAtmosScatter. The sun direction and the sun and sky light it
  measures in its HDRI light the clouds ('light from' Auto).
- **sun** (optional): an Axis, overriding the sun direction.
- **box1, box2, box3** (optional): a 3D node per layer that the layer's volume fills.
- **map** (optional): a coverage map for the sky decks, painted over the shot (a Roto over the
  plate works): white piles up clouds, mid grey keeps the layer's coverage, black clears it. It is
  seen through the camera on 'map frame' and marks where the clouds stand on the layer (read at
  its middle height), so a white patch becomes a cluster of heaped domes rather than a slab. It
  stays put in the world and drifts with the wind.
  Each deck's 'follow map' sets how much it obeys, and 'map channel' lets each deck read its own
  channel.

Each of the three Layer tabs has a type menu that fills in its knobs. A layer is either a sky
deck (Cumulus ... Cirrocumulus) or a placed volume (Hero Cumulus, Storm Anvil, Fog Bank, Puff):
picking a volume type drops it 'distance' ahead of the camera ('place in front of camera' does
it again), then position, rotate and size move it. Or plug any 3D node (a Cube, an Axis, a
TransformGeo, parented or tracked) into the layer's **box1/box2/box3** input: the volume fills
that box and follows it. 'make 3D box' makes a wireframe Cube and plugs it in; view it with your
camera and move, rotate and scale it in the 3D viewer ('release box' unplugs it, keeping the
volume where it is). Every layer has the erosion stack: billows,
wisps, grain, swirl, turbulence (a finer swirl that makes edges roll), crumble (chunks bitten
out of the edges, for torn cloud and fog) and wind shear. A volume can also fade towards each
face of its box ('fade top', 'fade bottom', left, right, front, back), so fog sits flat on the
ground and tears away above it. The fog types (Ground Fog, Wispy Fog, Torn Low Cloud) are made
for low cloud drifting through a valley; layer two or three at different distances for
parallax. Layers are put over each other nearest first, per pixel.
'sky occlusion' (in 'more shape', after 'sky light') sets how much the cloud above darkens the
sky light below it, deepening bases and the folds between lobes: 1 for cumulus, lower for tall
storms and thick decks so they don't go flat grey (each type sets its own; 0 turns it off).
'shadow depth' (in 'more shape', after 'sky occlusion') sets how far light diffuses through the
cloud: 0 glows right through with soft, luminous shadows, 1 keeps the folds and cores dark (Storm
Anvil uses 0.7; the rest 0.3). Backlit edges keep their silver lining. With Manual light, 'haze
color' is tinted half way towards the sky colour's hue, so far clouds fade cool into the air
instead of into flat grey.
'layers shadow each other' (main tab, on by default) lets each layer shade the sunlit side of the
clouds below it in the other layers, so a cumulus deck under an altocumulus sheet goes patchy and
a hero cloud shades the deck beside it. Each layer renders a small map of its shadow seen from
the sun; a thick layer above dims the sun to a soft glow rather than black.

For quick look-dev, tick **preview**: half the resolution and march steps, one sample, and only
the passes the view needs (the node's label says PREVIEW). For fast playback, **bake now** renders
the Comp with all its layers to 'bake folder' (EXR, one folder per script and node) and plays it
back from disk ('use bake'); 'status' says when the settings changed since the bake (camera and
bg changes aren't tracked).

'show me variations' (main tab) shows nine seeds of one layer side by side ('next nine' for
more); type the number of the one you like (1 top left, 9 bottom right) into 'use number' and
press 'use it'.

Output: rgba (the comp, or a view), depth.Z (Planar Z of the clouds, scene units, for
EzCloudShafts), and with 'breakout layers' on: cloud (rgba), cloud_sun, cloud_sky, and
cloud_shadow (how much sun the clouds block on the bg's surface, 1 fully shaded; needs its depth).
The Comp view darkens the bg by 'shadow amount'; the Shadow view shows the shadows alone.
With 'motion vectors' on: forward.u/v and backward.u/v, in pixels, for VectorBlur. They follow
the camera, the wind drift and moving 3D boxes (the nearest layer wins where layers overlap).

Building (in NukeX, it compiles the kernel and writes its hash):

    Nuke15.1.exe --nukex -t python/build_group.py
    set EZCLOUDGEN_TEST_WIDTH=960
    Nuke15.1.exe --nukex -i --gpu -t python/test_render.py

`reference/blink_check/run_kernel.py` compiles the kernel on CPU with a small C++ stand-in for
Blink, to check edits without Nuke. `reference/sheets/nuke/` has the test renders from NukeX.

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
