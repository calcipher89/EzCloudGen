"""The cloud types: one shared table for the Nuke build (python/build_group.py) and the
prototype (reference/presets.py). Heights in metres, sizes in km unless named _m.

Keys are the prototype's names; KERNEL maps them to the Blink kernel's parameters.
"""

DEFAULTS = dict(base=1500, thick=1000, coverage=0.5, scale=2.0, stretch=1.0, wind_deg=20, edge=0.12,
                taper=0.0, bottom=0.08, top=0.3, detail=180, erosion=0.5, sigma=0.04, cells=0.0,
                cell_km=0.5, warp=1.5, g=0.8, ambient=1.0, octaves=3, billow=1.0, streaks=0.0, vary=0.0,
                # Placed volumes (volume=1): shape 0 ellipsoid, 1 dome, 2 anvil, 3 box; size in m (full);
                # place_km: how far in front of the camera 'place in front of camera' puts it.
                volume=0, vol_shape=1, vol_size=(3000, 1800, 3000), lumps=0.5, lump_size=600, place_km=10,
                # Erosion stack (billows are detail/erosion above).
                wisp_size=60, wisp_amount=0.0, grain_size=15, grain_amount=0.0, swirl=0.0, swirl_size=400,
                shear=0.0)

KERNEL = dict(base="base", thick="thickness", coverage="coverage", scale="scale_km", stretch="stretch",
              wind_deg="wind_deg", edge="edge", taper="taper", bottom="bottom_round", top="top_round",
              detail="detail_size", erosion="erosion", sigma="sigma", cells="cells", cell_km="cell_km",
              warp="warp", g="forward", ambient="ambient", octaves="octaves", billow="billow",
              streaks="streaks", vary="vary", volume="volume", vol_shape="vol_shape", vol_size="vol_size",
              lumps="lumps", lump_size="lump_size", place_km="place_km", wisp_size="wisp_size",
              wisp_amount="wisp_amount", grain_size="grain_size", grain_amount="grain_amount", swirl="swirl",
              swirl_size="swirl_size", shear="shear")

TYPES = {
    # Fair weather cumulus: flat bases, cauliflower domes, blue gaps.
    "Cumulus": dict(base=1400, thick=1300, coverage=0.42, scale=1.6, edge=0.06, taper=0.85, bottom=0.04,
                     top=0.15, detail=220, erosion=0.45, sigma=0.06, warp=1.2, octaves=3.5, billow=1.0),
    # Towering cumulus: tall, few, hard edged.
    "Cumulus Congestus": dict(base=1400, thick=4200, coverage=0.42, scale=2.2, edge=0.05, taper=1.4,
                               bottom=0.02, top=0.12, detail=420, erosion=0.4, sigma=0.07, warp=1.0,
                               octaves=4, billow=1.0),
    # Stratocumulus: low lumpy deck with gaps (the EzCloudShafts demo look).
    "Stratocumulus": dict(base=1300, thick=600, coverage=0.66, scale=1.1, stretch=1.4, edge=0.16,
                           taper=0.35, bottom=0.15, top=0.35, detail=120, erosion=0.45, sigma=0.035,
                           warp=1.8, octaves=3, billow=0.8, vary=0.15),
    # Stratus: low grey sheet, soft base, little texture.
    "Stratus": dict(base=500, thick=450, coverage=0.97, scale=4.0, stretch=1.5, edge=0.35, taper=0.0,
                     bottom=0.35, top=0.3, detail=220, erosion=0.25, sigma=0.02, warp=1.0, octaves=2,
                     billow=0.2, vary=0.3),
    # Altocumulus: mid level mackerel rows of small puffs.
    "Altocumulus": dict(base=4200, thick=350, coverage=0.62, scale=2.5, stretch=2.0, edge=0.14, taper=0.3,
                         bottom=0.25, top=0.35, detail=60, erosion=0.5, sigma=0.03, cells=0.85,
                         cell_km=0.35, warp=1.6, octaves=2.5, billow=0.9),
    # Altostratus / overcast: thick mid grey layer, sun as a dim disk.
    "Altostratus": dict(base=3000, thick=1500, coverage=1.0, scale=6.0, stretch=1.5, edge=0.4, taper=0.0,
                         bottom=0.3, top=0.3, detail=300, erosion=0.2, sigma=0.006, warp=1.0, octaves=2,
                         billow=0.3, vary=0.2, g=0.85),
    # Cirrus: high thin ice fibres, strongly stretched.
    "Cirrus": dict(base=9000, thick=500, coverage=0.5, scale=5.0, stretch=7.0, wind_deg=35, edge=0.25,
                    taper=0.0, bottom=0.4, top=0.4, detail=150, erosion=0.6, sigma=0.0012, warp=2.5,
                    octaves=2, billow=0.0, streaks=1.0, g=0.85, ambient=1.2),
    # Cirrocumulus: high, tiny grain-like ripples.
    "Cirrocumulus": dict(base=7500, thick=250, coverage=0.55, scale=3.0, stretch=2.5, wind_deg=-30,
                          edge=0.15, taper=0.0, bottom=0.35, top=0.35, detail=40, erosion=0.45, sigma=0.008,
                          cells=1.0, cell_km=0.22, warp=2.0, octaves=2, billow=0.7, g=0.85),
    # ---- Placed volumes: pick one and it drops in front of the camera. ----
    # A hero cumulus: flat base, lumpy towers, wispy edges.
    "Hero Cumulus": dict(volume=1, vol_shape=1, vol_size=(5000, 2600, 4000), base=1400, lumps=0.8,
                         lump_size=900, place_km=12, coverage=0.5, edge=0.06, taper=0.0, bottom=0.04,
                         detail=220, erosion=0.45, sigma=0.06, warp=1.2, octaves=3, billow=1.0,
                         wisp_size=80, wisp_amount=0.12, grain_size=20, grain_amount=0.08),
    # A thunderstorm: a tall column spreading into a flat anvil, leaning downwind.
    "Storm Anvil": dict(volume=1, vol_shape=2, vol_size=(15000, 11000, 15000), base=1200, lumps=0.6,
                        lump_size=1500, place_km=40, coverage=0.5, edge=0.05, bottom=0.02, detail=450,
                        erosion=0.4, sigma=0.07, octaves=4, billow=1.0, wisp_size=200, wisp_amount=0.25,
                        shear=0.3),
    # A low fog bank: wide, thin, soft and swirly.
    "Fog Bank": dict(volume=1, vol_shape=3, vol_size=(8000, 600, 8000), base=0, lumps=0.6, lump_size=600,
                     place_km=6, coverage=0.5, edge=0.3, bottom=0.4, detail=120, erosion=0.3, sigma=0.01,
                     billow=0.2, octaves=2, wisp_size=40, wisp_amount=0.6, swirl=0.4, swirl_size=200,
                     g=0.7, ambient=1.2),
    # A single small puff.
    "Puff": dict(volume=1, vol_shape=0, vol_size=(600, 450, 600), base=800, lumps=0.4, lump_size=150,
                 place_km=2, coverage=0.5, edge=0.08, detail=60, erosion=0.5, sigma=0.05, octaves=3,
                 billow=1.0, wisp_size=20, wisp_amount=0.4, grain_size=6, grain_amount=0.3),
}


def full(name):
    """The type's values with the defaults filled in, keyed by kernel parameter name."""
    d = dict(DEFAULTS)
    d.update(TYPES[name])
    return dict((KERNEL[k], v) for k, v in d.items())
