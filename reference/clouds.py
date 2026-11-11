"""EzCloudGen prototype: a per-pixel volumetric cloud raymarcher written the way the Blink kernel
will be (scalar maths, one function per pixel), so it ports line for line.

Units: metres inside. Earth is curved (radius R), centre at (0, -R, 0); the camera sits at
(0, cam_y, 0) looking down -Z, pitched up by `pitch` degrees. Y is up.

Outputs per pixel: rgb (premultiplied), alpha, sun (direct sun share of rgb), sky (ambient
share), depth (transmittance weighted mean distance along the ray, metres).
"""

import math

import numpy as np
from numba import njit, prange

R_EARTH = 6371000.0

# ---- Cloud type parameter block -------------------------------------------------------------
# Index names for the per-layer parameter array (kept as plain floats so Blink can take them as
# knobs).
P = dict(
    base=0,         # cloud base height above ground, m
    thick=1,        # layer thickness, m
    coverage=2,     # 0..1 share of sky covered
    scale=3,        # weather (cloud placement) feature size, km
    stretch=4,      # elongation along the wind (1 = round)
    wind_deg=5,     # direction the shapes stretch along, deg from -Z towards +X
    edge=6,         # softness of the coverage edge
    taper=7,        # how much the cloud narrows going up (cumulus domes, 0 = flat top)
    bottom=8,       # bottom rounding as a share of the thickness (small = flat base)
    top=9,          # top rounding share
    detail=10,      # detail noise size, m
    erosion=11,     # how much detail noise eats the edges
    sigma=12,       # extinction per metre at density 1
    cells=13,       # cellular (mackerel / cirrocumulus) amount
    cell_km=14,     # cell size, km
    warp=15,        # domain warp of the weather map
    g=16,           # forward scattering (Henyey-Greenstein g)
    ambient=17,     # sky light amount
    octaves=18,     # detail octaves
    billow=19,      # 1 = billowy (cauliflower) detail, 0 = wispy
    streaks=20,     # 1 = ridged streaks (cirrus fibres)
    vary=21,        # height variation of the base/top across the deck, share of thickness
)
NP = len(P)


@njit(cache=True, fastmath=True)
def fr(v):
    return v - math.floor(v)


@njit(cache=True, fastmath=True)
def hash3(x, y, z):
    # Dave Hoskins' hash13, float only (Blink friendly).
    px = fr(x * 0.1031)
    py = fr(y * 0.1031)
    pz = fr(z * 0.1031)
    d = px * (py + 33.33) + py * (pz + 33.33) + pz * (px + 33.33)
    px += d
    py += d
    pz += d
    return fr((px + py) * pz)


@njit(cache=True, fastmath=True)
def vnoise3(x, y, z):
    ix = math.floor(x)
    iy = math.floor(y)
    iz = math.floor(z)
    fx = x - ix
    fy = y - iy
    fz = z - iz
    ux = fx * fx * fx * (fx * (fx * 6.0 - 15.0) + 10.0)
    uy = fy * fy * fy * (fy * (fy * 6.0 - 15.0) + 10.0)
    uz = fz * fz * fz * (fz * (fz * 6.0 - 15.0) + 10.0)
    a = hash3(ix, iy, iz)
    b = hash3(ix + 1, iy, iz)
    c = hash3(ix, iy + 1, iz)
    d = hash3(ix + 1, iy + 1, iz)
    e = hash3(ix, iy, iz + 1)
    f = hash3(ix + 1, iy, iz + 1)
    g = hash3(ix, iy + 1, iz + 1)
    h = hash3(ix + 1, iy + 1, iz + 1)
    k0 = a + (b - a) * ux
    k1 = c + (d - c) * ux
    k2 = e + (f - e) * ux
    k3 = g + (h - g) * ux
    l0 = k0 + (k1 - k0) * uy
    l1 = k2 + (k3 - k2) * uy
    return l0 + (l1 - l0) * uz


@njit(cache=True, fastmath=True)
def vnoise2(x, y):
    return vnoise3(x, y, 17.31)


@njit(cache=True, fastmath=True)
def fbm2(x, y, octaves):
    s = 0.0
    amp = 0.5
    tot = 0.0
    n = int(math.floor(octaves))
    for i in range(n + 1):
        w = 1.0 if i < n else octaves - n
        if w <= 0.0:
            break
        s += amp * w * vnoise2(x, y)
        tot += amp * w
        amp *= 0.5
        nx = 1.6 * x + 1.2 * y + 13.7
        y = -1.2 * x + 1.6 * y + 7.3
        x = nx
    return s / max(tot, 1e-6)


@njit(cache=True, fastmath=True)
def ridged2(x, y, octaves):
    s = 0.0
    amp = 0.5
    tot = 0.0
    n = int(math.floor(octaves))
    for i in range(n + 1):
        w = 1.0 if i < n else octaves - n
        if w <= 0.0:
            break
        v = 1.0 - abs(2.0 * vnoise2(x, y) - 1.0)
        s += amp * w * v * v
        tot += amp * w
        amp *= 0.55
        nx = 1.7 * x + 1.1 * y + 5.1
        y = -1.1 * x + 1.7 * y + 9.2
        x = nx
    return s / max(tot, 1e-6)


@njit(cache=True, fastmath=True)
def worley2(x, y):
    ix = math.floor(x)
    iy = math.floor(y)
    best = 9.0
    for j in range(-1, 2):
        for i in range(-1, 2):
            cx = ix + i
            cy = iy + j
            px = cx + hash3(cx, cy, 3.7)
            py = cy + hash3(cx, cy, 11.3)
            dx = px - x
            dy = py - y
            dd = dx * dx + dy * dy
            if dd < best:
                best = dd
    return math.sqrt(best)


@njit(cache=True, fastmath=True)
def worley3(x, y, z):
    ix = math.floor(x)
    iy = math.floor(y)
    iz = math.floor(z)
    best = 9.0
    for k in range(-1, 2):
        for j in range(-1, 2):
            for i in range(-1, 2):
                cx = ix + i
                cy = iy + j
                cz = iz + k
                dx = cx + hash3(cx, cy, cz) - x
                dy = cy + hash3(cy, cz, cx + 7.1) - y
                dz = cz + hash3(cz, cx, cy + 3.3) - z
                dd = dx * dx + dy * dy + dz * dz
                if dd < best:
                    best = dd
    return min(math.sqrt(best), 1.0)


@njit(cache=True, fastmath=True)
def detail3(x, y, z, octaves, billow):
    """Cloud detail: billowy (inverted Worley, cauliflower) mixed with wispy value fbm."""
    s = 0.0
    amp = 0.5
    tot = 0.0
    n = int(math.floor(octaves))
    for i in range(n + 1):
        w = 1.0 if i < n else octaves - n
        if w <= 0.0:
            break
        b = 1.0 - worley3(x, y, z)
        v = vnoise3(x * 1.3, y * 1.3, z * 1.3)
        s += amp * w * (billow * b + (1.0 - billow) * v)
        tot += amp * w
        amp *= 0.5
        x = x * 2.03 + 1.7
        y = y * 2.03 + 3.1
        z = z * 2.03 + 5.3
    return s / max(tot, 1e-6)


@njit(cache=True, fastmath=True)
def smoothstep(a, b, x):
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


@njit(cache=True, fastmath=True)
def weather(L, X, Z, foot, time):
    """2D cloud placement in 0..1 (before the height profile), at ground position X, Z (m)."""
    sc = L[3] * 1000.0
    a = L[5] * math.pi / 180.0
    ca = math.cos(a)
    sa = math.sin(a)
    # Wind drift.
    X = X - sa * time
    Z = Z + ca * time
    # Rotate into the wind frame and stretch along it.
    u = (X * ca + Z * sa) / sc
    v = (-X * sa + Z * ca) / (sc * L[4])
    oct = min(6.0, max(1.0, math.log2(max(sc / max(foot, 1.0), 1.0)) - 0.5))
    wx = fbm2(u * 0.5 + 3.1, v * 0.5, 3.0) - 0.5
    wz = fbm2(u * 0.5 + 9.7, v * 0.5 + 5.0, 3.0) - 0.5
    u2 = u + wx * L[15]
    v2 = v + wz * L[15]
    if L[20] > 0.5:
        f = ridged2(u2, v2, oct)
        f = f * (0.55 + 0.9 * fbm2(u * 0.3 + 40.0, v * 0.3, 3.0))
    else:
        f = fbm2(u2, v2, oct)
    # Coverage: positive inside the cloud footprint.
    c = f - (0.82 - 0.55 * L[2])
    if L[13] > 0.0:
        cs = L[14] * 1000.0
        cu = (X * ca + Z * sa) / cs
        cv = (-X * sa + Z * ca) / (cs * 0.6)
        # Fade the cells out when they get smaller than a pixel.
        fade = smoothstep(1.5, 5.0, cs / max(foot, 1.0))
        cell = worley2(cu + wx * 0.8, cv + wz * 0.8)
        c = c - L[13] * fade * (cell - 0.45) * 0.35
    return c


@njit(cache=True, fastmath=True)
def profile(L, hn):
    """How much the coverage shrinks at height hn (0 base, 1 top): rounds the base, the top and
    (with taper) makes domes, since only the strongest parts of the field reach the top."""
    k = 0.3 * (1.0 - smoothstep(0.0, max(L[8], 1e-3), hn))
    k += 0.3 * smoothstep(1.0 - max(L[9], 1e-3), 1.0, hn)
    k += L[7] * 0.32 * hn * math.sqrt(hn)
    return k


@njit(cache=True, fastmath=True)
def density(L, x, y, z, foot, time, cheap):
    """Cloud density 0..1 at world point (m), y up, curved earth."""
    dy = y + R_EARTH
    alt = math.sqrt(x * x + dy * dy + z * z) - R_EARTH
    base = L[0]
    thick = L[1]
    c = weather(L, x, z, foot, time)
    if c <= -0.12:
        return 0.0
    if L[21] > 0.0:
        # Base and top move up and down a little across the deck.
        off = (vnoise2(x / (L[3] * 2500.0) + 70.0, z / (L[3] * 2500.0)) - 0.5) * L[21] * thick
        base += off
    hn = (alt - base) / thick
    if hn <= 0.0 or hn >= 1.0:
        return 0.0
    c -= profile(L, hn)
    edge = max(L[6], 1e-3)
    if cheap or L[11] <= 0.0:
        return min(max(c / edge, 0.0), 1.0)
    if c < -0.12 * L[11]:
        return 0.0
    ds = L[10]
    oct = min(L[18], max(0.0, math.log2(max(ds / max(2.5 * foot, 1.0), 1.0))))
    if oct > 0.0:
        # Detail displaces the cloud surface; it rises slowly (boil).
        n = detail3(x / ds, (y - time * 0.3) / ds, z / ds, oct, L[19])
        c += L[11] * (n - 0.5) * 0.24
    return min(max(c / edge, 0.0), 1.0)


@njit(cache=True, fastmath=True)
def hg(g, c):
    gg = g * g
    return (1.0 - gg) / (4.0 * math.pi * (1.0 + gg - 2.0 * g * c) ** 1.5)


@njit(cache=True, fastmath=True)
def sphere_hits(ox, oy, oz, dx, dy, dz, r):
    """Ray vs sphere centred (0, -R, 0). Returns (hit, t0, t1)."""
    cy = oy + R_EARTH
    b = ox * dx + cy * dy + oz * dz
    c = ox * ox + cy * cy + oz * oz - r * r
    disc = b * b - c
    if disc < 0.0:
        return False, 0.0, 0.0
    s = math.sqrt(disc)
    return True, -b - s, -b + s


@njit(cache=True, fastmath=True)
def shell_intervals(ox, oy, oz, dx, dy, dz, rb, rt, tmax):
    """Up to two [t0, t1] intervals where the ray is inside the shell rb..rt, before the ground."""
    out = np.zeros(4)
    n = 0
    ho, a0, a1 = sphere_hits(ox, oy, oz, dx, dy, dz, rt)
    if not ho or a1 <= 0.0:
        return out, 0
    hg_, g0, g1 = sphere_hits(ox, oy, oz, dx, dy, dz, R_EARTH)
    if hg_ and g0 > 0.0:
        tmax = min(tmax, g0)
    hi, b0, b1 = sphere_hits(ox, oy, oz, dx, dy, dz, rb)
    s0 = max(a0, 0.0)
    s1 = min(a1, tmax)
    if not hi:
        if s1 > s0:
            out[0] = s0
            out[1] = s1
            n = 1
        return out, n
    # [a0, a1] minus (b0, b1)
    if min(b0, s1) > s0:
        out[0] = s0
        out[1] = min(b0, s1)
        n = 1
    if s1 > max(b1, s0):
        out[2 * n] = max(b1, s0)
        out[2 * n + 1] = s1
        n += 1
    return out, n


@njit(cache=True, fastmath=True)
def sun_od(L, x, y, z, sx, sy, sz, foot, time, steps):
    """Optical depth (density sum * metres) from a point towards the sun, inside the layer."""
    # Distance to leave the layer top along the sun.
    h, t0, t1 = sphere_hits(x, y, z, sx, sy, sz, R_EARTH + L[0] + L[1] * (1.0 + L[21]))
    far = max(t1, 0.0)
    far = min(far, 6.0 * L[1] / max(sy, 0.08), 12000.0)
    od = 0.0
    prev = 0.0
    for i in range(steps):
        # Steps grow away from the sample: fine near the edge, coarse deep in.
        f = (i + 0.5) / steps
        t = far * f * f
        dt = t - prev
        prev = t
        dd = density(L, x + sx * t, y + sy * t, z + sz * t, foot + t * 0.02, time, i > 1)
        od += dd * dt * 1.0
    return od


@njit(cache=True, fastmath=True)
def atmos_trans(elev_sin, alt):
    """Sun colour through the air down to `alt` (m), simple airmass model. Returns r, g, b."""
    br = (5.8e-6, 13.5e-6, 33.1e-6)
    bm = 21e-6
    e = max(elev_sin, -0.05)
    zen = math.acos(min(max(e, -1.0), 1.0)) * 180.0 / math.pi
    am = 1.0 / (max(e, 0.0) + 0.50572 * max(96.07995 - zen, 0.5) ** -1.6364)
    hr = 8000.0 * math.exp(-alt / 8000.0)
    hm = 1200.0 * math.exp(-alt / 1200.0)
    r = math.exp(-(br[0] * hr + bm * hm * 0.35) * am)
    g = math.exp(-(br[1] * hr + bm * hm * 0.35) * am)
    b = math.exp(-(br[2] * hr + bm * hm * 0.35) * am)
    return r, g, b


@njit(parallel=True, cache=True, fastmath=True)
def render(Ls, nl, width, height, cam_y, pitch, yaw, focal, hap, sun_elev, sun_az,
           sun_int, sky_col, gnd_col, haze_beta, haze_col, max_dist, quality, samples, time):
    out = np.zeros((height, width, 8), dtype=np.float32)
    se = sun_elev * math.pi / 180.0
    sa = sun_az * math.pi / 180.0
    sx = math.cos(se) * math.sin(sa)
    sy = math.sin(se)
    sz = -math.cos(se) * math.cos(sa)
    pr = pitch * math.pi / 180.0
    yr = yaw * math.pi / 180.0
    cp = math.cos(pr)
    sp = math.sin(pr)
    cyw = math.cos(yr)
    syw = math.sin(yr)
    vap = hap * height / width
    pix_ang = hap / focal / width
    for j in prange(height):
        for i in range(width):
            acc = np.zeros(8)
            for s in range(samples):
                jx = hash3(i + 0.5, j + 0.5, s * 7.0 + time * 13.0)
                jy = hash3(j + 1.5, i + 2.5, s * 3.0 + 5.0)
                u = ((i + jx) / width - 0.5) * hap / focal
                v = (0.5 - (j + jy) / height) * vap / focal
                # Camera looks down -Z, pitched up, then yawed.
                cx = u
                cyy = v * cp + sp
                cz = v * sp - cp
                dx = cx * cyw - cz * syw
                dz = cx * syw + cz * cyw
                dy = cyy
                ln = math.sqrt(dx * dx + dy * dy + dz * dz)
                dx /= ln
                dy /= ln
                dz /= ln
                cos_t = dx * sx + dy * sy + dz * sz
                T = 1.0
                cr = 0.0
                cg = 0.0
                cb = 0.0
                sr = 0.0
                sg = 0.0
                sb = 0.0
                dep = 0.0
                for li in range(nl):
                    L = Ls[li]
                    rb = R_EARTH + L[0] - L[1] * L[21]
                    rt = R_EARTH + L[0] + L[1] * (1.0 + L[21])
                    iv, n = shell_intervals(0.0, cam_y, 0.0, dx, dy, dz, rb, rt, max_dist)
                    # Phase with multiple scattering octaves (Wrenninge).
                    for k in range(n):
                        t0 = iv[2 * k]
                        t1 = iv[2 * k + 1]
                        t = t0 + hash3(i * 1.7, j * 2.3, s + 31.0 * li + k) * 0.0
                        minstep = max(min(L[1] / 24.0, L[10] * 0.35) / quality, 8.0)
                        first = True
                        steps = 0
                        while t < t1 and T > 0.01 and steps < int(220 * quality):
                            steps += 1
                            foot = max(t * pix_ang, 0.5)
                            dt = max(minstep, t * 0.012 / quality)
                            if first:
                                dt *= hash3(i * 1.7, j * 2.3, s + 31.0 * li + k) + 0.02
                                first = False
                            dt = min(dt, t1 - t + 1e-3)
                            tm = t + 0.5 * dt
                            x = dx * tm
                            y = cam_y + dy * tm
                            z = dz * tm
                            d = density(L, x, y, z, foot, time, False)
                            if d > 0.0:
                                sig = d * L[12]
                                alt = math.sqrt(x * x + (y + R_EARTH) ** 2 + z * z) - R_EARTH
                                od = sun_od(L, x, y, z, sx, sy, sz, foot, time, int(6 * quality)) * L[12]
                                tr, tg, tb = atmos_trans(sy, alt)
                                # Multiple scattering octaves.
                                ms = 0.0
                                a = 1.0
                                bb = 1.0
                                cc = 1.0
                                for o in range(4):
                                    ph = 0.75 * hg(L[16] * cc, cos_t) + 0.25 * hg(-0.25 * cc, cos_t)
                                    ms += bb * math.exp(-od * a) * ph
                                    a *= 0.3
                                    bb *= 0.6
                                    cc *= 0.5
                                # Powder: dark edges facing away from the sun.
                                powder = 1.0 - 0.6 * math.exp(-sig * 160.0)
                                sun_s = ms * powder * sun_int
                                # Ambient: sky from above, ground bounce from below.
                                hn = min(max((alt - L[0]) / L[1], 0.0), 1.0)
                                amb_up = math.exp(-sig * (1.0 - hn) * min(L[1], 1500.0) * 0.12)
                                amb_dn = math.exp(-sig * hn * min(L[1], 1500.0) * 0.12) * 0.35
                                ar = L[17] * (sky_col[0] * amb_up + gnd_col[0] * amb_dn)
                                ag = L[17] * (sky_col[1] * amb_up + gnd_col[1] * amb_dn)
                                ab = L[17] * (sky_col[2] * amb_up + gnd_col[2] * amb_dn)
                                ext = math.exp(-sig * dt)
                                wgt = T * (1.0 - ext)
                                # Aerial perspective between camera and sample.
                                hz = math.exp(-haze_beta * tm)
                                cr += wgt * (hz * (sun_s * tr + ar) + (1.0 - hz) * haze_col[0])
                                cg += wgt * (hz * (sun_s * tg + ag) + (1.0 - hz) * haze_col[1])
                                cb += wgt * (hz * (sun_s * tb + ab) + (1.0 - hz) * haze_col[2])
                                sr += wgt * hz * sun_s * tr
                                sg += wgt * hz * sun_s * tg
                                sb += wgt * hz * sun_s * tb
                                dep += wgt * tm
                                T *= ext
                            t += dt
                a_ = 1.0 - T
                acc[0] += cr
                acc[1] += cg
                acc[2] += cb
                acc[3] += a_
                acc[4] += sr
                acc[5] += sg
                acc[6] += sb
                acc[7] += dep / a_ if a_ > 1e-5 else 0.0
            for c in range(8):
                out[j, i, c] = acc[c] / samples
    return out


@njit(parallel=True, cache=True, fastmath=True)
def background(width, height, pitch, focal, hap, sun_elev, sun_az, sun_int, sky_col, haze_col, gnd_col):
    """A simple sky + ground backdrop for previews (in Nuke this is the HDRI / plate)."""
    out = np.zeros((height, width, 3), dtype=np.float32)
    se = sun_elev * math.pi / 180.0
    sa = sun_az * math.pi / 180.0
    sx = math.cos(se) * math.sin(sa)
    sy = math.sin(se)
    sz = -math.cos(se) * math.cos(sa)
    pr = pitch * math.pi / 180.0
    cp = math.cos(pr)
    sp = math.sin(pr)
    vap = hap * height / width
    for j in prange(height):
        for i in range(width):
            u = ((i + 0.5) / width - 0.5) * hap / focal
            v = (0.5 - (j + 0.5) / height) * vap / focal
            dx = u
            dy = v * cp + sp
            dz = v * sp - cp
            ln = math.sqrt(dx * dx + dy * dy + dz * dz)
            dx /= ln
            dy /= ln
            dz /= ln
            c = dx * sx + dy * sy + dz * sz
            if dy > -0.004:
                hgt = max(dy, 0.0)
                f = math.exp(-hgt * 6.0)
                mie = hg(0.76, c) * 0.25 * sun_int
                for k in range(3):
                    out[j, i, k] = sky_col[k] * 1.1 * (1.0 - f) + haze_col[k] * f + mie * haze_col[k] * 0.4
                if c > 0.99996:
                    for k in range(3):
                        out[j, i, k] += 400.0 * sun_int * haze_col[k]
            else:
                f = math.exp(-(-dy) * 30.0)
                for k in range(3):
                    out[j, i, k] = gnd_col[k] * 0.5 * (1.0 - f) + haze_col[k] * f
    return out
