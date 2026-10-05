"""
Red-team variants of a stored capture.

Each builder takes a capture dict and the loaded test module `th` (for the
harness `th.H`, the baseline and the map codec) and returns a NEW capture:
the part changed the way SolidWorks would have measured it. They come from
the red-team pass on harness 3.0.0 (see CHANGES.md, "Red team") and are used
by the RedTeam tests in test_harness.py. Nothing here touches SolidWorks.
"""
from __future__ import annotations

import copy
import math

import numpy as np


def _intervals(hits):
    """(enter, exit) x pairs of one +X ray (swRayPtsResults: 16 enter,
    32 exit)."""
    iv, start = [], None
    for x, t in sorted(hits):
        if t & 16 and not t & 32:
            start = x
        elif t & 32 and not t & 16 and start is not None:
            iv.append((start, x))
            start = None
    return iv


def _rays_from(intervals):
    return sorted([[round(a, 7), 17] for a, _ in intervals]
                  + [[round(b, 7), 33] for _, b in intervals])


def _cut_rays(xsec, keep_ray, x0, x1):
    """Remove material between x0 and x1 from the rays keep_ray(key) picks."""
    for key, hits in xsec["rays"].items():
        if not keep_ray(key):
            continue
        out = [(lo, hi) for a, b in _intervals(hits)
               for lo, hi in ((a, min(b, x0)), (max(a, x1), b)) if hi > lo]
        xsec["rays"][key] = _rays_from(out)


def _grid(hm, view="top"):
    step = hm["step_m"]
    shp = hm["shape_xz"] if view in ("top", "bottom") else hm["shape_xy"]
    kax = 2 if view in ("top", "bottom") else 1
    xs = hm["origin_m"][0] + (np.arange(shp[0]) + 0.5) * step
    ks = hm["origin_m"][kax] + (np.arange(shp[1]) + 0.5) * step
    return xs, ks


# -- wrong solutions ---------------------------------------------------------

def clusters_copied(cap, th):
    """Clusters COPIED, not moved: the reference plus the seed's original
    d-pad arms and face buttons left on their own sides (carried out by h
    with their grips), as a Mirror-body that keeps its sources leaves them.
    They overlap the swapped clusters; the interference census (which covers
    duplicate clusters at capture time) records 400 mm3 per pair."""
    c = copy.deepcopy(cap)
    bl = th.BASELINE
    g = th.grader(c)
    p_seed = bl["seed"]["plane_x_m"]
    seed_by = {b["id"]: b for b in bl["bodies"]}
    new = []
    for role in ("dpad", "face_buttons"):
        for sid in bl["seed"]["roles"][role]:
            b = copy.deepcopy(seed_by[sid])
            u = b["centroid_m"][0] - p_seed
            dx = (g.P + u + math.copysign(g.h, u)) - b["centroid_m"][0]
            nid = f"x{len(new):02d}"
            b["id"], b["name"] = nid, f"leftover-{role}"
            b["centroid_m"][0] += dx
            for key in ("extent_m", "bbox_m"):
                b[key][0] += dx
                b[key][3] += dx
            c["bodies"].append(b)
            c["glyph_faces"][nid] = [[r[0], r[1] + dx] + list(r[2:])
                                     for r in bl["glyph_faces"].get(sid, [])]
            c["body_skew_x"][nid] = bl["body_skew_x"].get(sid)
            new.append(nid)
    by = {b["id"]: b for b in c["bodies"]}

    def overlap(a, b):
        ea, eb = by[a]["extent_m"], by[b]["extent_m"]
        return all(min(ea[i + 3], eb[i + 3]) > max(ea[i], eb[i])
                   for i in range(3))
    pairs = c["interference"]["pairs"]
    controls = [i for r in ("dpad", "face_buttons") for i in g.roles[r]]
    for nid in new:
        for j in controls + list(c["housing_ids"]):
            if overlap(nid, j):
                pairs.append({"a": nid, "b": j, "volume_m3": 400e-9,
                              "error_code": 0})
    c["interference"]["total_volume_m3"] = sum(p["volume_m3"] for p in pairs)
    return c


def pocket(cap, th, u_mm, z_mm, wx_mm=15.0, wz_mm=15.0, depth_mm=1.0):
    """An unrequested pocket cut into the top of the housing at (u, z): the
    top map drops by depth, rays through the removed material lose it, its
    two short walls join the engraving-scale faces."""
    c = copy.deepcopy(cap)
    g = th.grader(c)
    hm = c["housing_maps"]
    top = th.dec(hm["top"], hm["shape_xz"])
    xs, zs = _grid(hm)
    x0, x1 = g.P + (u_mm - wx_mm / 2) / 1e3, g.P + (u_mm + wx_mm / 2) / 1e3
    z0, z1 = (z_mm - wz_mm / 2) / 1e3, (z_mm + wz_mm / 2) / 1e3
    cell = np.outer((xs >= x0) & (xs <= x1), (zs >= z0) & (zs <= z1))
    cell &= np.isfinite(top)
    old = top.copy()
    top[cell] -= depth_mm / 1e3
    hm["top"] = th.enc(top)
    xsec = c["xsection"]

    def through(key):
        iy, iz = (int(v) for v in key.split(","))
        y = xsec["y0_m"] + (iy + 0.5) * xsec["step_m"]
        z = xsec["z0_m"] + (iz + 0.5) * xsec["step_m"]
        if not z0 <= z <= z1:
            return False
        col = old[(xs >= x0) & (xs <= x1), int(np.argmin(np.abs(zs - z)))]
        return bool(np.isfinite(col).any()) and (
            np.nanmin(col) - depth_mm / 1e3 < y <= np.nanmax(col))
    _cut_rays(xsec, through, x0, x1)
    hid = c["housing_ids"][0]
    ymid = float(np.nanmean(old[cell])) - depth_mm / 2e3
    for x, nx in ((x0, 1.0), (x1, -1.0)):
        c["glyph_faces"][hid].append([wz_mm * depth_mm * 1e-6, x, ymid,
                                      (z0 + z1) / 2, nx, 0.0, 0.0])
    return c


def through_hole(cap, th, u_mm=30.0, z_mm=-28.0, d_mm=12.0):
    """A hole drilled vertically through the whole housing: top and bottom
    maps empty in the disc, rays crossing it lose the material."""
    c = copy.deepcopy(cap)
    g = th.grader(c)
    hm = c["housing_maps"]
    xc, zc, r = g.P + u_mm / 1e3, z_mm / 1e3, d_mm / 2e3
    for view in ("top", "bottom"):
        m = th.dec(hm[view], hm["shape_xz"])
        xs, zs = _grid(hm, view)
        X, Z = np.meshgrid(xs, zs, indexing="ij")
        m[np.hypot(X - xc, Z - zc) <= r] = np.nan
        hm[view] = th.enc(m)
    xsec = c["xsection"]
    for key, hits in xsec["rays"].items():
        z = xsec["z0_m"] + (int(key.split(",")[1]) + 0.5) * xsec["step_m"]
        if abs(z - zc) >= r:
            continue
        half = math.sqrt(r * r - (z - zc) ** 2)
        x0, x1 = xc - half, xc + half
        out = [(lo, hi) for a, b in _intervals(hits)
               for lo, hi in ((a, min(b, x0)), (max(a, x1), b)) if hi > lo]
        xsec["rays"][key] = _rays_from(out)
    return c


def leftover_stick(cap, th, first=True):
    """Sticks moved with Move/Copy 'Copy' ticked: a copy of the left stick
    stays at the seed stance, cutting the housing (300 mm3). first: the
    copy comes first in the body list (GetBodies2 order is arbitrary)."""
    c = copy.deepcopy(cap)
    g = th.grader(c)
    left = min(g.roles["sticks"], key=g.u)
    b = copy.deepcopy({x["id"]: x for x in cap["bodies"]}[left])
    b["id"], b["name"] = "x98", "Body-Move/Copy-leftover"
    shift = -math.copysign(g.h, g.u(left))
    b["centroid_m"][0] += shift
    for key in ("extent_m", "bbox_m"):
        b[key][0] += shift
        b[key][3] += shift
    if first:
        c["bodies"].insert(0, b)
    else:
        c["bodies"].append(b)
    c["glyph_faces"]["x98"] = []
    c["body_skew_x"]["x98"] = c["body_skew_x"].get(left)
    c["interference"]["pairs"].append({"a": "x98", "b": c["housing_ids"][0],
                                       "volume_m3": 300e-9, "error_code": 0})
    return c


def clusters_offset(cap, th, dy_mm=0.0, dz_mm=0.0):
    """Both swapped clusters at the right x but moved in y (floating above
    their seats) or z."""
    c = copy.deepcopy(cap)
    g = th.grader(c)
    ids = set(g.roles["dpad"]) | set(g.roles["face_buttons"])
    return th.move_bodies(c, ids, (0.0, dy_mm / 1e3, dz_mm / 1e3))


def block_on_top(cap, th):
    """A stray 40 x 12 x 20 mm block standing on the housing top at the
    plane (a left-over tool body)."""
    c = copy.deepcopy(cap)
    g = th.grader(c)
    a, b, d = 0.040, 0.012, 0.020
    ctr = (g.P, g.hext[4] + b / 2, -0.030)
    v = a * b * d
    e = [ctr[0] - a / 2, ctr[1] - b / 2, ctr[2] - d / 2,
         ctr[0] + a / 2, ctr[1] + b / 2, ctr[2] + d / 2]
    c["bodies"].append({
        "id": "x99", "name": "stray", "centroid_m": list(ctr),
        "volume_m3": v, "area_m2": 2 * (a * b + b * d + d * a),
        "inertia_com": {"Ixx": v * (b * b + d * d) / 12,
                        "Iyy": v * (a * a + d * d) / 12,
                        "Izz": v * (a * a + b * b) / 12,
                        "Ixy": 0.0, "Izx": 0.0, "Iyz": 0.0},
        "extent_m": e, "bbox_m": list(e)})
    c["glyph_faces"]["x99"] = []
    c["body_skew_x"]["x99"] = 0.0
    return c


def symbol_upside_down(cap, th, which="symbol top"):
    """One face-button symbol turned 180 deg about its button's axis (the
    triangle pointing down)."""
    c = copy.deepcopy(cap)
    g = th.grader(c)
    fb = g.roles["face_buttons"]
    cx = np.mean([g.C[i]["centroid_m"][0] for i in fb])
    cz = np.mean([g.C[i]["centroid_m"][2] for i in fb])

    def name(i):
        du = g.C[i]["centroid_m"][0] - cx
        dz = g.C[i]["centroid_m"][2] - cz
        return th.H.Grader.symbol_name({"du_m": du, "dz_m": dz})
    bid = next(i for i in fb if name(i) == which)
    rows = np.asarray(c["glyph_faces"][bid], float)
    a = rows[:, 0]
    sx = float((rows[:, 1] * a).sum() / a.sum())
    sz = float((rows[:, 3] * a).sum() / a.sum())
    c["glyph_faces"][bid] = [[r[0], 2 * sx - r[1], r[2], 2 * sz - r[3],
                              -r[4], r[5], -r[6]] for r in rows.tolist()]
    return c


def circle_deleted(cap, th):
    """The circle symbol removed from its button: the ring's floor -- an
    upward planar face below the button's top, its only face the capture
    records -- is gone (the button's top closes over it)."""
    c = copy.deepcopy(cap)
    g = th.grader(c)
    fb = g.roles["face_buttons"]
    cx = np.mean([g.C[i]["centroid_m"][0] for i in fb])
    cz = np.mean([g.C[i]["centroid_m"][2] for i in fb])
    sl = th.H.seed_labels(th.BASELINE)
    circle = next(S for S in sl["symbols"].values() if not len(S["faces"]))
    bid = min(fb, key=lambda i: math.hypot(
        g.C[i]["centroid_m"][0] - cx - circle["du_m"],
        g.C[i]["centroid_m"][2] - cz - circle["dz_m"]))
    c["planar_faces"][bid] = [r for r in c["planar_faces"][bid]
                              if r[5] < 1.0 - th.H.COPLANAR_N]
    return c


# -- valid solutions ---------------------------------------------------------

def three_piece_housing(cap, th, cut_mm=47.5):
    """Housing left as THREE side-by-side bodies, left grip | centre | right
    grip, cut at |u| = cut_mm (e.g. the seed cut at |u| = 40 mm, the grips
    moved out, the centre lengthened, bodies not combined). Each of the
    reference's two shells is split, so six pieces. Recorded the way THIS
    harness's capture() records it: only bodies that th.H.housing_ids()
    calls housing are ray-cast and rasterised. Piece mass properties are
    apportioned by plan area (no piece matches a control role)."""
    c = copy.deepcopy(cap)
    g = th.grader(c)
    p, cut = g.P, cut_mm / 1e3
    hm = c["housing_maps"]
    step = hm["step_m"]
    maps = {v: th.dec(hm[v], hm["shape_xz" if v in ("top", "bottom")
                                 else "shape_xy"])
            for v in ("top", "bottom", "front", "back")}
    top, bot = maps["top"], maps["bottom"]
    xs, zs = _grid(hm)
    hb = {b["id"]: b for b in c["bodies"] if b["id"] in c["housing_ids"]}
    xh0 = min(b["extent_m"][0] for b in hb.values())
    xh1 = max(b["extent_m"][3] for b in hb.values())
    ranges = {"L": (xh0, p - cut), "C": (p - cut, p + cut),
              "R": (p + cut, xh1)}
    foot = np.isfinite(top)
    new, glyphs, piece = [], {}, {}
    for hid, b in hb.items():
        for tag, (a, z) in ranges.items():
            sel = (xs >= a) & (xs < z)
            share = (foot & sel[:, None]).sum() / foot.sum()
            ks = np.nonzero((foot & sel[:, None]).any(0))[0]
            e = [a, max(b["extent_m"][1], np.nanmin(bot[sel])),
                 max(b["extent_m"][2], zs[ks[0]] - step / 2), z,
                 min(b["extent_m"][4], np.nanmax(top[sel])),
                 min(b["extent_m"][5], zs[ks[-1]] + step / 2)]
            v = b["volume_m3"] * share
            dx, dy, dz = e[3] - e[0], e[4] - e[1], e[5] - e[2]
            nid = f"{hid}{tag}"
            new.append({"id": nid, "name": f"{b['name']}-{tag}",
                        "centroid_m": [(a + z) / 2, b["centroid_m"][1],
                                       float(np.mean(zs[ks]))],
                        "volume_m3": v, "area_m2": b["area_m2"] * share,
                        "inertia_com": {"Ixx": v * (dy * dy + dz * dz) / 12,
                                        "Iyy": v * (dx * dx + dz * dz) / 12,
                                        "Izz": v * (dx * dx + dy * dy) / 12,
                                        "Ixy": 0.0, "Izx": 0.0, "Iyz": 0.0},
                        "extent_m": e, "bbox_m": list(e)})
            glyphs[nid] = [r for r in c["glyph_faces"].get(hid, [])
                           if a <= r[1] < z]
            piece.setdefault(tag, []).append(nid)
    for k, pick in ((1, min), (2, min), (4, max), (5, max)):
        owner = pick(hb.values(), key=lambda b: b["extent_m"][k])
        mine = [nb for nb in new if nb["id"].startswith(owner["id"])]
        best = pick(mine, key=lambda nb: nb["extent_m"][k])
        best["extent_m"][k] = best["bbox_m"][k] = owner["extent_m"][k]
    c["bodies"] = [b for b in c["bodies"] if b["id"] not in hb] + new
    for hid in hb:
        c["glyph_faces"].pop(hid)
    c["glyph_faces"].update(glyphs)
    hids = th.H.housing_ids(c["bodies"])
    c["housing_ids"] = hids
    for nb in new:
        if nb["id"] not in hids:
            c["body_skew_x"][nb["id"]] = 0.0
    if not hids:
        c["xsection"] = c["housing_maps"] = c["housing_extent_m"] = None
        return c
    hext = th.H.union_extent(c["bodies"], hids)
    c["housing_extent_m"] = hext
    keep = np.zeros(len(xs), bool)
    spans = []
    for tag, (a, z) in ranges.items():
        if any(i in hids for i in piece[tag]):
            keep |= (xs >= a) & (xs < z)
            spans.append((a, z))
    o = hm["origin_m"]
    i0 = int(np.floor((hext[0] - o[0]) / step + 1e-9))
    nx = int(np.ceil((hext[3] - hext[0]) / step - 1e-9))
    k0 = int(np.floor((hext[2] - o[2]) / step + 1e-9))
    nz = int(np.ceil((hext[5] - hext[2]) / step - 1e-9))
    j0 = int(np.floor((hext[1] - o[1]) / step + 1e-9))
    ny = int(np.ceil((hext[4] - hext[1]) / step - 1e-9))
    for v, m in maps.items():
        m = np.where(keep[:, None], m, np.nan)
        m = m[i0:i0 + nx, k0:k0 + nz] if v in ("top", "bottom") \
            else m[i0:i0 + nx, j0:j0 + ny]
        hm[v] = th.enc(m)
        hm["shape_xz" if v in ("top", "bottom") else "shape_xy"] = \
            list(m.shape)
    hm["origin_m"] = [o[0] + i0 * step, o[1] + j0 * step, o[2] + k0 * step]
    xsec = c["xsection"]
    for key, hits in xsec["rays"].items():
        out = []
        for a, b in _intervals(hits):
            for lo, hi in spans:
                s, e = max(a, lo), min(b, hi)
                if e > s:
                    out.append((s, e))
        xsec["rays"][key] = _rays_from(out)
    xsec["y0_m"], xsec["z0_m"] = hext[1], hext[2]
    return c


def one_piece_dpad(cap, th):
    """The swapped d-pad moulded as ONE cross-shaped body (four arms plus
    the hub joining them) instead of four arm bodies. Mass properties: the
    arms (parallel-axis theorem) plus a hub filling the gap between their
    inner ends; area: arms minus their inner end faces plus the hub's top
    and bottom; extent: the arms' union."""
    c = copy.deepcopy(cap)
    g = th.grader(c)
    arms = [b for b in c["bodies"] if b["id"] in g.roles["dpad"]]
    cen = np.mean([b["centroid_m"] for b in arms], 0)
    e = [min(b["extent_m"][k] for b in arms) for k in range(3)] + \
        [max(b["extent_m"][k] for b in arms) for k in range(3, 6)]
    side = [b for b in arms if abs(b["centroid_m"][0] - cen[0]) > 1e-3]
    gap = min(min(abs(b["extent_m"][0] - cen[0]),
                  abs(b["extent_m"][3] - cen[0])) for b in side)
    width = min(b["extent_m"][5] - b["extent_m"][2] for b in side)
    length = max(b["extent_m"][3] - b["extent_m"][0] for b in side)
    hh = arms[0]["volume_m3"] / (width * length)
    a = 2 * gap
    vh = a * a * hh
    v = sum(b["volume_m3"] for b in arms) + vh
    area = sum(b["area_m2"] for b in arms) - 4 * width * hh + 2 * a * a

    def tensor(i):
        return np.array([[i["Ixx"], -i["Ixy"], -i["Izx"]],
                         [-i["Ixy"], i["Iyy"], -i["Iyz"]],
                         [-i["Izx"], -i["Iyz"], i["Izz"]]])
    parts = [(b["volume_m3"], np.asarray(b["centroid_m"]),
              tensor(b["inertia_com"])) for b in arms]
    parts.append((vh, cen.copy(), tensor({
        "Ixx": vh * (hh * hh + a * a) / 12, "Iyy": vh * 2 * a * a / 12,
        "Izz": vh * (hh * hh + a * a) / 12, "Ixy": 0, "Izx": 0, "Iyz": 0})))
    com = sum(m * q for m, q, _ in parts) / v
    jt = sum(ji + m * (np.dot(q - com, q - com) * np.eye(3)
                       - np.outer(q - com, q - com)) for m, q, ji in parts)
    ids = {b["id"] for b in arms}
    c["glyph_faces"]["x50"] = [r for i in ids for r in c["glyph_faces"].pop(i)]
    for i in ids:
        c["body_skew_x"].pop(i, None)
    c["body_skew_x"]["x50"] = 0.0
    c["bodies"] = [b for b in c["bodies"] if b["id"] not in ids] + [{
        "id": "x50", "name": "Dpad-cross", "centroid_m": com.tolist(),
        "volume_m3": v, "area_m2": area,
        "inertia_com": {"Ixx": jt[0, 0], "Iyy": jt[1, 1], "Izz": jt[2, 2],
                        "Ixy": -jt[0, 1], "Izx": -jt[0, 2], "Iyz": -jt[1, 2]},
        "extent_m": e, "bbox_m": list(e)}]
    c["interference"]["pairs"] = [p for p in c["interference"]["pairs"]
                                  if p["a"] not in ids and p["b"] not in ids]
    return c


def labels_resplit(cap, th, frac=0.5, names=("START", "SELECT")):
    """The same engraving re-cut so every face of the named labels is split
    into two coplanar pieces (shares frac / 1-frac): total area and the
    area-weighted centroid are preserved, as any split preserves them."""
    c = copy.deepcopy(cap)
    for name in names:
        faces, _ = th.label_faces(c, name)
        by_h = {}
        for hid, j in faces:
            by_h.setdefault(hid, set()).add(j)
        for hid, js in by_h.items():
            rows = c["glyph_faces"][hid]
            keep = [r for k, r in enumerate(rows) if k not in js]
            for j in sorted(js):
                r = rows[j]
                a, p, n = r[0], np.asarray(r[1:4]), np.asarray(r[4:7])
                t = np.cross(n, [0.0, 1.0, 0.0])
                if np.linalg.norm(t) < 1e-9:
                    t = np.array([1.0, 0.0, 0.0])
                t = t / np.linalg.norm(t)
                size = np.sqrt(a)
                keep.append([a * frac, *(p - (1 - frac) * size / 2 * t),
                             *r[4:7]])
                keep.append([a * (1 - frac), *(p + frac * size / 2 * t),
                             *r[4:7]])
            c["glyph_faces"][hid] = keep
    return c


def lowest_point_pip(cap, th, delta_mm=0.1):
    """A 0.1 mm pip under the housing at its lowest point (a re-made fillet
    or a moulding pip): the lowest extreme point and the bottom map's lowest
    cell drop by delta. Nothing on the top surface changes."""
    c = copy.deepcopy(cap)
    low = min((b for b in c["bodies"] if b["id"] in c["housing_ids"]),
              key=lambda b: b["extent_m"][1])
    for key in ("extent_m", "bbox_m"):
        low[key][1] -= delta_mm / 1e3
    hm = c["housing_maps"]
    bot = th.dec(hm["bottom"], hm["shape_xz"])
    i, k = np.unravel_index(np.nanargmin(bot), bot.shape)
    bot[i, k] -= delta_mm / 1e3
    hm["bottom"] = th.enc(bot)
    return c


# -- documented limitations (not fixed) --------------------------------------

def seats_not_converted(cap, th, overlap_mm3=0.0):
    """Buttons swapped but the housing seats NOT converted: the two cluster
    regions (40 mm about each cluster centre) of the top/bottom maps and the
    ray hits there exchanged by mirroring."""
    c = copy.deepcopy(cap)
    g = th.grader(c)
    p, rad = g.P, 0.040
    cen = [(np.mean([g.C[i]["centroid_m"][0] for i in g.roles[r]]),
            np.mean([g.C[i]["centroid_m"][2] for i in g.roles[r]]))
           for r in ("dpad", "face_buttons")]
    hm = c["housing_maps"]
    step = hm["step_m"]
    for view in ("top", "bottom"):
        m = th.dec(hm[view], hm["shape_xz"])
        xs, zs = _grid(hm, view)
        X, Z = np.meshgrid(xs, zs, indexing="ij")
        reg = np.zeros_like(m, bool)
        for cx, cz in cen:
            reg |= np.hypot(X - cx, Z - cz) <= rad
        fi = ((2 * p - xs) - hm["origin_m"][0]) / step - 0.5
        i0 = np.clip(np.floor(fi).astype(int), 0, len(xs) - 2)
        t = np.clip(fi - i0, 0, 1)[:, None]
        hm[view] = th.enc(np.where(reg, m[i0] * (1 - t) + m[i0 + 1] * t, m))
    xr = [(cx - rad, cx + rad) for cx, _ in cen]
    xsec = c["xsection"]
    for key, hits in xsec["rays"].items():
        z = xsec["z0_m"] + (int(key.split(",")[1]) + 0.5) * xsec["step_m"]
        if not any(abs(z - cz) <= rad for _, cz in cen):
            continue
        inr = [hh for hh in hits if any(a <= hh[0] <= b for a, b in xr)]
        keep = [hh for hh in hits if hh not in inr]
        moved = [[round(2 * p - x, 7),
                  (t & ~48) | (16 if t & 32 else 0) | (32 if t & 16 else 0)]
                 for x, t in inr]
        xsec["rays"][key] = sorted(keep + moved)
    for r in ("dpad", "face_buttons"):
        for i in g.roles[r] if overlap_mm3 else []:
            c["interference"]["pairs"].append(
                {"a": i, "b": c["housing_ids"][0],
                 "volume_m3": overlap_mm3 * 1e-9, "error_code": 0})
    return c


def pocket_underneath(cap, th, u_mm=-60.0, z_mm=0.0, wx_mm=30.0, wz_mm=20.0,
                      depth_mm=2.0):
    """A 30 x 20 mm pocket, 2 mm deep, in the underside of the housing (the
    bottom map rises; no lattice ray passes that low there)."""
    c = copy.deepcopy(cap)
    g = th.grader(c)
    hm = c["housing_maps"]
    bot = th.dec(hm["bottom"], hm["shape_xz"])
    xs, zs = _grid(hm, "bottom")
    x0, x1 = g.P + (u_mm - wx_mm / 2) / 1e3, g.P + (u_mm + wx_mm / 2) / 1e3
    z0, z1 = (z_mm - wz_mm / 2) / 1e3, (z_mm + wz_mm / 2) / 1e3
    cell = np.outer((xs >= x0) & (xs <= x1), (zs >= z0) & (zs <= z1))
    cell &= np.isfinite(bot)
    bot[cell] += depth_mm / 1e3
    hm["bottom"] = th.enc(bot)
    return c


def symbols_mirrored_in_place(cap, th):
    """Every face-button symbol x-mirrored about its own centre, the
    arrangement kept (the cluster mirrored with Mirror Body, then the square
    and circle buttons swapped back). The symbols are symmetric shapes, so
    the part looks the same; only the square's face split is reversed."""
    c = copy.deepcopy(cap)
    g = th.grader(c)
    for bid in g.roles["face_buttons"]:
        rows = np.asarray(c["glyph_faces"][bid], float)
        if not len(rows):
            continue
        a = rows[:, 0]
        sx = float((rows[:, 1] * a).sum() / a.sum())
        c["glyph_faces"][bid] = [[r[0], 2 * sx - r[1], r[2], r[3], -r[4],
                                  r[5], r[6]] for r in rows.tolist()]
    return c


def text_rescaled(cap, th, scale=1.05, names=("START", "SELECT")):
    """START / SELECT re-typed at their mirrored positions in the same font,
    5 % larger (plan positions about the label centroid scaled, areas by
    scale squared)."""
    c = copy.deepcopy(cap)
    for name in names:
        faces, _ = th.label_faces(c, name)
        rows = np.array([c["glyph_faces"][hh][j] for hh, j in faces], float)
        cen = (rows[:, 1:4] * rows[:, :1]).sum(0) / rows[:, 0].sum()
        for hh, j in faces:
            r = c["glyph_faces"][hh][j]
            r[0] *= scale ** 2
            r[1] = cen[0] + scale * (r[1] - cen[0])
            r[3] = cen[2] + scale * (r[3] - cen[2])
    return c


