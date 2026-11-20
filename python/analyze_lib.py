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
    if n.knob('debug') is not None and n['debug'].value():
        debug_report(n)
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
            vap = hap * H / (float(W) * (bg.format().pixelAspect() or 1.0))
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

    # The ground: the low ground in the nearer half of the terrain (the valley the shot looks into).
    # Far terrain can lie well below it (a distant basin, the earth's curve in the render) and would
    # put every deck too low for the valley in view.
    terrain_km = None
    relief = None
    if len(ground) >= 8:
        d_mid = _pct([t[1] for t in ground], 0.5)
        near = [t for t in ground if t[1] <= d_mid]
        if len(near) < 8:
            near = ground
        ys = [t[2][1] for t in near]
        gh = _pct(ys, 0.05)
        low_all = _pct([t[2][1] for t in ground], 0.05)
        if gh < cam_y:
            setk('ground_height', round(gh, 3), 'ground height (scene units)')
        else:
            notes.append('Everything in the depth is at or above the camera, so the ground height was left '
                         'as it was.')
        d = [t[1] * s / 1000.0 for t in ground]
        terrain_km = (_pct(d, 0.1), _pct(d, 0.5), _pct(d, 0.9))
        relief = ((_pct(ys, 0.5) - gh) * s, (_pct(ys, 0.95) - gh) * s)
        found.append('ground: valley floor (lowest ground in the nearer half) at %g scene units; terrain %.2f / '
                     '%.2f / %.2f km away (near / middle / far)'
                     % (round(gh, 3), terrain_km[0], terrain_km[1], terrain_km[2]))
        found.append('terrain heights above that floor: middle %.0f m, ridges up to %.0f m' % relief)
        if (gh - low_all) * s > 50:
            found.append('far terrain goes %.0f m lower than that floor (not used for the ground height)'
                         % ((gh - low_all) * s))
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
    pa = (bg.format().pixelAspect() or 1.0) if bg is not None else 1.0
    vap = hap * (H / (float(W) * pa) if W else 9 / 16.0)
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
            if relief is not None and base < relief[1]:
                notes.append('Layer %d\'s base (%.0f m) is below the ridges in view (up to %.0f m above the floor): '
                             'the terrain rises through the deck and the clouds stop at it. That is right for '
                             'valley fog (set its base just above the valley floor, so the fog fills the low '
                             'ground); for a deck that should float over the terrain, raise its base above %.0f m.'
                             % (i, base, relief[1], relief[1]))
            if n[p + 'sigma'].value() * n[p + 'density'].value() >= 0.01 and cam_alt > top + 300:
                notes.append('Layer %d is seen from %.0f m above its top: at this density (sigma x density %.3g) '
                             'it reads as a solid, smooth sheet. For fog with breakup use the Valley Fog type '
                             '(0.0035), or lower density and coverage.'
                             % (i, cam_alt - top, n[p + 'sigma'].value() * n[p + 'density'].value()))
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


# ---------------------------------------------------------------------------------------------
# 'debug report' (About tab): a plain-text dump of what the node sees, printed to the Script
# Editor, for debugging a shot without sharing the plate. Numbers only: no picture leaves the node.

_P_NAMES = ('p', 'pworld', 'p_world', 'pw', 'wp', 'position', 'world_position', 'worldposition',
            'p_w', 'pos', 'worldpos', 'ppass', 'p_pass', 'position_world')


def _rgb_channels(bg, layer):
    chans = [c for c in bg.channels() if c.split('.')[0] == layer]
    order = {'red': 0, 'x': 0, 'r': 0, 'green': 1, 'y': 1, 'g': 1, 'blue': 2, 'z': 2, 'b': 2}
    chans = sorted(chans, key=lambda c: order.get(c.split('.')[-1].lower(), 9))
    return chans[:3] if len(chans) >= 3 else None


def _find_p_layer(bg):
    layers = []
    for c in bg.channels():
        l = c.split('.')[0]
        if l not in layers:
            layers.append(l)
    for l in layers:
        if l.lower() in _P_NAMES and _rgb_channels(bg, l):
            return l
    for l in layers:
        ll = l.lower()
        if ('position' in ll or ll.startswith('pworld') or ll.startswith('p_')) and _rgb_channels(bg, l):
            return l
    return None


def _fmt_list(vals, fmt='%.3g'):
    return ' / '.join(fmt % v for v in vals)


def debug_report(n):
    out = []
    w = out.append
    f = nuke.frame()
    s = n['scene_scale'].value() or 0.1

    def section(title):
        w('')
        w('-- %s ' % title + '-' * max(4, 70 - len(title)))

    def safe(fn):
        try:
            fn()
        except Exception as e:
            w('  (error in this section: %s: %s)' % (type(e).__name__, e))

    ver = n['version'].value() if n.knob('version') else '?'
    w('==== EzCloudGen debug report ' + '=' * 50)
    w('%s, node %s, frame %d, Nuke %s' % (ver, n.fullName(), f, nuke.NUKE_VERSION_STRING))
    rf = nuke.root().format()
    w('root format %d x %d (pixel aspect %g), fps %g' % (rf.width(), rf.height(), rf.pixelAspect(),
                                                          nuke.root()['fps'].value()))

    bg = n.input(0)
    cam = _find(n, 1, 'focal')
    atm = _find(n, 2, 'haze_density')
    axis = _find(n, 3, 'world_matrix')
    M = [n['cam_world_matrix'].getValueAt(f, i) for i in range(16)]
    focal = n['cam_focal'].getValueAt(f) or 24.0
    hap = n['cam_haperture'].getValueAt(f) or 36.0
    gh = n['ground_height'].value()
    W = H = 0
    pa = 1.0
    if bg is not None:
        W, H = bg.format().width(), bg.format().height()
        pa = bg.format().pixelAspect() or 1.0
    vap = hap * (H / (float(W) * pa) if W else 9 / 16.0)
    flags = []

    def to_world(p):
        return [M[0] * p[0] + M[1] * p[1] + M[2] * p[2] + M[3],
                M[4] * p[0] + M[5] * p[1] + M[6] * p[2] + M[7],
                M[8] * p[0] + M[9] * p[1] + M[10] * p[2] + M[11]]

    # ---- inputs
    def inputs():
        section('inputs')
        names = ['bg', 'camera', 'atmos', 'sun', 'map', 'box1', 'box2', 'box3', 'holdout', 'add']
        for i, nm in enumerate(names):
            x = n.input(i) if i < n.inputs() or n.input(i) is not None else None
            w('  %-8s %s' % (nm, '%s (%s)' % (x.name(), x.Class()) if x is not None else '-'))
        if bg is None:
            return
        fm = bg.format()
        w('  bg format %d x %d (pixel aspect %g); bbox %d %d %d %d'
          % (fm.width(), fm.height(), fm.pixelAspect(), bg.bbox().x(), bg.bbox().y(), bg.bbox().w(), bg.bbox().h()))
        bb = bg.bbox()
        if bb.x() < 0 or bb.y() < 0 or bb.x() + bb.w() > fm.width() or bb.y() + bb.h() > fm.height():
            flags.append('bg has overscan (bbox outside the format): the camera must match the FORMAT, '
                         'not the overscan area.')
            w('  ! bbox reaches outside the format (overscan)')
        chain, x, k = [], bg, 0
        while x is not None and k < 15:
            chain.append(x.Class())
            x = x.input(0) if x.inputs() else None
            k += 1
        w('  B pipe up from bg: ' + ' < '.join(chain))
        layers = []
        for c in bg.channels():
            l = c.split('.')[0]
            if l not in layers:
                layers.append(l)
        w('  bg layers: ' + ', '.join(layers))
    safe(inputs)

    # ---- camera
    def camera():
        section('camera')
        if cam is None:
            w('  none plugged in (the node uses a level camera 300 m up)')
            return
        w('  %s (%s)' % (cam.name(), cam.Class()))
        w('  world matrix rows: ' + ' | '.join(_fmt_list(M[4 * r:4 * r + 4], '%.6g') for r in range(4)))
        for kn in ('translate', 'rotate', 'rot_order', 'focal', 'haperture', 'vaperture', 'near', 'far',
                   'win_translate', 'win_scale', 'winroll', 'projection_mode', 'focal_point', 'fstop'):
            kk = cam.knob(kn)
            if kk is None:
                continue
            try:
                v = kk.getValueAt(f) if kk.arraySize() == 1 else [kk.getValueAt(f, i) for i in range(kk.arraySize())]
            except Exception:
                v = kk.value()
            anim = ' (animated)' if hasattr(kk, 'isAnimated') and kk.isAnimated() else ''
            w('  %-15s %s%s' % (kn, v, anim))
        cv = cam.knob('vaperture').getValueAt(f) if cam.knob('vaperture') else None
        if cv and W and abs(cv - vap) > 0.01 * vap:
            flags.append('camera vaperture %.4g differs from haperture x bg height / (width x pixel aspect) = %.4g: EzCloudGen derives '
                         'the vertical aperture from the format and its pixel aspect, so the clouds may be '
                         'stretched vertically against the plate.' % (cv, vap))
        if cam.knob('win_translate'):
            wt = [cam['win_translate'].getValueAt(f, i) for i in range(2)]
            if abs(wt[0]) > 1e-6 or abs(wt[1]) > 1e-6:
                flags.append('camera win_translate %s is not 0: EzCloudGen ignores it, so the clouds are offset '
                             'from the plate.' % wt)
        if cam.knob('win_scale'):
            ws = [cam['win_scale'].getValueAt(f, i) for i in range(2)]
            if abs(ws[0] - 1) > 1e-6 or abs(ws[1] - 1) > 1e-6:
                flags.append('camera win_scale %s is not 1: EzCloudGen ignores it.' % ws)
        if cam.knob('winroll') and abs(cam['winroll'].getValueAt(f)) > 1e-6:
            flags.append('camera winroll is not 0: EzCloudGen ignores it.')
        for kn in ('focal', 'haperture'):
            if cam.knob(kn) and cam[kn].isAnimated():
                flags.append('camera %s is animated (fine, it is read per frame; just so you know).' % kn)
        if cam.knob('projection_mode') and cam['projection_mode'].value() not in ('perspective', 0, '0'):
            flags.append('camera projection is %s: EzCloudGen assumes perspective.' % cam['projection_mode'].value())
        fwd = [-M[2], -M[6], -M[10]]
        l = math.sqrt(sum(c * c for c in fwd)) or 1.0
        fwd = [c / l for c in fwd]
        pitch = math.degrees(math.asin(max(-1.0, min(1.0, fwd[1]))))
        head = math.degrees(math.atan2(fwd[0], -fwd[2]))
        w('  as used: focal %g, haperture %g, vaperture (from format, pixel aspect %g) %.4g; position %s scene units; '
          'looking %.1f deg %s level, heading %.1f deg'
          % (focal, hap, pa, vap, _fmt_list(M[3:12:4], '%.6g'), abs(pitch), 'below' if pitch < 0 else 'above', head))
        w('  camera height above ground height: %.1f m' % ((M[7] - gh) * s))
        try:
            P = [n['cam_prev_matrix'].getValueAt(f, i) for i in range(16)]
            N = [n['cam_next_matrix'].getValueAt(f, i) for i in range(16)]
            mv = math.sqrt(sum((N[i] - P[i]) ** 2 for i in (3, 7, 11))) * s / 2.0
            w('  camera moves %.2f m per frame (from the frames either side)' % mv)
        except Exception:
            pass
    safe(camera)

    # ---- scene knobs
    def scene():
        section('scene knobs')
        for kn in ('scene_scale', 'ground_height', 'earth', 'occlude', 'depth_channel', 'depth_mode', 'sky_depth',
                   'bg_edge_softness', 'ground_softness', 'max_distance', 'render_preset', 'resolution', 'quality',
                   'edge_steps', 'sampling', 'samples', 'preview', 'motion_blur', 'haze_distance', 'horizon_haze',
                   'light_grid', 'view'):
            if n.knob(kn) is not None:
                w('  %-17s %s' % (kn, n[kn].value()))
        try:
            cc = n.node('Clouds_Color')
            spp = cc['EzCloudGen_samples'].value()
            w('  samples per pixel in use: %g' % spp)
        except Exception:
            pass
    safe(scene)

    # ---- depth, terrain, P
    grid = {}

    def depth():
        section('depth (bg, %dx%d grid)' % (GX, GY))
        if bg is None:
            w('  no bg')
            return
        chan = _depth_channel(n, bg)
        mode = int(n['depth_mode'].getValue())
        w('  channel %s, read as %s' % (chan, ['Planar Z', '1/Z', 'Distance'][mode]))
        if chan is None:
            return
        raw, bad = [], 0
        for j in range(GY):
            for i in range(GX):
                px, py = (i + 0.5) * W / GX, (j + 0.5) * H / GY
                try:
                    v = bg.sample(chan, px, py, frame=f)
                except Exception:
                    v = 0.0
                if not (v == v) or abs(v) == float('inf'):
                    bad += 1
                    v = 0.0
                raw.append(v)
        pos = [v for v in raw if v > 0]
        w('  raw: min %.6g, p5 %.6g, p50 %.6g, p95 %.6g, max %.6g; %d%% zero, %d%% NaN/inf, %d%% negative'
          % (min(pos) if pos else 0, _pct(pos, .05), _pct(pos, .5), _pct(pos, .95), max(pos) if pos else 0,
             100 * sum(1 for v in raw if v == 0) // len(raw), 100 * bad // len(raw),
             100 * sum(1 for v in raw if v < 0) // len(raw)))
        if _scanline_on_b(bg) and mode != 1:
            flags.append('A ScanlineRender/RayRender is up the bg pipe but depth is read as %s; its depth is 1/Z.'
                         % ['Planar Z', '1/Z', 'Distance'][mode])
        sky_su = n['sky_depth'].value() * 1000.0 / s
        pts = {}
        for idx, v in enumerate(raw):
            j, i = divmod(idx, GX)
            px, py = (i + 0.5) * W / GX, (j + 0.5) * H / GY
            z = (1.0 / v if v > 0 else 0.0) if mode == 1 else v
            if z <= 0 or z >= sky_su:
                continue
            cd = [(px / W - 0.5) * hap / focal, (py / H - 0.5) * vap / focal, -1.0]
            l = math.sqrt(cd[0] ** 2 + cd[1] ** 2 + 1.0)
            if mode == 2:
                dist, p = z, [c / l * z for c in cd]
            else:
                dist, p = z * l, [c * z for c in cd]
            pts[(i, j)] = (dist, to_world(p))
        grid['pts'] = pts
        w('  %d%% beyond \'sky beyond\' (%.4g km) or zero = sky' % (100 - 100 * len(pts) // len(raw),
                                                                   n['sky_depth'].value()))
        if not pts:
            return
        dk = [d * s / 1000.0 for d, _ in pts.values()]
        bins = [0.1, 0.3, 1, 3, 10, 30, 100, 300, 1e9]
        hist, lo = [], 0.0
        for b in bins:
            c = sum(1 for d in dk if lo <= d < b)
            hist.append('%s-%s km: %d' % (('%g' % lo), ('%g' % b) if b < 1e8 else 'inf', c))
            lo = b
        w('  distance histogram: ' + ', '.join(hist))
        # Edges: neighbours with a >2x depth jump.
        jumps = tot = 0
        for (i, j), (d, _) in pts.items():
            for di, dj in ((1, 0), (0, 1)):
                q = pts.get((i + di, j + dj))
                if q is None:
                    continue
                tot += 1
                if max(d, q[0]) / max(min(d, q[0]), 1e-9) > 2.0:
                    jumps += 1
        w('  depth edges: %d of %d grid neighbours (%.0f%%) jump more than 2x in depth' % (jumps, tot,
                                                                                          100.0 * jumps / max(tot, 1)))
        # Coarse maps, 16x9: distance (km) and height above 'ground height' (m). Top row = top of frame.
        def cmap(val, title, fmt):
            w('  %s (16x9, top of frame first; . = sky):' % title)
            for jj in range(8, -1, -1):
                row = []
                for ii in range(16):
                    vs = [val(pts[(2 * ii + a, 2 * jj + b)]) for a in (0, 1) for b in (0, 1)
                          if (2 * ii + a, 2 * jj + b) in pts]
                    row.append(fmt % (sorted(vs)[len(vs) // 2]) if vs else '      .')
                w('   ' + ''.join(row))
        cmap(lambda t: t[0] * s / 1000.0, 'distance km', '%7.2f')
        cmap(lambda t: (t[1][1] - gh) * s, 'height above ground height, m', '%7.0f')
        hs = [(t[1][1] - gh) * s for t in pts.values()]
        w('  heights above ground height (m): p5 %.0f, p25 %.0f, p50 %.0f, p75 %.0f, p95 %.0f'
          % (_pct(hs, .05), _pct(hs, .25), _pct(hs, .5), _pct(hs, .75), _pct(hs, .95)))
    safe(depth)

    def ppass():
        section('position pass')
        if bg is None:
            return
        picked = n['position_pass'].value() if n.knob('position_pass') is not None else 'none'
        if picked and picked not in ('none', 'all'):
            pl, how = picked, 'picked in \'position pass\''
            if _rgb_channels(bg, pl) is None:
                w('  layer %s (picked) is not on the bg, or has fewer than 3 channels' % pl)
                flags.append('\'position pass\' is set to %s, which the bg does not have.' % pl)
                return
        else:
            pl, how = _find_p_layer(bg), 'auto-detected'
            if pl is None:
                w('  none found on the bg (looked for P, Pworld, P_world, position, ...); pick it in '
                  '\'position pass\' (About tab) if it has another name')
                return
        ch = _rgb_channels(bg, pl)
        w('  layer %s (%s), %s' % (pl, ', '.join(ch), how))
        absmax = []
        pts = grid.get('pts', {})
        errs, rel, pys, near_ys, ratio = [], [], [], [], []
        dmid = _pct([d for d, _ in pts.values()], 0.5) if pts else 0
        camp = [M[3], M[7], M[11]]
        for j in range(GY):
            for i in range(GX):
                px, py = (i + 0.5) * W / GX, (j + 0.5) * H / GY
                try:
                    P = [bg.sample(c, px, py, frame=f) for c in ch]
                except Exception:
                    continue
                if not all(v == v and abs(v) != float('inf') for v in P) or (P[0] == 0 and P[1] == 0 and P[2] == 0):
                    continue
                pys.append(P[1])
                absmax.append(max(abs(v) for v in P))
                t = pts.get((i, j))
                if t is None:
                    continue
                d, wp = t
                e = math.sqrt(sum((P[k] - wp[k]) ** 2 for k in range(3)))
                errs.append(e * s)
                rel.append(100.0 * e / max(d, 1e-9))
                dp = math.sqrt(sum((P[k] - camp[k]) ** 2 for k in range(3)))
                ratio.append(dp / max(d, 1e-9))
                if d <= dmid:
                    near_ys.append(P[1])
        w('  %d grid points with P; %d also with depth' % (len(pys), len(errs)))
        if absmax and _pct(absmax, 0.95) <= 1.05:
            w('  ! its values stay within -1..1: this looks like a normal pass or a normalised / reference '
              'position (Pref), not world positions')
            flags.append('Position pass %s has values within -1..1: probably not a world-position pass.' % pl)
        if pys:
            w('  P.y: p5 %.6g, p50 %.6g, p95 %.6g (scene units)' % (_pct(pys, .05), _pct(pys, .5), _pct(pys, .95)))
        if near_ys:
            pg = _pct(near_ys, 0.05)
            w('  ground from P (5th pct of the nearer half): %.6g scene units; ground height knob %.6g (%+.1f m)'
              % (pg, gh, (gh - pg) * s))
        if errs:
            w('  P vs depth+camera world position: error median %.2f m, p90 %.2f m; %.2f%% / %.2f%% of distance'
              % (_pct(errs, .5), _pct(errs, .9), _pct(rel, .5), _pct(rel, .9)))
            r = _pct(ratio, 0.5)
            w('  |P - camera| / depth distance: median %.4g' % r)
            if _pct(rel, .5) > 20.0:
                w('  ! P and the depth+camera positions are far apart (median %.0f%% of distance): if this '
                  'layer is not world position in the camera\'s space (Pref, object space, camera space), '
                  'pick the world one in \'position pass\'' % _pct(rel, .5))
            if _pct(rel, .5) > 2.0:
                hint = []
                if abs(r - 1) > 0.05:
                    hint.append('distances differ by a factor %.3g: wrong \'depth is\' mode or units '
                                '(P and depth in different units?)' % r)
                else:
                    hint.append('distances agree but positions do not: the camera does not match the render '
                                '(film back / vaperture, win_translate, overscan, or a different camera)')
                flags.append('Position pass and depth disagree (median %.1f%% of distance): ' % _pct(rel, .5) +
                             '; '.join(hint))
            else:
                w('  -> depth, depth mode, camera and units agree with the position pass')
    safe(ppass)

    # ---- layers
    def layers():
        section('layers')
        cam_alt = (M[7] - gh) * s
        hs = [(t[1][1] - gh) * s for t in grid.get('pts', {}).values()]
        for i in (1, 2, 3):
            p = 'l%d_' % i
            if not n[p + 'enable'].value():
                w('  layer %d: off' % i)
                continue
            vol = n[p + 'volume'].value() > 0.5
            sd = n[p + 'sigma'].value() * n[p + 'density'].value()
            w('  layer %d: %s, %s; coverage %g, sigma x density %.4g, size %g km, detail %g m, erosion %g, '
              'edge %g, model %s, wind %g deg %g m/s'
              % (i, n[p + 'type'].value(), 'volume' if vol else 'deck', n[p + 'coverage'].value(), sd,
                 n[p + 'scale_km'].value(), n[p + 'detail_size'].value(), n[p + 'erosion'].value(),
                 n[p + 'edge'].value(), n[p + 'detail_model'].value(), n[p + 'wind_deg'].value(),
                 n[p + 'wind_speed'].value()))
            if not vol and n.knob(p + 'depth_ramp_on') is not None and n[p + 'depth_ramp_on'].value():
                kr = n.node('L%d_DepthRamp' % i)
                rv = [kr['range'].value(k) for k in range(4)] if kr is not None else [0, 0, 0, 0]
                w('    depth ramp (Planar Z): %s scene units = %s m; %s'
                  % (_fmt_list(rv, '%g'), _fmt_list([v * s for v in rv], '%g'),
                     'hides shadows too' if n.knob(p + 'depth_ramp_shadows') is not None
                     and n[p + 'depth_ramp_shadows'].value() else 'shadows kept'))
            if not vol:
                base = n[p + 'base'].value()
                top = base + n[p + 'thickness'].value()
                where = 'inside' if base <= cam_alt <= top else 'above' if cam_alt > top else 'below'
                w('    base %.0f m, top %.0f m above ground height (scene y %.6g to %.6g); camera %s it'
                  % (base, top, gh + base / s, gh + top / s, where))
                if hs:
                    below = sum(1 for h in hs if h < base)
                    inside = sum(1 for h in hs if base <= h <= top)
                    above = len(hs) - below - inside
                    w('    terrain in view: %d%% below the base, %d%% inside the layer (fog meets ground there), '
                      '%d%% above the top' % (100 * below // len(hs), 100 * inside // len(hs), 100 * above // len(hs)))
            else:
                if n[p + 'box_found'].value() > 0.5:
                    w('    follows the 3D box in box%d: centre %s, size %s'
                      % (i, _fmt_list([n[p + 'box_center'].value(k) for k in range(3)], '%.6g'),
                         _fmt_list([n[p + 'box_size'].value(k) for k in range(3)], '%.6g')))
                else:
                    w('    position %s (scene units), size %s m, shape %s'
                      % (_fmt_list(n[p + 'vol_position'].value(), '%.6g'), _fmt_list(n[p + 'vol_size'].value(), '%g'),
                         n[p + 'vol_shape'].value()))
    safe(layers)

    # ---- sun and light
    def light():
        section('sun and light')
        w('  sun from %s, light from %s; atmos %s, sun axis %s'
          % (n['sun_from'].value(), n['light_from'].value(), atm.name() if atm else '-', axis.name() if axis else '-'))
        src = int(n['sun_source'].getValueAt(f))
        sv = [n['sun_in_use'].getValueAt(f, i) for i in range(3)]
        l = math.sqrt(sum(c * c for c in sv)) or 1.0
        sv = [c / l for c in sv]
        elev = math.degrees(math.asin(max(-1.0, min(1.0, sv[1]))))
        fwd = [-M[2], -M[10]]
        az = math.degrees(math.atan2(sv[0] * fwd[1] - sv[2] * fwd[0], sv[0] * fwd[0] + sv[2] * fwd[1]))
        w('  source in use: %s; direction %s, %.1f deg up, %.1f deg %s of the camera heading'
          % (['typed', 'Axis', 'EzAtmosScatter'][src] if 0 <= src <= 2 else src, _fmt_list(sv, '%.3f'), elev,
             abs(az), 'right' if az < 0 else 'left'))
        w('  light source: %s; sun colour in use %s; sky colour in use %s'
          % ('EzAtmosScatter' if int(n['light_source'].getValueAt(f)) else 'Manual (Light tab)',
             _fmt_list([n['sun_color_in_use'].getValueAt(f, i) for i in range(3)], '%.3g'),
             _fmt_list([n['sky_color_in_use'].getValueAt(f, i) for i in range(3)], '%.3g')))
    safe(light)

    # ---- GPU
    def gpu():
        section('gpu')
        import platform
        w('  %s, %s; Nuke %s mode' % (platform.system(), platform.machine(),
                                     'GUI' if nuke.env.get('gui') else 'terminal'))
        names = []
        for nd in n.nodes():
            if nd.Class() == 'BlinkScript' and nd.knob('gpuName') is not None:
                names.append((nd.name(), nd['gpuName'].value(), nd['useGPUIfAvailable'].value(),
                              nd['disable'].value() if nd.knob('disable') else False))
        devices = sorted(set(g for _, g, _, _ in names))
        w('  BlinkScript GPU: %s' % (', '.join(devices) if devices else '?'))
        off = [nm for nm, _, use, _ in names if not use]
        if off:
            w("  'use GPU if available' is off on: " + ', '.join(off))
            flags.append("'use GPU if available' is off on %s inside the node: they render on the CPU." % ', '.join(off))
        if any('not available' in g.lower() for g in devices):
            flags.append('Nuke has no usable GPU here (BlinkScript says "Not available"), so EzCloudGen renders on the '
                         'CPU: much slower, and the first frame compiles for a long time. Check Preferences > '
                         'Performance > Hardware (GPU device), the NVIDIA driver, and, for terminal or farm renders, '
                         'that Nuke is started with --gpu.')
        try:
            pr = nuke.toNode('preferences')
            for kn in ('selectedGPUDeviceName', 'selectedGPUDeviceIndex', 'enableMultiGPU'):
                if pr.knob(kn) is not None:
                    w('  pref %s: %s' % (kn, pr[kn].value()))
        except Exception:
            pass
    safe(gpu)

    section('flags')
    if flags:
        for x in flags:
            w('  ! ' + x)
    else:
        w('  none')
    if n.knob('analysis') and n['analysis'].value():
        section('last analyze scene text')
        for line in n['analysis'].value().splitlines():
            w('  ' + line)
    w('==== end of EzCloudGen debug report ' + '=' * 43)
    text = '\n'.join(out)
    print(text)
    return text
