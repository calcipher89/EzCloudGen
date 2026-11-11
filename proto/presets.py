"""Cloud type presets for the prototype. Heights in metres, scales in km."""

import numpy as np

from clouds import NP, P


def layer(**kw):
    d = dict(base=1500, thick=1000, coverage=0.5, scale=2.0, stretch=1.0, wind_deg=20, edge=0.12,
             taper=0.0, bottom=0.08, top=0.3, detail=180, erosion=0.5, sigma=0.04, cells=0.0,
             cell_km=0.5, warp=1.5, g=0.8, ambient=1.0, octaves=3, billow=1.0, streaks=0.0, vary=0.0)
    d.update(kw)
    a = np.zeros(NP)
    for k, v in d.items():
        a[P[k]] = v
    return a


TYPES = {
    # Fair weather cumulus: flat bases, cauliflower domes, blue gaps.
    "Cumulus": layer(base=1400, thick=1300, coverage=0.42, scale=1.6, edge=0.06, taper=0.85, bottom=0.04,
                     top=0.15, detail=220, erosion=0.45, sigma=0.06, warp=1.2, octaves=3.5, billow=1.0),
    # Towering cumulus: tall, few, hard edged.
    "Cumulus Congestus": layer(base=1400, thick=4200, coverage=0.42, scale=2.2, edge=0.05, taper=1.4,
                               bottom=0.02, top=0.12, detail=420, erosion=0.4, sigma=0.07, warp=1.0,
                               octaves=4, billow=1.0),
    # Stratocumulus: low lumpy deck with gaps (the EzCloudShafts demo look).
    "Stratocumulus": layer(base=1300, thick=600, coverage=0.66, scale=1.1, stretch=1.4, edge=0.16,
                           taper=0.35, bottom=0.15, top=0.35, detail=120, erosion=0.45, sigma=0.035,
                           warp=1.8, octaves=3, billow=0.8, vary=0.15),
    # Stratus: low grey sheet, soft base, little texture.
    "Stratus": layer(base=500, thick=450, coverage=0.97, scale=4.0, stretch=1.5, edge=0.35, taper=0.0,
                     bottom=0.35, top=0.3, detail=220, erosion=0.25, sigma=0.02, warp=1.0, octaves=2,
                     billow=0.2, vary=0.3),
    # Altocumulus: mid level mackerel rows of small puffs.
    "Altocumulus": layer(base=4200, thick=350, coverage=0.62, scale=2.5, stretch=2.0, edge=0.14, taper=0.3,
                         bottom=0.25, top=0.35, detail=60, erosion=0.5, sigma=0.03, cells=0.85,
                         cell_km=0.35, warp=1.6, octaves=2.5, billow=0.9),
    # Altostratus / overcast: thick mid grey layer, sun as a dim disk.
    "Altostratus": layer(base=3000, thick=1500, coverage=1.0, scale=6.0, stretch=1.5, edge=0.4, taper=0.0,
                         bottom=0.3, top=0.3, detail=300, erosion=0.2, sigma=0.006, warp=1.0, octaves=2,
                         billow=0.3, vary=0.2, g=0.85),
    # Cirrus: high thin ice fibres, strongly stretched.
    "Cirrus": layer(base=9000, thick=500, coverage=0.5, scale=5.0, stretch=7.0, wind_deg=35, edge=0.25,
                    taper=0.0, bottom=0.4, top=0.4, detail=150, erosion=0.6, sigma=0.0012, warp=2.5,
                    octaves=2, billow=0.0, streaks=1.0, g=0.85, ambient=1.2),
    # Cirrocumulus: high, tiny grain-like ripples.
    "Cirrocumulus": layer(base=7500, thick=250, coverage=0.55, scale=3.0, stretch=2.5, wind_deg=-30,
                          edge=0.15, taper=0.0, bottom=0.35, top=0.35, detail=40, erosion=0.45, sigma=0.008,
                          cells=1.0, cell_km=0.22, warp=2.0, octaves=2, billow=0.7, g=0.85),
}
