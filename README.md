# EzCloudGen

A procedural, volumetric cloud generator for Nuke, built to sit alongside the ezTools
(EzAtmosScatter, EzDepthHaze, EzCloudShafts). It will ship as a self-contained Group and a gizmo,
with all code and settings in the node's knobs (no init.py or menu.py).

## Status

v0.23.1: the Group (`groups/EzCloudGen_group.nk`) and gizmo (`gizmos/EzCloudGen.gizmo`) build and
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
deck (Cumulus ... Cirrocumulus) or a placed volume (Hero Cumulus, Soft Cumulus, Storm Anvil, Fog Bank, Puff):
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
parallax. The layers are marched together, one ray through all three: where they overlap (a
deck crossing a hero cloud, a tower rising through a deck, fog banks one behind another) their
clouds interleave sample by sample instead of one whole layer being drawn over the other, so there
are no hard seams or dotted outlines where they meet. A layer alone renders exactly as it did.
'billow light' (by 'detail sharpness'; 0 = as before) lights each billow on its own: the light march
looks a billow towards the sun with the fine detail, so every lobe gets a sunlit side and a shaded far
side, and the creases between lobes go dark. 'billow shrink' gives big, soft lobes low in a cloud and
tighter cauliflower near its top. For photographic cumulus use 'light diffusion' 1, 'detail
sharpness' about 0.6, 'billow light' 1 and 'billow shrink' about 0.6.
'map softness' (coverage map, default 0.5) frays and blurs the painted edges over part of a cloud's
size, so a hard edge in the map comes out as cloud thinning out rather than a straight wall.
Cleaner silhouettes: the march now takes its fine edge steps from the band where a cloud's detail
can reach, not only once it has hit cloud, so thin bright rims are no longer stepped over in one
pixel and caught in the next (the dithered, jagged fringe round clouds against the sky). Several
samples per pixel are spread evenly over the pixel and over a step, and bright samples count for
less when they are averaged, so an edge half on a blazing cloud and half on sky blends instead of
clipping to white. The render time is about the same.
'sky occlusion' (in 'more shape', after 'sky light') sets how much the cloud above darkens the
sky light below it, deepening bases and the folds between lobes: 1 for cumulus, lower for tall
storms and thick decks so they don't go flat grey (each type sets its own; 0 turns it off).
'shadow depth' (in 'more shape', after 'sky occlusion') sets how far light diffuses through the
cloud: 0 glows right through with soft, luminous shadows, 1 keeps the folds and cores dark (Storm
Anvil uses 0.7; the rest 0). Backlit edges keep their silver lining. With Manual light, 'haze
color' is tinted half way towards the sky colour's hue, so far clouds fade cool into the air
instead of into flat grey.
'lumps' and 'lump size' break a layer into big rounded lobes, on decks as well as volumes (Cumulus
and Cumulus Congestus use them), and 'small lumps' adds a second set a bit under half the size
riding on them, for cauliflower heads. Cumulus keep a flat base: the lobes run straight down to it
from a fifth of the way up, and the base itself is thin and ragged, not a plate.
'skirt' (after 'small lumps') gives smooth, firm billows on top and a wide, soft skirt of wisps
around the base: it calms the erosion higher up, and widens the edge and feeds the wisps low down;
the lobes die away into the base, so it stays soft and even from below.
The Soft Cumulus type uses it, with more sky light, for a softer, more photographic cloud (see the
SoftCloud demo).
'sun glow' (by the light knobs; 0 = off) adds the narrow forward peak real cloud droplets have: thin
cloud in front of the sun blazes and backlit edges get a hot silver lining, while thick cores stay
dark. Use 0.3 to 1 for shots into the sun, with 'highlight rolloff'.
'light diffusion' (by 'sun glow'; 0 = the older look) lights the clouds the way thick real cloud
takes sunlight: light scattered many times fades slowly with depth (1 / (1 + k tau), from diffusion
theory) instead of dying off, so sunlit sides are bright white, billows shade off gradually round
their sides and the cores stay a luminous grey. Use 1 for photographic clouds, with 'highlight
rolloff' 0.3 to 0.5 and 'exposure' to place the whites.
Fixed in this version, all of which showed as bright outlines or dotted seams where clouds overlap:
the depth of a cloud's edge pixels was averaged over the samples that missed it too (so far cloud
edges were drawn in front of nearer cloud); a thick cloud stopped at 99% opaque, so a sun or a
blazing rim behind it leaked through as an outline; and two layers at about the same depth flipped
order from pixel to pixel (the order now fades between them). 'highlight rolloff' also has a
gentler shoulder, so bright cloud keeps its shading instead of going to a flat white.
Where the coverage map thins a deck, the clouds that are left keep the layer's density (fewer,
smaller clouds) instead of turning into thin see-through veils. Paint maps with soft edges: a hard
edge in the map still stands up as a straight wall through a tall deck. The Storm Anvil's thin rim
holds a minimum thickness, so it no longer breaks up into speckle.
Volume shape **Shelf** and the **Shelf Cloud** type: a one-sided cloud shelf, thick and low at its
box's -x end, thinning and lifting to a torn, streaky trailing edge at +x. Turn the box to point it.
'detail sharpness' (by 'light diffusion'; 0 = as before) keeps more of the finer billow octaves and
hardens the surface, for crisp cauliflower edges. With a self-lit EzAtmosScatter, the sun colour
follows its 'white balance'.
Cumulus and Cumulus Congestus decks have rounder bases ('base rounding' 0.1, was 0.04 and 0.02): a
near-flat base showed as banded, terraced undersides when seen from close below.
The Towering Cumulus type (shape Towers) is a cumulus complex: a few tall towers on a wider,
flat-based shelf with a ragged footprint, made to stand in front of the sun.
With an EzAtmosScatter that is self-lit (no HDRI), 'light from' Auto takes the sky light from the
atmos's own sky and the sun from its manual sun, dimmed by the air it crosses at that sun height.
'sun shadow layer' (main tab, on by default, with 'breakout layers') adds cloud_sunmap: all the
layers' shadow seen from the sun. Plug the node into EzCloudShafts' clouds input and its rays and
ground shadows are cast by the real volumes, tall clouds and clouds outside the frame included.
'exposure' (stops) and 'highlight rolloff' (by the light knobs) act on the clouds only, not the bg.
Rolloff bends the highlights towards 1 instead of letting them run past it (sunlit tops seen towards
the sun blow out in a plain sRGB view); it keeps the hue, scales the sun share alike, and 0 leaves the
render linear.
'edge steps' (main tab, by 'quality'; default 3) takes finer ray steps where a ray meets cloud, and
the sun's shadow march takes 10 steps (was 6), so surfaces and edges come out clean instead of
grainy at one sample; it costs roughly 1.5 to 2 times the render time, and the preview turns it
off. For the last of the dither on thin edges use 2 samples.
'layers shadow each other' (main tab, on by default) lets each layer shade the sunlit side of the
clouds below it in the other layers, so a cumulus deck under an altocumulus sheet goes patchy and
a hero cloud shades the deck beside it. Each layer renders a small map of its shadow seen from
the sun; a thick layer above dims the sun to a soft glow rather than black.

For quick look-dev, tick **preview**: half the resolution and march steps, one sample, and only
the passes the view needs (the node's label says PREVIEW). For fast playback or the farm, precomp
the node with your own Write (channels all keeps every layer) and read it back.

'show me variations' (main tab) shows nine seeds of one layer side by side ('next nine' for
more); type the number of the one you like (1 top left, 9 bottom right) into 'use number' and
press 'use it'.

Output: rgba (the comp, or a view), depth.Z (Planar Z of the clouds, scene units, for
EzCloudShafts), and with 'breakout layers' on: cloud (rgba), cloud_sun, cloud_sky, and
cloud_shadow (how much sun the clouds block on the bg's surface, 1 fully shaded; needs its depth).
The Comp view darkens the bg by 'shadow amount'; the Shadow view shows the shadows alone.
With 'motion vectors' on: forward.u/v and backward.u/v, in pixels, for VectorBlur. They follow
the camera, the wind drift and moving 3D boxes (where layers overlap, each layer's motion counts by
how much of the pixel it covers).

Building (in NukeX, it compiles the kernel and writes its hash):

    Nuke15.1.exe --nukex -t python/build_group.py
    set EZCLOUDGEN_TEST_WIDTH=960
    Nuke15.1.exe --nukex -i --gpu -t python/test_render.py

`reference/blink_check/run_kernel.py` compiles the kernel on CPU with a small C++ stand-in for
Blink, to check edits without Nuke (per-layer settings: `base=2000` is layer 1, `base.2=5000`
layer 2, `layer_on.2=1` turns it on). On the CPU, Nuke takes about 13 minutes to compile the
kernel the first time (30 s on the GPU). `reference/sheets/nuke/` has the test renders from NukeX.

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

- 'earth' (scene section) is Flat by default: the ground is a plane pinned to the world, so a
  camera can climb, dive and fly through the decks and every cloud keeps its shape and place out
  to an eye-level horizon. Curved is the real earth (6371 km), its top at the scene origin: from
  high up the far decks sink behind the true horizon and lose their bases, as in aerial photos.
- Below the horizon the node draws no ground. 'horizon haze' (by 'haze distance', default 1) lays
  the haze over the far ground, thick at the horizon and thinning towards the camera, so the decks
  sink into haze instead of ending on a straight line; turn it off over a plate that has its own
  ground and no depth. 'max distance' (default 400 km) fades the clouds out towards it, so it never
  cuts them hard. A deck's base ('vary') has a broad and a fine height variation, so seen at eye
  level it is a ragged edge, not a ruled line.
- Stratus and Altostratus are too flat; Cirrus needs finer fibres; Congestus is grainy up close.
