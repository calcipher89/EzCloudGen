# 'analyze scene': reads the node's inputs (the bg's depth as numbers on a coarse grid, the
# camera, the sun and light inputs) and sets the scene knobs to match. Only numbers are read:
# no picture leaves the node. Undoable in one step. Writes what it found to 'analysis'.
import math

GX, GY = 32, 18


def _find(n, idx, knob):
    c = n.input(idx)
    while c is not None and not c.knob(knob):
        c = c.input(0) if c.inputs() else None
    return c


def _pct(vals, q):
    if not vals:
        return 0.0
    v = sorted(vals)
    i = min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))
    return v[i]


def _depth_channel(n, bg):
    chans = list(bg.channels())
    cur = n['depth_channel'].value()
    cur = {'depth': 'depth.Z'}.get(cur, cur)
    if cur in chans:
        return cur
    if 'depth.Z' in chans:
        return 'depth.Z'
    for test in (lambda c: c.endswith('.Z') and 'depth' in c.lower(),
                 lambda c: 'depth' in c.lower(),
                 lambda c: c.endswith('.Z') or c.endswith('.z')):
        for c in chans:
            if test(c):
                return c
    return None


def _scanline_on_b(bg):
    # ScanlineRender (or RayRender) up the B pipe: its depth is 1/Z.
    x, seen = bg, 0
    while x is not None and seen < 300:
        if x.Class() in ('ScanlineRender', 'ScanlineRender2', 'RayRender'):
            return True
        x = x.input(0) if x.inputs() else None
        seen += 1
    return False


def analyze(n):
    undo = nuke.Undo()
    undo.begin('EzCloudGen analyze scene')
    try:
        text = _analyze(n)
    finally:
        undo.end()
    n['analysis'].setValue(text)
    if nuke.GUI:
        nuke.message('EzCloudGen: analyze scene\n\n' + text)
    return text


def _analyze(n):
    found, changed, notes = [], [], []
    s = n['scene_scale'].value() or 0.1
    f = nuke.frame()

    def setk(name, value, label, fmt='%g'):
        k = n[name]
        old = k.value()
        if isinstance(value, (int, float)) and isinstance(old, (int, float)):
            if abs(old - value) <= 1e-6 * max(1.0, abs(value)):
                return
            changed.append('%s: %s to %s' % (label, fmt % old, fmt % value))
        else:
            if old == value:
                return
            changed.append('%s: %s to %s' % (label, old, value))
        k.setValue(value)

    bg = n.input(0)
    cam = _find(n, 1, 'focal')
    atm = _find(n, 2, 'haze_density')
    axis = _find(n, 3, 'world_matrix')

    # The camera, as the kernel sees it.
    M = [n['cam_world_matrix'].getValueAt(f, i) for i in range(16)]
    focal = n['cam_focal'].getValueAt(f) or 24.0
    hap = n['cam_haperture'].getValueAt(f) or 36.0
    cam_y = M[7]
    if cam is None:
        found.append('camera: none plugged in, so the node looks level from 300 m up. Plug in the shot camera.')
    else:
        found.append('camera: %s (focal %g, haperture %g)' % (cam.name(), focal, hap))

    def to_world(p):
        return [M[0] * p[0] + M[1] * p[1] + M[2] * p[2] + M[3],
                M[4] * p[0] + M[5] * p[1] + M[6] * p[2] + M[7],
                M[8] * p[0] + M[9] * p[1] + M[10] * p[2] + M[11]]

    def to_cam(w):
        r = [w[0] - M[3], w[1] - M[7], w[2] - M[11]]
        return [M[0] * r[0] + M[4] * r[1] + M[8] * r[2],
                M[1] * r[0] + M[5] * r[1] + M[9] * r[2],
                M[2] * r[0] + M[6] * r[1] + M[10] * r[2]]

    # The bg's depth.
    W = H = 0
    ground = []      # (planar or distance raw value, distance in scene units, world point, px, py)
    sky_raw = []
    mode = int(n['depth_mode'].getValue())
    chan = None
    if bg is None:
        found.append('bg: none plugged in. The clouds render over black at the root format.')
    else:
        fmt = bg.format()
        W, H = fmt.width(), fmt.height()
        chan = _depth_channel(n, bg)
        if chan is None:
            found.append('bg: %s, %d x %d, no depth channel. Clouds can\'t go behind anything in the plate '
                         'and cast no shadows on it.' % (bg.name(), W, H))
        else:
            raw = []
            for j in range(GY):
                for i in range(GX):
                    px, py = (i + 0.5) * W / GX, (j + 0.5) * H / GY
                    try:
                        v = bg.sample(chan, px, py, frame=f)
                    except Exception:
                        v = 0.0
                    if not (v == v) or abs(v) == float('inf'):
                        v = 0.0
                    raw.append((v, px, py))
            pos = [v for v, _, _ in raw if v > 0]
            # 1/Z: ScanlineRender up the plate's main pipe, or depth that is all under 1 (in scene
            # units nothing in a shot is that close; 1/Z of anything past 1 unit is).
            if pos and (_scanline_on_b(bg) or _pct(pos, 0.95) < 1.0):
                new_mode = 1
            elif mode == 1 and pos and _pct(pos, 0.5) > 1.0:
                new_mode = 0
            else:
                new_mode = mode
            if new_mode != mode:
                setk('depth_mode', ['Planar Z', '1/Z (ScanlineRender)', 'Distance'][new_mode], 'depth is')
                mode = new_mode
            vap = hap * H / float(W)
            pts = []
            for v, px, py in raw:
                z = (1.0 / v if v > 0 else 0.0) if mode == 1 else v
                if z <= 0:
                    sky_raw.append(0.0)
                    continue
                cd = [(px / W - 0.5) * hap / focal, (py / H - 0.5) * vap / focal, -1.0]
                l = math.sqrt(cd[0] ** 2 + cd[1] ** 2 + 1.0)
                if mode == 2:
                    dist, p = z, [c / l * z for c in cd]
                else:
                    dist, p = z * l, [c * z for c in cd]
                pts.append((z, dist, to_world(p), px, py))
            # Sky: a tight cluster of far distances (a sky dome) well past the rest.
            pts.sort(key=lambda t: t[1])
            split = None
            m = len(pts)
            best = 0.0
            for k in range(1, m):
                lo, hi = pts[k - 1][1], pts[k][1]
                top = m - k
                if top < max(3, 0.03 * GX * GY) or k < 3 or lo <= 0:
                    continue
                gap = hi / lo
                tight = pts[-1][1] / hi <= 1.3
                if (gap >= 1.5 and tight) or gap >= 4.0:
                    if gap > best:
                        best, split = gap, k
            if split is not None:
                ground = pts[:split]
                sky_raw += [t[0] for t in pts[split:]]
                g_max = max(t[0] for t in ground)
                s_min = min(t[0] for t in pts[split:])
                # Just under the dome: terrain between the grid's samples can reach further than
                # the farthest one sampled.
                thr = (max(g_max * 1.2, 0.8 * s_min) if s_min > 1.25 * g_max else
                       math.sqrt(g_max * s_min) if s_min > g_max else 0.5 * (ground[-1][1] + pts[split][1]))
                setk('sky_depth', round(thr * s / 1000.0, 2), 'sky beyond (km)')
                found.append('sky in the depth: a far dome at about %.0f km (%d%% of the frame)'
                             % (pts[split][1] * s / 1000.0, 100 * (m - split) // (GX * GY)))
            else:
                ground = pts
                if ground:
                    g_max = max(t[0] for t in ground)
                    if n['sky_depth'].value() * 1000.0 / s <= g_max:
                        setk('sky_depth', round(min(500.0, g_max * 1.5 * s / 1000.0), 2), 'sky beyond (km)')
            n_sky = sum(1 for v in sky_raw if v == 0)
            found.append('bg: %s, %d x %d, depth in %s (%s); %d%% of the frame is ground or buildings%s'
                         % (bg.name(), W, H, chan, ['Planar Z', '1/Z', 'Distance'][mode],
                            100 * len(ground) // (GX * GY),
                            ', %d%% depth 0 (sky)' % (100 * n_sky // (GX * GY)) if n_sky else ''))
            if chan != {'depth': 'depth.Z'}.get(n['depth_channel'].value(), n['depth_channel'].value()):
                setk('depth_channel', chan, 'depth channel')
                try:
                    n.node('DepthEnsure')['channels'].setValue(chan)
                    n.node('DepthSource')['from0'].setValue(chan)
                except Exception:
                    pass
            if not n['occlude'].value():
                setk('occlude', True, 'hide behind bg')

    # The ground.
    terrain_km = None
    if len(ground) >= 8:
        ys = [t[2][1] for t in ground]
        gh = _pct(ys, 0.05)
        if gh < cam_y:
            setk('ground_height', round(gh, 3), 'ground height (scene units)')
        else:
            notes.append('Everything in the depth is at or above the camera, so the ground height was left '
                         'as it was.')
        d = [t[1] * s / 1000.0 for t in ground]
        terrain_km = (_pct(d, 0.1), _pct(d, 0.5), _pct(d, 0.9))
        found.append('ground: lowest visible ground at %g scene units; terrain %.2f / %.2f / %.2f km away '
                     '(near / middle / far)' % (round(gh, 3), terrain_km[0], terrain_km[1], terrain_km[2]))
        if terrain_km[2] > 0.8 * n['max_distance'].value():
            setk('max_distance', round(min(500.0, terrain_km[2] * 1.5), 1), 'max distance (km)')
    elif n['ground_height'].value() >= cam_y:
        setk('ground_height', 0.0, 'ground height (scene units)')
        notes.append('The camera was below the ground; ground height reset to 0.')
    cam_alt = (cam_y - n['ground_height'].value()) * s
    found.append('camera height: %.0f m above the ground' % cam_alt)

    # Units sanity.
    if terrain_km is not None and (terrain_km[1] < 0.02 or terrain_km[1] > 300):
        notes.append('The terrain comes out %.3g km away at its middle. If that is wrong, check '
                     '\'units to metres\' (now %g: 0.1 for decimetres, 1 for metres, 0.01 for centimetres) and '
                     'press analyze again.' % (terrain_km[1], s))
    if cam_alt > 30000 or cam_alt < -1:
        notes.append('A camera %.0f m above the ground looks wrong: check \'units to metres\' (now %g) '
                     'and the camera.' % (cam_alt, s))

    # Sun and light.
    src = int(n['sun_source'].getValueAt(f))
    if src == 1:
        found.append('sun: from the Axis %s' % (axis.name() if axis else ''))
    elif src == 2:
        found.append('sun: from the EzAtmosScatter %s' % (atm.name() if atm else ''))
    else:
        sd = n['sun_direction'].value()
        found.append('sun: the typed sun direction (%.2f, %.2f, %.2f)' % tuple(sd))
        if n['sun_from'].value() == 'Auto':
            notes.append('No sun Axis or EzAtmosScatter is plugged in. For the plate\'s own sun, plug the '
                         'scene\'s sun Axis into \'sun\' or its EzAtmosScatter into \'atmos\'.')
    if int(n['light_source'].getValueAt(f)):
        found.append('light: sun and sky colour measured by the EzAtmosScatter')
    else:
        found.append('light: the Light tab\'s sun and sky colours (Manual)')
        if atm is not None and n['light_from'].value() == 'Auto':
            notes.append('The EzAtmosScatter is plugged in but measured no light (self lit?), so the '
                         'Light tab\'s colours are used.')

    # The layers.
    vap = hap * (H / float(W) if W else 9 / 16.0)
    for i in (1, 2, 3):
        p = 'l%d_' % i
        if not n[p + 'enable'].value():
            continue
        t = n[p + 'type'].value()
        if n[p + 'volume'].value() < 0.5:
            base = n[p + 'base'].value()
            top = base + n[p + 'thickness'].value()
            where = ('inside it' if base <= cam_alt <= top else
                     'above it, looking down on it' if cam_alt > top else 'below it')
            found.append('layer %d: %s deck, %.0f to %.0f m above the ground; the camera is %s'
                         % (i, t, base, top, where))
            continue
        if n[p + 'box_found'].value() > 0.5:
            found.append('layer %d: %s volume, following the 3D box in box%d' % (i, t, i))
            continue
        pos = n[p + 'vol_position'].value()
        size = n[p + 'vol_size'].value()
        c = to_cam([pos[0], pos[1] + size[1] / s / 2.0, pos[2]])
        reason = None
        if c[2] > -1e-6:
            reason = 'behind the camera'
        else:
            u = c[0] / -c[2] * focal / hap
            v = c[1] / -c[2] * focal / vap
            if abs(u) > 0.65 or abs(v) > 0.65:
                reason = 'out of frame'
            elif ground and W:
                # Hidden behind the plate's terrain?
                px, py = (u + 0.5) * W, (v + 0.5) * H
                near = min(ground, key=lambda tt: (tt[3] - px) ** 2 + (tt[4] - py) ** 2)
                d_vol = math.sqrt(c[0] ** 2 + c[1] ** 2 + c[2] ** 2) - 0.5 * max(size) / s
                if (near[3] - px) ** 2 + (near[4] - py) ** 2 < (1.5 * W / GX) ** 2 and near[1] < d_vol:
                    reason = 'behind the plate\'s terrain'
        if reason is None:
            found.append('layer %d: %s volume, in view' % (i, t))
            continue
        if n[p + 'vol_position'].isAnimated():
            notes.append('Layer %d (%s) is %s, but its position is animated, so it was left alone.'
                         % (i, t, reason))
            continue
        km = n[p + 'place_km'].value()
        if terrain_km is not None:
            km = max(0.2, min(km, 0.7 * terrain_km[1]))
        n[p + 'place_km'].setValue(round(km, 2))
        # The layer's own 'place in front of camera' code, run on this node.
        exec(n[p + 'place'].value().replace('nuke.thisNode()', '_n'), {'nuke': nuke, '_n': n})
        changed.append('layer %d (%s) was %s: placed %.2f km in front of the camera' % (i, t, reason, km))

    if n['preview'].value():
        notes.append('preview is on: half resolution, one sample. Turn it off for the real look.')

    out = 'Found:\n' + '\n'.join('  ' + x for x in found)
    out += '\n\nChanged:\n' + ('\n'.join('  ' + x for x in changed) if changed else '  nothing, it already matched')
    if notes:
        out += '\n\nCheck:\n' + '\n'.join('  ' + x for x in notes)
    return out
