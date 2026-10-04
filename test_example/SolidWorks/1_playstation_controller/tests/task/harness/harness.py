#!/usr/bin/env python3
"""
Task 1 (SolidWorks) -- PS3 controller: widen 15 mm + left-handed layout.

Grades a candidate .SLDPRT against tests/task/prompt/input.json, the frozen
measurements of the seed part. GEOMETRY ONLY: mass properties, exact extreme
points, ray sections and face areas -- never feature or body names, and never
body order (IPartDoc::GetBodies2 "may vary the order in which bodies are
returned"). A candidate who solves the task a different valid way scores the
same as the reference.

RUBRIC -- weights live in ALL_CRITERIA, each next to the clause it comes from
  1  widened 15 mm at the grips        2.0   grip-lobe separation growth and
                                             body X extent; x not-scaled check
  2  clusters re-spaced to the stance  2.0   cluster x vs mirror + h; x rigidity,
                                             followers (sticks/triggers/bumpers)
                                             and fit (no new interference)
  3  d-pad and face buttons swapped    2.0   side of each cluster (continuous)
  4  START/SELECT mirrored             1.0   START/SELECT at mirrored positions
  5  text and logos oriented           1.0   INTERIM (stage B): v2's "R" label
                                             side witness; stage D registers
                                             every label
  6  text and logos preserved          1.0   INTERIM (stage B): v2's face-button
                                             engraving count
  7  no unrequested changes            0.5   shape/position of the bodies the
                                             edit leaves alone, housing Y/Z
                                             spans; housing surface: stage E
  8  rebuilds cleanly                  0.5   INTERIM (stage B): v2's newly
                                             broken fraction

FRAME
  u = x - P, with P the candidate's OWN mirror plane: the median midline of
  its two hand-grip lobes, read from +X rays through the housing at the (y, z)
  positions where the seed's section is two separate grips. A part translated
  along X is therefore graded on its geometry, not its origin.
  h = half the candidate's OWN grip-separation growth. Re-spacing is judged
  against the stance the candidate built, so a wrongly sized widening is
  charged once, by criterion 1.

IDENTITY (no names, no order)
  housing           every body spanning >= HOUSING_SPAN_FRAC of the part's X
                    extent (the reference splits it into two shells)
  kept bodies       sticks, triggers, bumpers and the two small bodies on the
                    plane: optimal assignment to the seed's bodies by shape
                    fingerprint -- the edit has no reason to reshape them
  button clusters   four congruent bodies forming a cross; the d-pad is the
                    one with elongated arms (plan aspect), the face buttons
                    are round. Structural, so a rebuilt or resized button set
                    is still recognised (the reference rebuilds both: face
                    buttons -53 % volume, d-pad arms +66 %)
  START / SELECT    the off-plane bodies near the seed's centre buttons,
                    assigned by scale-invariant shape

MEASUREMENT
  The saved model is brought up to date with EditRebuild3 and measured as
  delivered. A forced full rebuild is recorded last as an UNSCORED diagnostic
  (see incremental_census for why it is not scored).

CLI (harness.py --help for everything):
    python harness.py [candidate.SLDPRT]      grade (no arg = active document)
    python harness.py --capture-only P        measure only, store the capture
    python harness.py --score-from cap.json   score a capture, no SolidWorks
    python harness.py --batch [DIR|PARTS]     grade many, tabulate, write files
    python harness.py --capture-baseline P    re-freeze prompt/input.json
    python harness.py --capture-seed-rebuild  refresh only the rebuild census
"""

from __future__ import annotations

import itertools
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK_DIR = HERE.parent


def _find_repo_root(start: Path) -> Path:
    """Directory holding the shared `common` package, searched for rather
    than counted: the harness ships at two different tree depths."""
    d = start
    for _ in range(8):
        if (d / "common" / "__init__.py").is_file():
            return d
        if d.parent == d:
            break
        d = d.parent
    return start.parents[4] if len(start.parents) > 4 else start


_REPO_ROOT = _find_repo_root(HERE)
#: `/opt` is where `common/` sits inside a Harbor verifier container.
for _p in ("/opt", str(_REPO_ROOT / "SolidWorks"), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from common import solidworks_measure as M                      # noqa: E402
from common.solidworks_measure import z                         # noqa: E402
from common import solidworks_capture as SC                     # noqa: E402
from common import solidworks_session as SW                     # noqa: E402
from common import harness_cli as HC                            # noqa: E402
from common import harness_base as HB                           # noqa: E402
from common.harness_base import (Harness, finalize,             # noqa: E402
                                 score_error, write_env)

BASELINE_PATH = TASK_DIR / "prompt" / "input.json"

PASS, PARTIAL, FAIL, UNVERIFIABLE = "PASS", "PARTIAL", "FAIL", "UNVERIFIABLE"

HARNESS_VERSION = "3.0.0-b"
#: /5: exact extreme points per body, the +X ray section of the housing, the
#: raw EditRebuild3 census and the unscored forced-rebuild diagnostic.
CAPTURE_SCHEMA = "ps3-capture/5"
#: /4: adds the seed's structural roles, cluster geometry, grip-lobe rays and
#: the thresholds derived from them (see derive_seed).
BASELINE_SCHEMA = "ps-annotation-baseline/4"

# Metres -> millimetres, applied once, where a number is reported or scored.
MM = 1000.0

JUDGE_NOTE = (
    "No judgement is asked here. What the instruction asks -- the widening, "
    "the re-spacing, the swapped clusters, START/SELECT in mirrored "
    "positions, text kept and kept the right way round -- is measured. "
    "What no measurement settles is whether the reference's own extra "
    "hardware (screws, LED domes) and rebuilt buttons are welcome; they "
    "are reported, not scored, and a judge would not settle that either."
)

# --------------------------------------------------------------------------
# the rubric
# --------------------------------------------------------------------------

C_WIDTH = "widened 15 mm at the grips"
C_SPACE = "clusters re-spaced to the stance"
C_SWAP = "d-pad and face buttons swapped"
C_STSEL = "START/SELECT mirrored"
C_ORIENT = "text and logos oriented"
C_KEPT = "text and logos preserved"
C_UNREQ = "no unrequested changes"
C_REBUILD = "rebuilds cleanly"

#: The asked-for edits carry 7.0, the constraints the instruction names 2.0,
#: the implicit constraints 1.0. An untouched seed collects exactly the last
#: two groups: 3.0 of 10.0.
ALL_CRITERIA = {
    # "Widen the body by 15mm by increasing the separation between the two
    # hand-grip halves (not by scaling the overall housing)" -- asked for.
    C_WIDTH: 2.0,
    # "...and re-space the button clusters to match the wider stance" --
    # asked for.
    C_SPACE: 2.0,
    # "Convert the controller to a left-handed layout by swapping the D-pad
    # and face-button clusters to the opposite side from where they
    # currently sit" -- asked for.
    C_SWAP: 2.0,
    # "The button clusters, START/SELECT labels, and shoulder buttons should
    # end up in mirrored positions" -- asked for; START/SELECT is the part
    # of the sentence no other criterion reads.
    C_STSEL: 1.0,
    # "...any text, logos, and standard/purchased parts ... must remain
    # legible and correctly oriented -- a naive geometric mirror that flips
    # the labels backwards ... is incorrect" -- a constraint the instruction
    # names.
    C_ORIENT: 1.0,
    # "...any text, logos ... must remain legible" -- the same named
    # constraint, its "remain" half: the markings must still be there.
    C_KEPT: 1.0,
    # Implicit: nothing but the edits asked for.
    C_UNREQ: 0.5,
    # Implicit, from task.toml's description: "Make design edits while
    # preserving design intent and feature tree references".
    C_REBUILD: 0.5,
}

#: Every tolerance with its justification. Lengths in mm, unless named _m.
TOL = {
    # -- 1 widening --------------------------------------------------------
    "width_target_mm": 15.0,     # "Widen the body by 15mm"
    "width_perfect_mm": 0.5,     # 15 is stated to the mm: +-0.5 is rounding
    "width_zero_mm": 15.0,       # 100 % relative error: 0 mm (not done) or
                                 # 30 mm (done twice) earns nothing
    "scale_perfect_mm": 0.5,     # lobe width under a rigid separation is
                                 # unchanged; 0.5 mm = the same rounding
    # scale_zero_mm is derived from the seed (derive_seed): the lobe-width
    # change an X-scale reaching the same +15 mm would cause -- the forbidden
    # alternative itself sets where the credit runs out.
    # -- 2 re-spacing ------------------------------------------------------
    "space_perfect_mm": 0.5,     # x position: the widening's own rounding
    "space_zero_mm": 7.5,        # the full per-side move of a 15 mm widening:
                                 # a cluster that did not move earns nothing
    "rigid_perfect_mm": 0.5,     # spacing inside a cluster: same rounding
    "rigid_zero_mm": 5.0,        # a quarter of the seed's 19.8 mm button
                                 # offset: past that it is not the same cluster
    "fit_perfect_mm3": 1.0,      # touching solids intersect to ~0 (the seed
                                 # reads 0.0): 1 mm3 is boolean noise
    "fit_zero_mm3": 50.0,        # ~0.15 mm of overlap across one face
                                 # button's 353 mm2 footprint
    "factor_floor": 0.5,         # rigidity / followers / fit can halve the
                                 # placement credit, never erase it
    # -- 4 START/SELECT ----------------------------------------------------
    "stsel_perfect_mm": 0.5,     # same rounding as above; zero is |u_seed|:
                                 # an item that has not crossed the plane
    # -- 7 unrequested (interim parts) -------------------------------------
    "fp_perfect": 0.01,          # unchanged B-rep mass props repeat to ~1e-5;
                                 # 1 % is the smallest deliberate resize
    "fp_zero": 0.08,
    "drift_perfect_mm": 0.5,     # the instruction moves nothing in y or z
    "drift_zero_mm": 5.0,        # a third of the requested change
    "span_perfect_mm": 0.5,      # housing Y/Z spans: X only is asked for
    "span_zero_mm": 5.0,
    # -- 8 rebuild (interim: v2's fraction) --------------------------------
    "health_perfect_frac": 0.0,
    "health_zero_frac": 0.20,
}

# Structural constants, each with its basis.
#: A housing body spans the controller. Seed: the housing spans 100 % of the
#: part's X extent, the widest control (a trigger) 11 %. Split shells or
#: halves keep each piece above a third.
HOUSING_SPAN_FRAC = 0.35
#: Bootstrap grouping for the SEED's own clusters only: its face buttons
#: differ by 0.011 in fingerprint (different symbols), its two closest
#: distinct roles (triggers, bumpers) by 0.136. Candidates use a threshold
#: derived from the seed instead (seed.congruent_tol).
SEED_CONGRUENT = 0.05
#: A cross of four buttons: radii equal, opposite pairs cancelling and the
#: two pairs perpendicular, each to within 10 %. The seed's clusters are
#: exact to 0.1 %; a row of identical bodies (LED domes) fails perpendicular.
DIAMOND_TOL = 0.10
#: A body "on the plane": the seed's on-plane bodies sit within 0.01 mm of
#: it, its nearest off-plane control 23 mm away.
PLANE_ON_MM = 2.0
#: Seed only: top-surface buttons sit within 15 mm of the housing top (seed
#: 6.3-7.3 mm); the two small on-plane bodies sit 25.7 mm down.
CENTRE_DEPTH_MM = 15.0
#: Seed only: centre buttons lie between the clusters (seed |u| 23-24 mm,
#: clusters 80.5 mm): half the cluster offset.
CENTRE_U_MAX_MM = 40.0

# Ray sections of the housing (swRayPtsOpts_e / swRayPtsResults_e values are
# the documented ones; common/solidworks_rays.py has ENTRY_EXIT and TOPOLS
# swapped and is not used here).
RAY_NORMALS, RAY_ENTRY_EXIT = 1, 4
RAY_ENTER, RAY_EXIT = 16, 32
RAY_HIT_RADIUS_M = 1e-6
RAY_OFFSET_M = 1e-7
RAY_CHUNK = 2000
#: A hit further than this from the ray its row names means the hit array is
#: not laid out as documented; the capture refuses to read it.
RAY_ON_TOL_M = 1e-5
#: Seed grid: 2 mm puts ~25 rays across each 51.8 mm grip lobe. Cast once,
#: when the baseline is frozen (4 080 rays, 32 s on the seed).
XSECTION_STEP_M = 0.002
#: Candidates cast every 3rd seed ray in y and z (a 6 mm lattice, ~190 rays):
#: rays cost 8 ms each on the seed and 63 ms on the reference's shells.
XSECTION_LATTICE = 3
XSECTION_LEAD_M = 0.02
#: A median of fewer rays than this is not read as a grip measurement.
MIN_LOBE_RAYS = 20

# v2 carry-overs used by the interim criteria 5 and 6.
SMALL_FACE_AREA = 15e-6          # engraving-scale faces (m2)
LIGHT_FACE_MAX_AREA = 8e-6
LIGHT_MIN_OFFPLANE_M = 0.040
LIGHT_AREA_TOL_FRAC = 0.02
LIGHT_CLUSTER_RADIUS_M = 0.020
LIGHT_MIN_MATCHES = 3
MARKINGS_FULL_FRACTION = 0.75
NEUTRAL_UNVERIFIABLE = 0.5       # unreadable is not free

CONTROL_ROLES = ("dpad", "face_buttons", "select", "start", "ps",
                 "sticks", "triggers", "bumpers")
PAIR_ROLES = ("sticks", "triggers", "bumpers")
KEPT_ROLES = ("sticks", "triggers", "bumpers", "plane_small")


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def clamp01(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    if v != v:
        return 0.0
    return max(0.0, min(1.0, v))


def mean(values, default=None):
    vals = list(values)
    return sum(vals) / len(vals) if vals else default


def status_of(score, floor=1e-9):
    if score >= 1.0 - floor:
        return PASS
    if score <= floor:
        return FAIL
    return PARTIAL


def factor(score):
    """A multiplier that can halve the credit it qualifies, never erase it."""
    f = TOL["factor_floor"]
    return f + (1.0 - f) * clamp01(score)


def fingerprint(b):
    I = b["inertia_com"]
    return [b["volume_m3"], b["area_m2"]] + sorted([I["Ixx"], I["Iyy"],
                                                    I["Izz"]])


def fp_distance(a, b):
    """RMS relative difference of (volume, area, sorted principal moments):
    invariant to translation and to a mirror about any axis plane."""
    fa, fb = fingerprint(a), fingerprint(b)
    return math.sqrt(sum(((u - v) / max(abs(u), abs(v), 1e-30)) ** 2
                         for u, v in zip(fa, fb)) / len(fa))


def shape_si(b):
    """Scale-invariant shape: A / V^(2/3) and the sorted moments over
    V^(5/3). A uniformly resized button reads the same."""
    V = b["volume_m3"]
    if V <= 0:
        return None
    I = b["inertia_com"]
    return [b["area_m2"] / V ** (2 / 3)] + sorted(
        x / V ** (5 / 3) for x in (I["Ixx"], I["Iyy"], I["Izz"]))


def si_distance(a, b):
    fa, fb = shape_si(a), shape_si(b)
    if fa is None or fb is None:
        return float("inf")
    return math.sqrt(sum(((u - v) / max(abs(u), abs(v), 1e-30)) ** 2
                         for u, v in zip(fa, fb)) / len(fa))


def extent_of(b):
    """Exact extents from GetExtremePoint; GetBodyBox ("approximate, not for
    comparison") only when a capture predates them."""
    e = b.get("extent_m") or b.get("bbox_m")
    return e if e and len(e) == 6 else None


def plan_aspect(b):
    e = extent_of(b)
    if not e:
        return None
    lo, hi = sorted((abs(e[3] - e[0]), abs(e[5] - e[2])))
    return hi / lo if lo > 0 else None


def d3(a, b):
    return math.sqrt(sum((u - v) ** 2 for u, v in zip(a, b)))


def sgn(v):
    return 1.0 if v >= 0 else -1.0


# --------------------------------------------------------------------------
# COM measurement layer
# --------------------------------------------------------------------------

def _body_summary(bodies):
    return sorted(({"volume_m3": b["volume_m3"], "area_m2": b["area_m2"],
                    "centroid_m": b["centroid_m"]} for b in bodies),
                  key=lambda r: -r["volume_m3"])


def _census_key(census):
    return sorted((n, int(c), bool(w)) for n, (c, w) in (census or {}).items())


def incremental_census(doc):
    """Bring the saved model up to date, then read each feature's error state.
    THIS is the census rebuild health is scored on, and the geometry every
    criterion reads is measured right after it.

    IModelDoc2::EditRebuild3 rebuilds only what is out of date, so a file
    whose cached B-rep is stale is regenerated where it is stale, and a
    consistent file is left exactly as saved. Measured on SolidWorks 2026
    SP4.1 (fresh open, seed / reference / feature_tree_with_errors /
    unwidened_shell): it changed no body volume on any of them, and it
    reports the saved trees' real faults (15 and 34 failing features on the
    two broken adversaries, 0 on the seed and the reference).

    A FORCED full rebuild is not used for scoring: on the same machine the
    reference never rebuilds clean under it (DeleteFace33/34 fail on every
    pass, two new warnings) although its saved state is consistent, and a
    forced pass run straight after opening even broke the untouched seed
    (18 features, -20 522 mm3). It is still taken, last, as an unscored
    diagnostic (forced_rebuild_diagnostic).
    """
    try:
        _, cached, _, _, _ = SC.capture_bodies(doc)
    except Exception:                                       # noqa: BLE001
        cached = []
    t0 = time.time()
    returned, error = None, None
    try:
        member = doc.EditRebuild3
        returned = bool(member() if callable(member) else member)
    except Exception as exc:                                # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    seconds = time.time() - t0
    census, meta = SC.feature_census(doc, rebuild=None)     # read only
    return {"mode": "incremental",
            "edit_rebuild_returned": returned,
            "edit_rebuild_error": error,
            "rebuild_seconds": round(seconds, 2),
            "features": meta.get("features", 0),
            "census": census or {},
            "cached_bodies": _body_summary(cached)}


#: Forced passes in the diagnostic, at most: repeated until two in a row give
#: the same census. One pass is not a reading on this corpus -- the probe saw
#: the reference go 4 -> 2 -> 2 failing features over three passes.
FORCE_REBUILD_MAX_PASSES = 3


def forced_rebuild_diagnostic(doc, max_passes=FORCE_REBUILD_MAX_PASSES):
    """UNSCORED. How the tree fares when every feature is regenerated from
    scratch, repeated until the census stops changing. Must run AFTER every
    measurement: a forced rebuild mutates the geometry (the probe saw up to
    3 264 mm3 move on feature_tree_with_errors).

    IModelDoc2::ForceRebuild3 returns False when ANY feature fails, so its
    return value is recorded per pass, never used as a verdict.
    """
    try:
        _, before, _, _, _ = SC.capture_bodies(doc)
    except Exception:                                       # noqa: BLE001
        before = []
    passes, census, meta = [], {}, {"features": 0}
    previous, stable = None, False
    for k in range(1, max_passes + 1):
        t0 = time.time()
        returned, error = None, None
        try:
            returned = bool(doc.ForceRebuild3(False))
        except Exception as exc:                            # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
        seconds = time.time() - t0
        census, meta = SC.feature_census(doc, rebuild=None)  # read only
        census = census or {}
        key = _census_key(census)
        passes.append({"pass": k, "returned": returned, "error": error,
                       "seconds": round(seconds, 2),
                       "hard": sum(1 for _, _, w in key if not w),
                       "warnings": sum(1 for _, _, w in key if w),
                       "failing": [n for n, _, _ in key][:25]})
        if (returned and not census) or key == previous:
            stable = True
            break
        previous = key
    try:
        _, after, _, _, _ = SC.capture_bodies(doc)
    except Exception:                                       # noqa: BLE001
        after = []
    a = sorted(b["volume_m3"] for b in before)
    b = sorted(x["volume_m3"] for x in after)
    return {"mode": "force-until-stable",
            "scored": False,
            "passes": passes,
            "stable": stable,
            "seconds": round(sum(p["seconds"] for p in passes), 2),
            "features": meta.get("features", 0),
            "census": census,
            "bodies_before": len(a), "bodies_after": len(b),
            "max_body_volume_change_mm3": (
                round(max(abs(u - v) for u, v in zip(a, b)) * 1e9, 3)
                if len(a) == len(b) and a else None)}


def cache_drift(rebuild, bodies):
    """How far the geometry cached in the file was from what EditRebuild3
    left. Diagnostic only -- never scored."""
    cached = (rebuild or {}).get("cached_bodies")
    if cached is None:
        return None
    a = sorted(r["volume_m3"] for r in cached)
    b = sorted(x["volume_m3"] for x in bodies)
    out = {"bodies_cached": len(a), "bodies_rebuilt": len(b),
           "volume_cached_mm3": round(sum(a) * 1e9, 3),
           "volume_rebuilt_mm3": round(sum(b) * 1e9, 3)}
    if len(a) == len(b) and a:
        out["max_body_volume_change_mm3"] = round(
            max(abs(u - v) for u, v in zip(a, b)) * 1e9, 3)
    return out


def _extreme_point(body, d):
    """IBody2::GetExtremePoint(X, Y, Z, out Outx, out Outy, out Outz).

    Bodies handed back by GetBodies2 carry type information, so pywin32
    makes a TYPED call: out-params go in as plain floats and come back in the
    result tuple (ok, x, y, z). The VARIANT(VT_BYREF|VT_R8) idiom raises
    "float() argument must be ... not 'VARIANT'" there (measured on this
    machine); it is kept as the fallback for an untyped dispatch.
    """
    try:
        res = body.GetExtremePoint(d[0], d[1], d[2], 0.0, 0.0, 0.0)
        if isinstance(res, tuple) and len(res) == 4:
            return bool(res[0]), (float(res[1]), float(res[2]),
                                  float(res[3]))
    except TypeError:
        pass
    import pythoncom
    from win32com.client import VARIANT
    out = [VARIANT(pythoncom.VT_BYREF | pythoncom.VT_R8, 0.0)
           for _ in range(3)]
    ok = body.GetExtremePoint(d[0], d[1], d[2], *out)
    return bool(ok), tuple(float(v.value) for v in out)


def body_extent(body):
    """[xmin, ymin, zmin, xmax, ymax, zmax], exact. Measured on the seed the
    approximate GetBodyBox is up to 2.6 mm loose on the housing."""
    lo, hi = [0.0] * 3, [0.0] * 3
    for axis in range(3):
        for sign in (-1.0, 1.0):
            d = [0.0, 0.0, 0.0]
            d[axis] = sign
            ok, p = _extreme_point(body, d)
            if not ok:
                return None
            (lo if sign < 0 else hi)[axis] = p[axis]
    return lo + hi


def _ray_points(doc):
    """IModelDoc2::GetRayIntersectionsPoints is a PROPERTY late-bound; read
    it whichever way this build exposes it."""
    for fn in (lambda: doc.GetRayIntersectionsPoints,
               lambda: doc.GetRayIntersectionsPoints()):
        try:
            v = fn()
            if v is None or callable(v):
                continue
            v = list(v)
            if v:
                return v
        except Exception:                                   # noqa: BLE001
            continue
    return []


def cast_rays(doc, bodies, origins, dirs):
    """{ray index: [(distance along ray (m), swRayPtsResults_e), ...]}.

    IModelDoc2::RayIntersections(Bodies, BasePoints, Vectors, Options,
    HitRadius, Offset); per hit GetRayIntersectionsPoints gives [BodyIndex,
    RayIndex, IntersectionType, x, y, z, nx, ny, nz] (NORMALS requested).
    The layout is CHECKED, not assumed: every hit must lie on the ray its row
    names, or the capture refuses the array.
    """
    import numpy as np
    import pythoncom
    from win32com.client import VARIANT
    o_all = np.asarray(origins, float).reshape(-1, 3)
    d_all = np.asarray(dirs, float).reshape(-1, 3)
    disp = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, list(bodies))
    out = {}
    for s in range(0, len(o_all), RAY_CHUNK):
        o = o_all[s:s + RAY_CHUNK]
        d = d_all[s:s + RAY_CHUNK]
        n = doc.RayIntersections(
            disp,
            VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8,
                    [float(v) for v in o.ravel()]),
            VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8,
                    [float(v) for v in d.ravel()]),
            RAY_NORMALS | RAY_ENTRY_EXIT, RAY_HIT_RADIUS_M, RAY_OFFSET_M)
        n = int(n or 0)
        if not n:
            continue
        raw = _ray_points(doc)
        if not raw or len(raw) % n:
            raise RuntimeError(f"{len(raw)} hit values do not divide into "
                               f"{n} hits")
        a = np.asarray(raw, float).reshape(n, len(raw) // n)
        if a.shape[1] < 6:
            raise RuntimeError("hit rows narrower than documented")
        col = a[:, 1]
        if (not np.all(col == np.floor(col)) or col.min() < 0
                or col.max() >= len(o)):
            raise RuntimeError("ray-index column not as documented")
        ri = col.astype(int)
        v = a[:, 3:6] - o[ri]
        t = np.einsum("ij,ij->i", v, d[ri])
        off = np.linalg.norm(v - t[:, None] * d[ri], axis=1)
        if float(off.max()) > RAY_ON_TOL_M:
            raise RuntimeError(f"hits lie {float(off.max()):.2e} m off their "
                               f"rays: layout not as documented")
        for r, tt, typ in zip(ri, t, a[:, 2]):
            out.setdefault(s + int(r), []).append((float(tt), int(typ)))
    return {k: sorted(v) for k, v in out.items()}


def xsection_rays(hext, keys=None, step=XSECTION_STEP_M):
    """(keys, origins, grid) for +X rays on the (y, z) grid anchored at THIS
    housing's own ymin/zmin. keys are "iy,iz"; None = the full grid."""
    y0, z0 = hext[1], hext[2]
    ny = int((hext[4] - y0) / step)
    nz = int((hext[5] - z0) / step)
    if keys is None:
        keys = [f"{iy},{iz}" for iy in range(ny) for iz in range(nz)]
    origins = []
    for k in keys:
        iy, iz = (int(v) for v in k.split(","))
        origins.append([hext[0] - XSECTION_LEAD_M, y0 + (iy + 0.5) * step,
                        z0 + (iz + 0.5) * step])
    return keys, origins, {"step_m": step, "y0_m": y0, "z0_m": z0,
                           "ny": ny, "nz": nz}


def housing_xsection(doc, hbodies, hext, keys=None):
    """+X ray section of the housing bodies: per ray the hit x and type."""
    keys, origins, grid = xsection_rays(hext, keys)
    t0 = time.time()
    hits = cast_rays(doc, hbodies, origins, [[1.0, 0.0, 0.0]] * len(origins))
    x0 = hext[0] - XSECTION_LEAD_M
    rays = {k: [[round(x0 + t, 7), typ] for t, typ in hits.get(i, [])]
            for i, k in enumerate(keys)}
    return {**grid, "rays": rays, "n_rays": len(keys),
            "seconds": round(time.time() - t0, 2)}


def _small_face_counts(raw_bodies):
    out = {}
    for idx, b in enumerate(raw_bodies):
        n = 0
        for f in (z(b.GetFaces) or []):
            try:
                if float(z(f.GetArea)) < SMALL_FACE_AREA:
                    n += 1
            except Exception:                               # noqa: BLE001
                continue
        out[f"c{idx:02d}"] = n
    return out


def housing_faces(raw_bodies, housing):
    """(area, box-centre xyz) per housing face."""
    out = []
    for hid in housing:
        for f in (z(raw_bodies[int(hid[1:])].GetFaces) or []):
            try:
                a = float(z(f.GetArea))
                box = z(f.GetBox)
                c = [(float(box[k]) + float(box[k + 3])) / 2 for k in range(3)]
            except Exception:                               # noqa: BLE001
                continue
            out.append((a, c))
    return out


def _light_group(cand, plane_x):
    best = None
    for a0, c0 in cand:
        grp = [(a, c) for a, c in cand
               if math.hypot(c[0] - c0[0], c[2] - c0[2])
               < LIGHT_CLUSTER_RADIUS_M]
        if best is None or len(grp) > len(best):
            best = grp
    if not best or len(best) < LIGHT_MIN_MATCHES:
        return None
    cx = sum(c[0] for _, c in best) / len(best)
    return {"areas_m2": sorted(a for a, _ in best),
            "centroid_m": [sum(c[k] for _, c in best) / len(best)
                           for k in range(3)],
            "side": 1 if cx >= plane_x else -1,
            "n_faces": len(best)}


def find_light_cluster_seed(faces, plane_x, bbox):
    """v2 (interim criterion 5): the engraving-scale face cluster on the
    top-rear edge well off the plane -- the engraved "R" shoulder label."""
    y_top, z_rear = bbox[4], bbox[2]
    cand = [(a, c) for a, c in faces
            if a < LIGHT_FACE_MAX_AREA
            and abs(c[0] - plane_x) > LIGHT_MIN_OFFPLANE_M
            and (y_top - c[1]) < 0.030 and (c[2] - z_rear) < 0.020]
    return _light_group(cand, plane_x) if len(cand) >= LIGHT_MIN_MATCHES \
        else None


def find_light_cluster_candidate(faces, plane_x, seed_cluster):
    """v2: the seed cluster re-found by its mirror-invariant area multiset."""
    if not seed_cluster:
        return None
    hits = []
    for want in seed_cluster["areas_m2"]:
        best, bd = None, None
        for a, c in faces:
            dd = abs(a - want) / max(want, 1e-30)
            if dd < LIGHT_AREA_TOL_FRAC and (bd is None or dd < bd):
                best, bd = (a, c), dd
        if best:
            hits.append(best)
    return _light_group(hits, plane_x) if len(hits) >= LIGHT_MIN_MATCHES \
        else None


def control_interference(raw, bodies, controls, housing):
    """Boolean-intersect volume among control bodies and control vs housing
    (IBody2::Copy + Operations2 SWBODYINTERSECT on the copies)."""
    by = {b["id"]: b for b in bodies}
    boxes = {i: by[i]["bbox_m"] for i in set(controls) | set(housing)}
    tests = list(itertools.combinations(sorted(controls), 2)) + \
        [(a, h) for a in sorted(controls) for h in housing]
    pairs, total, failures = [], 0.0, 0
    for a, b in tests:
        if not M._boxes_overlap(boxes[a], boxes[b], M.BBOX_PAD):
            continue
        try:
            res, code = M._operations2(z(raw[int(a[1:])].Copy),
                                       z(raw[int(b[1:])].Copy))
            vol = 0.0
            for rb in (res or []):
                try:
                    vol += float(rb.GetMassProperties(0.0)[3])
                except Exception:                           # noqa: BLE001
                    pass
            if vol > M.MIN_INTERFERENCE_VOLUME or code != 0:
                total += vol
                failures += 1 if code != 0 else 0
                pairs.append({"a": a, "b": b, "volume_m3": vol,
                              "error_code": code})
        except Exception:                                   # noqa: BLE001
            failures += 1
            pairs.append({"a": a, "b": b, "volume_m3": 0.0, "error_code": -1})
    return {"tested_pairs": len(tests), "pairs": pairs,
            "total_volume_m3": total, "boolean_failures": failures,
            "controls": sorted(controls), "housing": list(housing)}


# --------------------------------------------------------------------------
# pure geometry: housing, plane, grip lobes, roles
# --------------------------------------------------------------------------

def housing_ids(bodies):
    ext = {b["id"]: extent_of(b) for b in bodies}
    ext = {k: e for k, e in ext.items() if e}
    if not ext:
        return []
    x0 = min(e[0] for e in ext.values())
    x1 = max(e[3] for e in ext.values())
    w = x1 - x0
    if w <= 0:
        return []
    return sorted(k for k, e in ext.items()
                  if (e[3] - e[0]) >= HOUSING_SPAN_FRAC * w)


def union_extent(bodies, ids):
    want = set(ids)
    es = [extent_of(b) for b in bodies if b["id"] in want]
    es = [e for e in es if e]
    if not es:
        return None
    return ([min(e[k] for e in es) for k in range(3)]
            + [max(e[k + 3] for e in es) for k in range(3)])


def ray_inside_at(hits, x):
    """Is there material at x on this ray? From the ENTER/EXIT flags of the
    hits before x; an edge graze (both flags, or neither) changes nothing."""
    inside = False
    for hx, typ in hits:
        if hx >= x:
            break
        ent, ext = bool(typ & RAY_ENTER), bool(typ & RAY_EXIT)
        if ent and not ext:
            inside = True
        elif ext and not ent:
            inside = False
    return inside


def ray_lobes(hits, plane):
    """((l0, l1), (r0, r1)): the OUTERMOST material on each side of the
    plane. Outermost, because a shelled grip is hit four times -- outer and
    inner wall -- and its outer extent is what a hand holds."""
    left = [x for x, _ in hits if x < plane]
    right = [x for x, _ in hits if x > plane]
    if len(left) < 2 or len(right) < 2:
        return None
    return (min(left), max(left)), (min(right), max(right))


def seed_lobe_keys(xsec, plane):
    """Seed rays whose section is two separate grips: no material at the
    plane and material on both sides. Read on the SEED only: a hollow shell
    also shows "two lobes" where a ray crosses its empty bridge."""
    keys = []
    for k, hits in xsec["rays"].items():
        hits = [tuple(h) for h in hits]
        if hits and not ray_inside_at(hits, plane) and ray_lobes(hits, plane):
            keys.append(k)
    return keys


def lobe_stats(xsec, plane, keys):
    """{key: [cL, cR, wL, wR]} (m) for the keys whose lobes both exist."""
    out = {}
    rays = (xsec or {}).get("rays") or {}
    for k in keys:
        lob = ray_lobes([tuple(h) for h in (rays.get(k) or [])], plane)
        if lob:
            (l0, l1), (r0, r1) = lob
            out[k] = [(l0 + l1) / 2, (r0 + r1) / 2, l1 - l0, r1 - r0]
    return out


def plane_from_lobes(xsec, plane0, keys):
    """Median midline of the two grip lobes, refined once about itself."""
    st = lobe_stats(xsec, plane0, keys)
    if len(st) < MIN_LOBE_RAYS:
        return None, st
    p = statistics.median((v[0] + v[1]) / 2 for v in st.values())
    if abs(p - plane0) > 0.002:
        st2 = lobe_stats(xsec, p, keys)
        if len(st2) >= MIN_LOBE_RAYS:
            st = st2
            p = statistics.median((v[0] + v[1]) / 2 for v in st.values())
    return p, st


def _union_groups(bodies, tol):
    """Groups of bodies within `tol` of each other in fingerprint."""
    ids = [b["id"] for b in bodies]
    by = {b["id"]: b for b in bodies}
    parent = {i: i for i in ids}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in itertools.combinations(ids, 2):
        if fp_distance(by[a], by[b]) <= tol:
            parent[find(a)] = find(b)
    groups = {}
    for i in ids:
        groups.setdefault(find(i), []).append(i)
    return [sorted(g) for g in groups.values()]


def _diamond(bs):
    """(cx, cz, radius, irregularity) if four bodies form a cross in plan:
    two opposite pairs on perpendicular axes, all at one radius."""
    cx = sum(b["centroid_m"][0] for b in bs) / 4
    cz = sum(b["centroid_m"][2] for b in bs) / 4
    off = [(b["centroid_m"][0] - cx, b["centroid_m"][2] - cz) for b in bs]
    r = [math.hypot(*o) for o in off]
    rm = sum(r) / 4
    if rm <= 0:
        return None
    spread = max(abs(x - rm) for x in r) / rm
    if spread > DIAMOND_TOL:
        return None
    best = None
    for (a, b), (c, d) in (((0, 1), (2, 3)), ((0, 2), (1, 3)),
                           ((0, 3), (1, 2))):
        s1 = math.hypot(off[a][0] + off[b][0], off[a][1] + off[b][1]) / rm
        s2 = math.hypot(off[c][0] + off[d][0], off[c][1] + off[d][1]) / rm
        cos = abs(off[a][0] * off[c][0] + off[a][1] * off[c][1]) / (r[a] * r[c])
        if s1 <= DIAMOND_TOL and s2 <= DIAMOND_TOL and cos <= DIAMOND_TOL:
            irr = max(spread, s1, s2, cos)
            if best is None or irr < best:
                best = irr
    if best is None:
        return None
    return cx, cz, rm, best


def find_diamonds(bodies, tol):
    """Non-overlapping crosses of four congruent bodies, most regular first."""
    by = {b["id"]: b for b in bodies}
    found = []
    for g in _union_groups(bodies, tol):
        if len(g) < 4:
            continue
        for quad in itertools.combinations(g, 4):
            d = _diamond([by[i] for i in quad])
            if d:
                found.append((d[3], list(quad), d))
    found.sort(key=lambda t: (t[0], t[1]))
    used, out = set(), []
    for _, quad, d in found:
        if used.isdisjoint(quad):
            used.update(quad)
            out.append({"ids": quad, "cx_m": d[0], "cz_m": d[1],
                        "radius_m": d[2],
                        "aspect": mean(plan_aspect(by[i]) or 1.0
                                       for i in quad)})
    return out


def _pair_dists(bodies, ids):
    by = {b["id"]: b for b in bodies}
    return sorted(d3(by[a]["centroid_m"], by[b]["centroid_m"])
                  for a, b in itertools.combinations(ids, 2))


def seed_roles(bodies, plane, hext):
    """The SEED's roles, from structure. Raises if the seed does not read as
    the controller it is (a re-freeze must fail loudly, not grade wrongly)."""
    by = {b["id"]: b for b in bodies}
    hids = housing_ids(bodies)
    others = [b for b in bodies if b["id"] not in hids]
    diamonds = find_diamonds(others, SEED_CONGRUENT)
    if len(diamonds) != 2:
        raise RuntimeError(f"seed: expected two button crosses, found "
                           f"{len(diamonds)}")
    dpad, face = sorted(diamonds, key=lambda d: -d["aspect"])
    roles = {"housing": hids, "dpad": dpad["ids"],
             "face_buttons": face["ids"]}
    taken = set(hids) | set(dpad["ids"]) | set(face["ids"])
    rest = [b for b in others if b["id"] not in taken]

    def u(b):
        return b["centroid_m"][0] - plane

    pairs = []
    for g in _union_groups(rest, SEED_CONGRUENT):
        if len(g) != 2:
            continue
        a, b = by[g[0]], by[g[1]]
        if (abs(u(a) + u(b)) * MM <= PLANE_ON_MM
                and abs(a["centroid_m"][1] - b["centroid_m"][1]) * MM
                <= PLANE_ON_MM
                and abs(a["centroid_m"][2] - b["centroid_m"][2]) * MM
                <= PLANE_ON_MM and abs(u(a)) * MM > PLANE_ON_MM):
            pairs.append(g)
    if len(pairs) != 3:
        raise RuntimeError(f"seed: expected three mirror pairs, found "
                           f"{len(pairs)}")
    # top to bottom: sticks on the face, bumpers, triggers underneath
    pairs.sort(key=lambda g: -by[g[0]]["centroid_m"][1])
    roles["sticks"], roles["bumpers"], roles["triggers"] = pairs
    taken |= {i for g in pairs for i in g}
    rest = [b for b in rest if b["id"] not in taken]
    top = hext[4]
    centre = [b for b in rest if abs(u(b)) * MM <= CENTRE_U_MAX_MM
              and (top - b["centroid_m"][1]) * MM <= CENTRE_DEPTH_MM]
    on = [b for b in centre if abs(u(b)) * MM <= PLANE_ON_MM]
    off = [b for b in centre if abs(u(b)) * MM > PLANE_ON_MM]
    if len(on) != 1 or len(off) != 2 or u(off[0]) * u(off[1]) >= 0:
        raise RuntimeError("seed: expected the PS button on the plane and "
                           "one centre button each side of it")
    roles["ps"] = [on[0]["id"]]
    # The seed is right-handed: SELECT sits left of the plane, START right.
    roles["select"] = [min(off, key=u)["id"]]
    roles["start"] = [max(off, key=u)["id"]]
    taken |= {b["id"] for b in centre}
    small = [b for b in rest if b["id"] not in taken
             and abs(u(b)) * MM <= PLANE_ON_MM]
    roles["plane_small"] = sorted(b["id"] for b in small)
    roles["other"] = sorted(b["id"] for b in rest if b["id"] not in taken
                            and b["id"] not in roles["plane_small"])
    return roles, {"dpad_aspect": dpad["aspect"],
                   "face_aspect": face["aspect"]}


def derive_seed(cap):
    """Everything a candidate is compared against, from the seed's capture."""
    bodies = cap["bodies"]
    hids = housing_ids(bodies)
    hext = union_extent(bodies, hids)
    xsec = cap["xsection"]
    plane0 = (hext[0] + hext[3]) / 2
    two = seed_lobe_keys(xsec, plane0)
    plane, _ = plane_from_lobes(xsec, plane0, two)
    if plane is None:
        raise RuntimeError("seed: grip lobes not found in the ray section")
    two = seed_lobe_keys(xsec, plane)
    sparse = [k for k in two
              if all(int(v) % XSECTION_LATTICE == 0 for v in k.split(","))]
    lobes = lobe_stats(xsec, plane, sparse)
    widths = [v[2] for v in lobes.values()] + [v[3] for v in lobes.values()]
    lobe_w = statistics.median(widths)
    info = seed_role_info(bodies, plane, hext)
    info.update({
        "plane_x_m": plane,
        "housing_extent_m": hext,
        "xsection": {"step_m": XSECTION_STEP_M,
                     "lattice": XSECTION_LATTICE,
                     "keys": sparse,
                     "lobes": lobes,
                     "two_lobe_rays": len(two),
                     "lobe_width_median_m": lobe_w,
                     "separation_median_m": statistics.median(
                         v[1] - v[0] for v in lobes.values())},
        "scale_zero_mm": lobe_w * TOL["width_target_mm"]
        / (hext[3] - hext[0]),
    })
    return info


def seed_role_info(bodies, plane, hext):
    """The seed's roles and the identity thresholds candidates are judged
    by, every one read off the seed itself."""
    by = {b["id"]: b for b in bodies}
    hids = housing_ids(bodies)
    roles, diag = seed_roles(bodies, plane, hext)

    def u(i):
        return by[i]["centroid_m"][0] - plane

    # Thresholds a candidate is judged by, all read off the seed.
    inter = [fp_distance(by[a], by[b])
             for ra, rb in itertools.combinations(
                 [r for r in roles if r not in ("housing", "other")], 2)
             for a in roles[ra] for b in roles[rb]]
    clusters = {}
    for role in ("dpad", "face_buttons"):
        ids = roles[role]
        cx = sum(by[i]["centroid_m"][0] for i in ids) / 4
        cz = sum(by[i]["centroid_m"][2] for i in ids) / 4
        clusters[role] = {
            "ids": ids, "u_m": cx - plane,
            "y_m": sum(by[i]["centroid_m"][1] for i in ids) / 4,
            "z_m": cz,
            "radius_m": sum(math.hypot(by[i]["centroid_m"][0] - cx,
                                       by[i]["centroid_m"][2] - cz)
                            for i in ids) / 4,
            "aspect": mean(plan_aspect(by[i]) or 1.0 for i in ids),
            "pair_dists_m": _pair_dists(bodies, ids)}
    kept = {role: [dict(by[i], u_m=u(i)) for i in roles[role]]
            for role in KEPT_ROLES}
    centre = {}
    for role in ("select", "start", "ps"):
        b = by[roles[role][0]]
        centre[role] = {"id": b["id"], "u_m": u(b["id"]),
                        "y_m": b["centroid_m"][1], "z_m": b["centroid_m"][2],
                        "volume_m3": b["volume_m3"], "area_m2": b["area_m2"],
                        "inertia_com": b["inertia_com"]}
    # START/SELECT search radius: half the distance from each to the nearest
    # other seed body, so the window never reaches a neighbouring part.
    near = []
    for role in ("select", "start"):
        me = by[roles[role][0]]
        near.append(min(d3(me["centroid_m"], o["centroid_m"])
                        for o in bodies if o["id"] != me["id"]
                        and o["id"] not in hids))
    return {
        "roles": roles,
        "role_notes": diag,
        "clusters": clusters,
        "kept": kept,
        "centre": centre,
        "pool_radius_m": 0.5 * min(near),
        "congruent_tol": 0.5 * min(inter),
        "aspect_threshold": 0.5 * (diag["dpad_aspect"] + diag["face_aspect"]),
    }


def widening(xsec, hext, seed):
    """(plane, lobes, measures) for a candidate: its own mirror plane, the
    grip-separation growth, the body-extent growth and the lobe-width drift,
    every length in metres; None where it cannot be read."""
    sx = seed["xsection"]
    plane0 = (hext[0] + hext[3]) / 2
    plane, st = (None, {})
    if xsec and xsec.get("rays"):
        plane, st = plane_from_lobes(xsec, plane0, sx["keys"])
    common = [k for k in st if k in sx["lobes"]]
    dsep = dwidth = None
    if plane is not None and len(common) >= MIN_LOBE_RAYS:
        dsep = statistics.median(
            (st[k][1] - st[k][0]) - (sx["lobes"][k][1] - sx["lobes"][k][0])
            for k in common)
        dwidth = statistics.median(
            [abs(st[k][2] - sx["lobes"][k][2]) for k in common]
            + [abs(st[k][3] - sx["lobes"][k][3]) for k in common])
    sh = seed["housing_extent_m"]
    dext = (hext[3] - hext[0]) - (sh[3] - sh[0])
    return (plane if plane is not None else plane0), st, {
        "plane_source": "grip lobes" if plane is not None
        else "housing extent midline",
        "lobe_rays": len(common), "dsep_m": dsep, "dext_m": dext,
        "dwidth_m": dwidth}


def candidate_roles(bodies, plane, seed, h):
    """A candidate's roles. Kept bodies by seed fingerprint; clusters by
    structure; START/SELECT by scale-invariant shape near the seed's centre
    buttons. Returns (roles, diagnostics)."""
    from scipy.optimize import linear_sum_assignment
    by = {b["id"]: b for b in bodies}
    hids = housing_ids(bodies)
    others = [b for b in bodies if b["id"] not in hids]
    tol = seed["congruent_tol"]
    roles = {"housing": hids}
    diag = {"congruent_tol": tol}

    def u(i):
        return by[i]["centroid_m"][0] - plane

    # kept bodies: optimal assignment, rejected beyond the seed's own
    # half-distance between two different roles
    rows = [(role, rec) for role in KEPT_ROLES for rec in seed["kept"][role]]
    taken = set()
    for role in KEPT_ROLES:
        roles[role] = []
    if rows and others:
        cost = [[fp_distance(rec, b) for b in others] for _, rec in rows]
        ri, ci = linear_sum_assignment(cost)
        for r, c in zip(ri, ci):
            if cost[r][c] <= tol:
                roles[rows[r][0]].append(others[c]["id"])
                taken.add(others[c]["id"])
    rest = [b for b in others if b["id"] not in taken]

    # button clusters
    diamonds = find_diamonds(rest, tol)
    thr = seed["aspect_threshold"]
    dup = []
    for role, is_kind in (("dpad", lambda d: d["aspect"] > thr),
                          ("face_buttons", lambda d: d["aspect"] <= thr)):
        kind = [d for d in diamonds if is_kind(d)]
        us = seed["clusters"][role]["u_m"]
        u_exp = -us + sgn(-us) * h
        kind.sort(key=lambda d: (abs((d["cx_m"] - plane) - u_exp), d["ids"]))
        roles[role] = kind[0]["ids"] if kind else []
        dup += [d["ids"] for d in kind[1:]]
    diag["clusters"] = [{"ids": d["ids"], "u_mm": round((d["cx_m"] - plane)
                                                         * MM, 2),
                         "aspect": round(d["aspect"], 3),
                         "radius_mm": round(d["radius_m"] * MM, 2)}
                        for d in diamonds]
    diag["duplicate_clusters"] = dup
    in_clusters = {i for d in diamonds for i in d["ids"]}
    rest = [b for b in rest if b["id"] not in in_clusters]

    # START / SELECT: off-plane bodies near either seed centre button's
    # seed or mirrored position (|u| from the seed's to h further out)
    R = seed["pool_radius_m"]

    def window(b, rec):
        au = abs(u(b["id"]))
        lo, hi = abs(rec["u_m"]), abs(rec["u_m"]) + max(h, 0.0)
        du = 0.0 if lo <= au <= hi else min(abs(au - lo), abs(au - hi))
        return math.sqrt(du ** 2 + (b["centroid_m"][1] - rec["y_m"]) ** 2
                         + (b["centroid_m"][2] - rec["z_m"]) ** 2)

    cen = seed["centre"]
    pool = [b for b in rest if abs(u(b["id"])) * MM > PLANE_ON_MM
            and min(window(b, cen["select"]), window(b, cen["start"])) <= R]
    roles["select"], roles["start"] = [], []
    if pool:
        cost = [[si_distance(cen[role], b) for b in pool]
                for role in ("select", "start")]
        ri, ci = linear_sum_assignment(cost)
        for r, c in zip(ri, ci):
            roles[("select", "start")[r]] = [pool[c]["id"]]
    used = set(roles["select"]) | set(roles["start"])
    rest = [b for b in rest if b["id"] not in used]
    ps = [b for b in rest if abs(u(b["id"])) * MM <= PLANE_ON_MM
          and window(b, cen["ps"]) <= 2 * R]
    roles["ps"] = [min(ps, key=lambda b: window(b, cen["ps"]))["id"]] \
        if ps else []
    roles["other"] = sorted(b["id"] for b in rest
                            if b["id"] not in roles["ps"])
    diag["start_select_pool"] = [b["id"] for b in pool]
    return roles, diag


# --------------------------------------------------------------------------
# capture: measure a document (the expensive half)
# --------------------------------------------------------------------------

def capture(doc, baseline=None):
    """Every measurement of one open document. Seed mode when `baseline` is
    None (the full ray grid is cast and roles come from structure alone)."""
    rebuild = incremental_census(doc)
    raw, bodies, boxes, gmin, gmax = SC.capture_bodies(doc)
    rebuild["cache_drift"] = cache_drift(rebuild, bodies)
    for b, rb in zip(bodies, raw):
        try:
            b["extent_m"] = body_extent(rb)
        except Exception as exc:                            # noqa: BLE001
            b["extent_m"] = None
            b["extent_error"] = f"{type(exc).__name__}: {exc}"
    hids = housing_ids(bodies)
    hext = union_extent(bodies, hids)
    seed = (baseline or {}).get("seed")
    xsec, plane, roles, rdiag, wmeas = None, None, {}, {}, {}
    if hext:
        keys = seed["xsection"]["keys"] if seed else None
        try:
            xsec = housing_xsection(doc, [raw[int(i[1:])] for i in hids],
                                    hext, keys=keys)
        except Exception as exc:                            # noqa: BLE001
            xsec = {"error": f"{type(exc).__name__}: {exc}"}
        if seed:
            plane, _, wmeas = widening(xsec, hext, seed)
            h = (wmeas["dsep_m"] if wmeas["dsep_m"] is not None
                 else wmeas["dext_m"]) / 2
            roles, rdiag = candidate_roles(bodies, plane, seed, h)
        else:
            plane0 = (hext[0] + hext[3]) / 2
            plane, _ = plane_from_lobes(
                xsec, plane0, seed_lobe_keys(xsec, plane0)) \
                if xsec.get("rays") else (None, {})
            plane = plane if plane is not None else plane0
            roles, rdiag = seed_roles(bodies, plane, hext)
    smf = _small_face_counts(raw)
    lights = None
    if hids and plane is not None:
        hfaces = housing_faces(raw, hids)
        lights = (find_light_cluster_candidate(hfaces, plane,
                                               baseline.get("light_cluster"))
                  if baseline else
                  find_light_cluster_seed(hfaces, plane, gmin + gmax))
    controls = sorted({i for r in CONTROL_ROLES for i in roles.get(r, [])}
                      | {i for g in rdiag.get("duplicate_clusters", [])
                         for i in g})
    intf = control_interference(raw, bodies, controls, hids)
    title = str(z(doc.GetTitle))
    modelling = SC.modelling_census(doc)
    # LAST, because it mutates the geometry everything above has measured.
    rebuild["forced_diagnostic"] = forced_rebuild_diagnostic(doc)
    return {
        "schema": CAPTURE_SCHEMA,
        "harness_version": HARNESS_VERSION,
        "document": title,
        "rebuild": rebuild,
        "modelling": modelling,
        "global": {"bbox_m": gmin + gmax},
        "bodies": bodies,
        "housing_ids": hids,
        "housing_extent_m": hext,
        "xsection": xsec,
        "plane_x_m": plane,
        "capture_roles": roles,
        "capture_role_diag": rdiag,
        "widening_at_capture": wmeas,
        "small_face_counts": smf,
        "light_cluster": lights,
        "interference": intf,
    }


# --------------------------------------------------------------------------
# grading (the cheap half: pure arithmetic over two dictionaries)
# --------------------------------------------------------------------------

def rebuild_delta(rb, baseline):
    """The rebuild census as a delta against the seed's, computed at SCORING
    time: errors and warnings on features the seed census does not already
    flag. A capture from before ps3-capture/4.1 carries the delta already."""
    rb = dict(rb or {})
    if "census" not in rb:
        return rb
    census = rb.get("census") or {}
    hard = {n: c for n, (c, w) in census.items() if not w}
    warn = {n: c for n, (c, w) in census.items() if w}
    seed = ((baseline or {}).get("rebuild") or {}).get("feature_errors") or {}
    seed_hard = {n for n, v in seed.items() if not v[1]}
    newly_broken = [{"name": n, "code": c} for n, c in sorted(hard.items())
                    if n not in seed_hard]
    new_warnings = [{"name": n, "code": c} for n, c in sorted(warn.items())
                    if n not in seed]
    rb.update({
        "ok": not newly_broken,
        "errors": len(newly_broken),
        "warnings": len(warn),
        "broken_features": newly_broken[:25],
        "new_warnings": new_warnings[:25],
        "pre_existing_errors": len(seed_hard),
        "graded": "delta_vs_seed",
    })
    return rb


def ungradable_reason(baseline, measured):
    """Why this candidate cannot be measured at all, or None. Distinct from
    measured-and-wrong: both end at 0, only this one says why."""
    if measured.get("open_error"):
        return f"document could not be opened: {measured['open_error']}"
    if not measured.get("bodies"):
        return "part contains no solid bodies"
    if not housing_ids(measured["bodies"]):
        return "no housing body could be identified"
    if not baseline.get("seed"):
        raise SystemExit("the baseline predates schema "
                         f"{BASELINE_SCHEMA}; re-freeze it with "
                         "--capture-baseline environment\\input.SLDPRT")
    return None


class Grader:
    def __init__(self, baseline, measured):
        self.bl, self.ms = baseline, measured
        self.seed = baseline["seed"]
        self.C = {b["id"]: b for b in measured["bodies"]}
        self.rebuild = rebuild_delta(measured.get("rebuild"), baseline)
        self.notes = []
        self.hids = housing_ids(measured["bodies"])
        self.hext = union_extent(measured["bodies"], self.hids)
        xsec = measured.get("xsection")
        if xsec and xsec.get("error"):
            self.notes.append(f"ray section unavailable: {xsec['error']}")
        self.P, self.lobes, self.wm = widening(xsec, self.hext, self.seed)
        if self.wm["dsep_m"] is not None:
            self.h = self.wm["dsep_m"] / 2
        else:
            self.h = self.wm["dext_m"] / 2
            self.notes.append("grip lobes unreadable: the stance h is taken "
                              "from the body X extent instead")
        self.roles, self.rdiag = candidate_roles(measured["bodies"], self.P,
                                                 self.seed, self.h)

    def u(self, i):
        return self.C[i]["centroid_m"][0] - self.P

    # -- 1 ---------------------------------------------------------------
    def c_width(self):
        t = TOL["width_target_mm"]
        parts = {}
        if self.wm["dsep_m"] is not None:
            parts["grip_separation"] = score_error(
                self.wm["dsep_m"] * MM - t, TOL["width_perfect_mm"],
                TOL["width_zero_mm"])
        if self.wm["dext_m"] is not None:
            parts["body_extent"] = score_error(
                self.wm["dext_m"] * MM - t, TOL["width_perfect_mm"],
                TOL["width_zero_mm"])
        if not parts:
            return {"score": NEUTRAL_UNVERIFIABLE, "status": UNVERIFIABLE,
                    "evidence": "neither the grip lobes nor the body extent "
                                "could be read"}
        base = mean(parts.values())
        if self.wm["dwidth_m"] is not None:
            scale = score_error(self.wm["dwidth_m"] * MM,
                                TOL["scale_perfect_mm"],
                                self.seed["scale_zero_mm"])
        else:
            scale = 1.0
        score = base * factor(scale)

        def fmt(v):
            return None if v is None else round(v * MM, 3)
        return {"score": round(score, 4), "status": status_of(score),
                "components": {**{k: round(v, 4) for k, v in parts.items()},
                               "not_scaled": round(scale, 4)},
                "detail": {"grip_separation_growth_mm": fmt(self.wm["dsep_m"]),
                           "body_extent_growth_mm": fmt(self.wm["dext_m"]),
                           "lobe_width_change_mm": fmt(self.wm["dwidth_m"]),
                           "lobe_rays": self.wm["lobe_rays"],
                           "scale_zero_mm": round(self.seed["scale_zero_mm"],
                                                  3),
                           "plane_source": self.wm["plane_source"]},
                "evidence": f"grip separation "
                            f"{fmt(self.wm['dsep_m'])} mm, body X extent "
                            f"{fmt(self.wm['dext_m'])} mm wider (target "
                            f"+{t:g}); grip lobes changed width by "
                            f"{fmt(self.wm['dwidth_m'])} mm"}

    # -- 2 ---------------------------------------------------------------
    def _interference_growth_mm3(self):
        intf = self.ms.get("interference") or {}
        controls = {i for r in CONTROL_ROLES for i in self.roles.get(r, [])}
        hs = set(self.hids)
        vol = 0.0
        for p in intf.get("pairs", []):
            a, b = p["a"], p["b"]
            if (a in controls and (b in controls or b in hs)) or \
                    (b in controls and a in hs):
                vol += p.get("volume_m3", 0.0)
        seed_v = (self.bl.get("interference") or {}).get("total_volume_m3",
                                                         0.0)
        return max(0.0, vol - seed_v) * 1e9

    def c_space(self):
        h = self.h
        det = {"h_mm": round(h * MM, 3)}
        place, rigid = {}, {}
        for role in ("dpad", "face_buttons"):
            sc = self.seed["clusters"][role]
            ids = self.roles.get(role) or []
            if len(ids) != 4:
                place[role] = 0.0
                det[role] = {"missing": True}
                continue
            uc = mean(self.u(i) for i in ids)
            us = sc["u_m"]
            ue = -us + sgn(-us) * h
            dx = (uc - ue) * MM
            place[role] = score_error(dx, TOL["space_perfect_mm"],
                                      TOL["space_zero_mm"])
            dists = _pair_dists(self.ms["bodies"], ids)
            drift = max(abs(a - b) for a, b in
                        zip(dists, sc["pair_dists_m"])) * MM
            rigid[role] = score_error(drift, TOL["rigid_perfect_mm"],
                                      TOL["rigid_zero_mm"])
            yz = [mean(self.C[i]["centroid_m"][1] for i in ids) - sc["y_m"],
                  mean(self.C[i]["centroid_m"][2] for i in ids) - sc["z_m"]]
            det[role] = {"u_mm": round(uc * MM, 3),
                         "expected_u_mm": round(ue * MM, 3),
                         "dx_mm": round(dx, 3),
                         "spacing_drift_mm": round(drift, 3),
                         "dy_mm_reported": round(yz[0] * MM, 3),
                         "dz_mm_reported": round(yz[1] * MM, 3)}
        base = mean(place.values())
        follow = []
        for role in PAIR_ROLES:
            seed_abs = mean(abs(r["u_m"]) for r in self.seed["kept"][role])
            for i in self.roles.get(role) or []:
                follow.append(score_error(
                    (abs(self.u(i)) - (seed_abs + h)) * MM,
                    TOL["space_perfect_mm"], TOL["space_zero_mm"]))
        f_follow = mean(follow, 1.0)
        f_rigid = mean(rigid.values(), 1.0)
        growth = self._interference_growth_mm3()
        f_fit = score_error(growth, TOL["fit_perfect_mm3"],
                            TOL["fit_zero_mm3"])
        score = base * factor(f_rigid) * factor(f_follow) * factor(f_fit)
        det["followers_scored"] = len(follow)
        det["new_interference_mm3"] = round(growth, 3)
        return {"score": round(score, 4), "status": status_of(score),
                "model": "cluster placement x rigidity x followers x fit",
                "components": {"placement": round(base, 4),
                               "rigidity": round(f_rigid, 4),
                               "followers": round(f_follow, 4),
                               "fit": round(f_fit, 4)},
                "detail": det,
                "evidence": "each button cluster at the mirror of its seed "
                            "position carried outboard by the candidate's own "
                            f"h = {h * MM:.2f} mm; followers, rigidity and "
                            "fit qualify that credit"}

    # -- 3 ---------------------------------------------------------------
    def c_swap(self):
        parts, det = {}, {}
        for role in ("dpad", "face_buttons"):
            sc = self.seed["clusters"][role]
            ids = self.roles.get(role) or []
            if len(ids) != 4:
                parts[role] = 0.0
                det[role] = {"missing": True}
                continue
            uc = mean(self.u(i) for i in ids)
            side = -sgn(sc["u_m"])
            parts[role] = clamp01(0.5 + side * uc / (2 * sc["radius_m"]))
            det[role] = {"u_mm": round(uc * MM, 2),
                         "required_side": "+" if side > 0 else "-",
                         "score": round(parts[role], 4)}
        if self.rdiag.get("duplicate_clusters"):
            det["duplicate_clusters"] = self.rdiag["duplicate_clusters"]
        score = mean(parts.values())
        return {"score": round(score, 4), "status": status_of(score),
                "detail": det,
                "evidence": "each cluster's side of the candidate's own "
                            "plane, ramped over one seed cluster radius; a "
                            "missing cluster (or a copy of the other in its "
                            "place) scores 0"}

    # -- 4 ---------------------------------------------------------------
    def c_stsel(self):
        h = self.h
        parts, det = {}, {}
        for role in ("select", "start"):
            rec = self.seed["centre"][role]
            ids = self.roles.get(role) or []
            if not ids:
                parts[role] = 0.0
                det[role] = {"missing": True}
                continue
            uc = self.u(ids[0])
            us = rec["u_m"]
            lo, hi = sorted((-us, -us + sgn(-us) * h))
            d = 0.0 if lo <= uc <= hi else min(abs(uc - lo), abs(uc - hi))
            parts[role] = score_error(d * MM, TOL["stsel_perfect_mm"],
                                      abs(us) * MM)
            det[role] = {"u_mm": round(uc * MM, 2),
                         "band_mm": [round(lo * MM, 2), round(hi * MM, 2)],
                         "outside_band_mm": round(d * MM, 3),
                         "dy_mm_reported": round(
                             (self.C[ids[0]]["centroid_m"][1] - rec["y_m"])
                             * MM, 3)}
        score = mean(parts.values())
        return {"score": round(score, 4), "status": status_of(score),
                "detail": det,
                "evidence": "START and SELECT buttons at the mirror of their "
                            "seed positions (carried outboard by up to h is "
                            "also mirrored); the text labels join in stage D"}

    # -- 5 (interim) -----------------------------------------------------
    def c_orient(self):
        seed_l = self.bl.get("light_cluster")
        cand_l = self.ms.get("light_cluster")
        if not seed_l or not cand_l:
            return {"score": NEUTRAL_UNVERIFIABLE, "status": UNVERIFIABLE,
                    "evidence": "INTERIM (stage B): the engraved 'R' label "
                                "was not found, so its side cannot be read"}
        same = seed_l["side"] == cand_l["side"]
        s = 1.0 if same else 0.0
        return {"score": s, "status": status_of(s),
                "detail": {"seed_side": seed_l["side"],
                           "candidate_side": cand_l["side"]},
                "evidence": "INTERIM (stage B): v2's witness -- the engraved "
                            "'R' shoulder label stays on its side; stage D "
                            "replaces it with label registration"}

    # -- 6 (interim) -----------------------------------------------------
    def c_kept(self):
        smf_b = self.bl.get("small_face_counts") or {}
        smf_c = self.ms.get("small_face_counts") or {}
        bids = self.seed["roles"]["face_buttons"]
        cids = self.roles.get("face_buttons") or []
        b_total = sum(smf_b.get(i, 0) for i in bids)
        if not b_total:
            return {"score": NEUTRAL_UNVERIFIABLE, "status": UNVERIFIABLE,
                    "evidence": "seed face buttons carry no engraving"}
        if len(cids) != 4:
            return {"score": 0.0, "status": FAIL,
                    "evidence": "INTERIM (stage B): no face-button cluster "
                                "to read the symbols on"}
        c_total = sum(smf_c.get(i, 0) for i in cids)
        retained = c_total / float(b_total)
        s = clamp01(retained / MARKINGS_FULL_FRACTION)
        return {"score": round(s, 4), "status": status_of(s),
                "detail": {"seed_engraved_faces": b_total,
                           "candidate_engraved_faces": c_total},
                "evidence": f"INTERIM (stage B): {c_total} of the seed's "
                            f"{b_total} engraving-scale faces on the face "
                            f"buttons ({retained:.0%})"}

    # -- 7 ---------------------------------------------------------------
    def c_unreq(self):
        parts, det = {}, {}
        worst_fp, worst_drift, missing = 0.0, 0.0, []
        for role in KEPT_ROLES:
            recs = sorted(self.seed["kept"][role], key=lambda r: r["u_m"])
            ids = sorted(self.roles.get(role) or [], key=self.u)
            if len(ids) < len(recs):
                missing.append(role)
            for i, rec in zip(ids, recs):
                b = self.C[i]
                worst_fp = max(worst_fp, fp_distance(rec, b))
                dr = [abs(b["centroid_m"][1] - rec["centroid_m"][1]),
                      abs(b["centroid_m"][2] - rec["centroid_m"][2])]
                if role == "plane_small":
                    dr.append(abs(self.u(i) - rec["u_m"]))
                worst_drift = max(worst_drift, max(dr) * MM)
        parts["kept_shapes"] = 0.0 if missing else score_error(
            worst_fp, TOL["fp_perfect"], TOL["fp_zero"])
        parts["kept_positions"] = 0.0 if missing else score_error(
            worst_drift, TOL["drift_perfect_mm"], TOL["drift_zero_mm"])
        sh = self.seed["housing_extent_m"]
        span = max(abs((self.hext[4] - self.hext[1]) - (sh[4] - sh[1])),
                   abs((self.hext[5] - self.hext[2]) - (sh[5] - sh[2]))) * MM
        parts["housing_yz_spans"] = score_error(span, TOL["span_perfect_mm"],
                                                TOL["span_zero_mm"])
        det.update({"worst_fingerprint_distance": round(worst_fp, 5),
                    "worst_yz_drift_mm": round(worst_drift, 3),
                    "missing_kept_roles": missing,
                    "housing_span_change_mm": round(span, 3),
                    "unassigned_bodies_reported": self.roles.get("other"),
                    "housing_bodies": len(self.hids)})
        score = min(parts.values())
        return {"score": round(score, 4), "status": status_of(score),
                "components": {k: round(v, 4) for k, v in parts.items()},
                "detail": det,
                "evidence": "the weaker part decides: bodies the edit leaves "
                            "alone keep shape and y/z, housing keeps its Y/Z "
                            "spans. Added hardware is reported, not scored. "
                            "Housing surface comparison arrives in stage E"}

    # -- 8 (interim) -----------------------------------------------------
    def c_rebuild(self):
        rb = self.rebuild
        n_feat = rb.get("features") or 0
        broken = rb.get("errors")
        if broken is None:
            return {"score": NEUTRAL_UNVERIFIABLE, "status": UNVERIFIABLE,
                    "evidence": "no rebuild census available"}
        frac = (broken / n_feat) if n_feat else (1.0 if broken else 0.0)
        s = score_error(frac, TOL["health_perfect_frac"],
                        TOL["health_zero_frac"])
        return {"score": round(s, 4), "status": status_of(s),
                "detail": {"newly_broken": broken, "features": n_feat,
                           "broken_features": rb.get("broken_features",
                                                     [])[:10]},
                "evidence": "INTERIM (stage B): fraction of features newly "
                            "broken after EditRebuild3 vs the seed census"}

    def hygiene_report(self):
        """Report only (decision: tree structure is not graded)."""
        bm, cm = self.bl.get("modelling") or {}, self.ms.get("modelling") or {}

        def n(d, *path):
            for k in path:
                d = (d or {}).get(k)
            return d
        return {"scored": False,
                "sketch_status_counts": {
                    "seed": n(bm, "sketches", "status_counts"),
                    "candidate": n(cm, "sketches", "status_counts")},
                "suppressed": {"seed": n(bm, "suppressed", "count"),
                               "candidate": n(cm, "suppressed", "count")},
                "new_warnings": len(self.rebuild.get("new_warnings") or [])}

    def grade(self):
        report = {"document": self.ms.get("document"),
                  "rebuild": self.rebuild,
                  "plane_x_m": self.P,
                  "plane_offset_vs_seed_mm": round(
                      (self.P - self.seed["plane_x_m"]) * MM, 3),
                  "roles": self.roles,
                  "role_diag": self.rdiag,
                  "widening": self.wm,
                  "criteria": {}, "notes": list(self.notes)}
        report["criteria"][C_WIDTH] = self.c_width()
        report["criteria"][C_SPACE] = self.c_space()
        report["criteria"][C_SWAP] = self.c_swap()
        report["criteria"][C_STSEL] = self.c_stsel()
        report["criteria"][C_ORIENT] = self.c_orient()
        report["criteria"][C_KEPT] = self.c_kept()
        report["criteria"][C_UNREQ] = self.c_unreq()
        report["criteria"][C_REBUILD] = self.c_rebuild()
        report["hygiene"] = self.hygiene_report()
        fd = self.rebuild.get("forced_diagnostic")
        if fd:
            last = (fd.get("passes") or [{}])[-1]
            report["notes"].append(
                f"unscored diagnostic: under forced full rebuilds "
                f"({len(fd.get('passes') or [])} pass(es), "
                f"{'stable' if fd.get('stable') else 'NOT stable'}) "
                f"{last.get('hard')} feature(s) fail and "
                f"{last.get('warnings')} warn")
        if not self.rebuild.get("ok", True):
            report["notes"].append(
                f"{self.rebuild.get('errors')} newly broken feature(s) after "
                "EditRebuild3; geometry graded as rebuilt, the fault is "
                "charged to rebuild health only")
        report["weighted_score"] = round(sum(
            report["criteria"][k]["score"] * w
            for k, w in ALL_CRITERIA.items()), 4)
        st = [v["score"] for v in report["criteria"].values()]
        report["overall"] = (PASS if all(s >= 1.0 for s in st) else
                             FAIL if all(s <= 0.0 for s in st) else PARTIAL)
        return report


def summarise(report, weights=None):
    weights = weights or ALL_CRITERIA
    rb = report.get("rebuild") or {}
    out = [f"document : {report.get('document')}",
           f"rebuild  : newly broken={rb.get('errors')}  "
           f"plane offset vs seed={report.get('plane_offset_vs_seed_mm')} mm",
           ""]
    for k, v in report["criteria"].items():
        out.append(f"  {k:34} {v['score']:.3f}  {v['status']:<12} "
                   f"(w={weights.get(k, 0):g})")
        for cname, cval in (v.get("components") or {}).items():
            out.append(f"        . {cname:28} {cval:.3f}")
        if v.get("evidence"):
            out.append(f"        - {v['evidence'][:150]}")
    for n in report.get("notes", []):
        out.append(f"  note: {n}")
    out += ["", f"  WEIGHTED SCORE   {report.get('weighted_score', 0.0):.3f}"
                f" / {sum(ALL_CRITERIA.values()):g}   ({report['overall']})"]
    return "\n".join(out)


def annotate_envelope(envelope, report):
    """Attach the report-level facts a pipeline must see without opening the
    full report."""
    if not report:
        return envelope
    if report.get("ungradable"):
        envelope["ungradable"] = report["ungradable"]
    return envelope


# --------------------------------------------------------------------------
# measure / score / grade
# --------------------------------------------------------------------------

def open_fresh(app, path=None):
    """The part at `path` loaded FROM DISK, or the active document.

    solidworks_session.open_document reuses a document already open under
    the same path, and a rebuild is a mutation: a document left open by an
    earlier run was measured in whatever state that run left it in (observed
    in this repo). Sweeping first makes every measurement start from the
    saved file. No path = the user's active document, never closed.
    """
    if path:
        SW.close_all_documents(app)
    return SC.open_or_active(app, path)


def measure_candidate(path=None, close_after=False, baseline=None):
    """Open a part and take every measurement. A part SolidWorks refuses to
    open yields a capture marked `open_error`, never a traceback."""
    baseline = baseline if baseline is not None else load_baseline()
    app = SC.attach_app()
    try:
        doc = open_fresh(app, path)
    except Exception as exc:                                # noqa: BLE001
        return {"schema": CAPTURE_SCHEMA, "harness_version": HARNESS_VERSION,
                "document": Path(path).name if path else None,
                "source_path": os.path.abspath(path) if path else None,
                "open_error": f"{type(exc).__name__}: {exc}",
                "bodies": []}
    measured = capture(doc, baseline=baseline)
    measured["source_path"] = os.path.abspath(path) if path else None
    if close_after and path:
        try:
            SW.close_all_documents(app)
        except Exception:                                   # noqa: BLE001
            pass
    for line in SW.session_report():
        print(f"  ! {line}", file=sys.stderr)
    return measured


def score_capture(measured, baseline=None, weights=None, quiet=False):
    """Grade a capture dict. No SolidWorks involved."""
    baseline = baseline if baseline is not None else load_baseline()
    schema = measured.get("schema")
    hard = ungradable_reason(baseline, measured)
    if hard:
        report = {"document": measured.get("document"),
                  "rebuild": measured.get("rebuild", {}),
                  "criteria": {k: {"score": 0.0, "status": FAIL,
                                   "evidence": "not evaluated -- candidate "
                                               "is ungradable"}
                               for k in ALL_CRITERIA},
                  "ungradable": {"reason": hard,
                                 "bodies": len(measured.get("bodies", []))},
                  "weighted_score": 0.0, "overall": FAIL,
                  "notes": [f"UNGRADABLE: {hard}"]}
    else:
        report = Grader(baseline, measured).grade()
    if schema and schema != CAPTURE_SCHEMA:
        report.setdefault("notes", []).append(
            f"capture schema {schema} differs from this harness's "
            f"{CAPTURE_SCHEMA}; measurements it lacks read as unavailable")
    if not quiet:
        print(summarise(report, weights), file=sys.stderr)
    return report


def grade_candidate(path=None, close_after=False, weights=None):
    """Measure and score in one pass -- the default single-part flow. Keeps
    the capture when the batch runner asks for it (HARNESS_CAPTURE_JSON)."""
    baseline = load_baseline()
    measured = measure_candidate(path, close_after=close_after,
                                 baseline=baseline)
    write_env("HARNESS_CAPTURE_JSON",
              json.dumps(measured, indent=1, default=str))
    return score_capture(measured, baseline=baseline, weights=weights)


class PS3Harness(Harness):
    MUST_PASS = ()             # no score-zeroing gates
    CANDIDATE_OPTIONAL = True  # without an arg, grades the live document
    WEIGHTS = ALL_CRITERIA

    def main(self):
        from common import harness_base as _HB
        if _HB.is_run_request():
            _HB.runner_main(*sys.argv[2:6], fmt=self.RUNNER_FMT)
            raise SystemExit(0)
        candidate = (None if (self.CANDIDATE_OPTIONAL and len(sys.argv) == 1)
                     else _HB.candidate_from_argv())
        self.timeout = _HB.timeout_from_argv(self.BUILD_TIMEOUT_S)
        state = self.build_state(candidate)
        env = finalize(self.task_dir(), self.checks(state),
                       version=HARNESS_VERSION,
                       must_pass=self.MUST_PASS, weights=self.WEIGHTS)
        return annotate_envelope(env, getattr(self, "report", None))

    def build_state(self, candidate_path):
        return candidate_path

    def checks(self, state):
        report = grade_candidate(state, close_after=bool(state),
                                 weights=self.WEIGHTS)
        self.report = report
        dump = os.environ.get("HARNESS_REPORT_JSON")
        if dump:
            try:
                p = Path(dump)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(report, indent=1, default=str),
                             encoding="utf-8")
            except Exception as exc:                        # noqa: BLE001
                print(f"[warn] could not write {dump}: {exc}",
                      file=sys.stderr)
        return {c: (c, clamp01(v.get("score", 0.0)), v.get("evidence", ""))
                for c, v in report["criteria"].items()}


main = PS3Harness.as_main()


# --------------------------------------------------------------------------
# baseline
# --------------------------------------------------------------------------

BASELINE_REQUIRED_KEYS = ("bodies", "seed", "plane_x_m", "xsection",
                          "modelling", "rebuild")
BASELINE = HB.Baseline(BASELINE_PATH, BASELINE_SCHEMA,
                       BASELINE_REQUIRED_KEYS)


def load_baseline():
    return BASELINE.load()


def capture_baseline(path, out_path=None):
    """Re-freeze prompt/input.json from the unmodified seed part."""
    out_path = Path(out_path) if out_path else BASELINE_PATH
    app = SC.attach_app()
    doc = open_fresh(app, path)
    cap = capture(doc, baseline=None)
    seed = derive_seed(cap)
    census = cap["rebuild"]["census"]
    hard = {n: c for n, (c, w) in census.items() if not w}
    warn = {n: c for n, (c, w) in census.items() if w}
    baseline = {
        "schema": BASELINE_SCHEMA,
        "row": "widen 15mm + left-handed layout (PS3 controller)",
        "seed_document": cap["document"],
        "units": "ALL lengths in metres, volumes m^3 -- SolidWorks API units",
        "plane_x_m": seed["plane_x_m"],
        "seed": seed,
        "modelling": cap["modelling"],
        "bodies": cap["bodies"],
        "housing_ids": cap["housing_ids"],
        "xsection": cap["xsection"],
        "small_face_counts": cap["small_face_counts"],
        "light_cluster": cap["light_cluster"],
        "interference": {k: cap["interference"][k] for k in
                         ("tested_pairs", "pairs", "total_volume_m3")},
        "rebuild": {
            "captured_from": cap["document"],
            "mode": "incremental",
            "features": cap["rebuild"]["features"],
            "errors": len(hard),
            "warnings": len(warn),
            "feature_errors": census,
            "forced_diagnostic": cap["rebuild"]["forced_diagnostic"],
            "note": "per-feature error census of the unmodified seed after "
                    "EditRebuild3; candidates are graded as a delta vs this. "
                    "forced_diagnostic is unscored.",
        },
    }
    BASELINE.freeze(baseline, out_path, dump=lambda r: json.dumps(r, indent=1))
    if path:
        SW.close_all_documents(app)
    r = seed["roles"]
    print(f"  plane {seed['plane_x_m'] * MM:.3f} mm; roles "
          f"{ {k: len(v) for k, v in r.items()} }; grip rays "
          f"{seed['xsection']['two_lobe_rays']} (sparse "
          f"{len(seed['xsection']['keys'])}); congruent_tol "
          f"{seed['congruent_tol']:.4f}; aspect threshold "
          f"{seed['aspect_threshold']:.3f}", file=sys.stderr)
    return baseline


def capture_seed_rebuild(path=None, out_path=None):
    """Refresh only the rebuild census inside an existing baseline."""
    out_path = Path(out_path) if out_path else BASELINE_PATH
    baseline = json.loads(out_path.read_text(encoding="utf-8"))
    app = SC.attach_app()
    doc = open_fresh(app, path)
    inc = incremental_census(doc)
    census = inc["census"]
    hard = {n: c for n, (c, w) in census.items() if not w}
    warn = {n: c for n, (c, w) in census.items() if w}
    title = str(z(doc.GetTitle))
    forced = forced_rebuild_diagnostic(doc)
    baseline["rebuild"] = {
        "captured_from": title, "mode": "incremental",
        "features": inc["features"], "errors": len(hard),
        "warnings": len(warn), "feature_errors": census,
        "forced_diagnostic": forced,
        "note": "per-feature error census of the unmodified seed after "
                "EditRebuild3; candidates are graded as a delta vs this. "
                "forced_diagnostic is unscored.",
    }
    out_path.write_text(json.dumps(baseline, indent=1), encoding="utf-8")
    if path:
        SW.close_all_documents(app)
    print(f"refreshed rebuild census in {out_path} ({inc['features']} "
          f"features, {len(hard)} hard errors)", file=sys.stderr)
    return baseline


# --------------------------------------------------------------------------
# batch mode and CLI -- the runner itself is common/harness_cli.py
# --------------------------------------------------------------------------

# Seed (the do-nothing control) and reference first, then the examples in the
# order task.toml declares them. Anything not named here still runs.
BATCH_ORDER = [
    "input",
    "solution",
    "adversarial_feature_tree_with_errors",
    "adversarial_missing_glyphs",
    "adversarial_only_one_button_cluster_mirrored",
    "adversarial_text_mirrored_incorrectly",
    "adversarial_unrequested_change_elsewhere",
    "adversarial_unwidened_shell_with_correct_clusters",
    "adversarial_widened_15mm_clusters_at_original_spacing",
    "adversarial_widened_by_30mm",
]

SHORT = {C_WIDTH: "width", C_SPACE: "space", C_SWAP: "swap",
         C_STSEL: "st/sel", C_ORIENT: "orient", C_KEPT: "logos",
         C_UNREQ: "unreq", C_REBUILD: "rebld"}


def discover_models(task_dir):
    """{label: path} for a task directory laid out like the shipped one; a
    recursive glob for any other directory."""
    task_dir = Path(task_dir)
    found = {}
    ref = task_dir / "solution" / "solution.SLDPRT"
    if ref.is_file():
        found["solution"] = ref
    ex = task_dir / "examples"
    if ex.is_dir():
        # One candidate per FOLDER: examples/<name>/<name>.SLDPRT (v2.3.1
        # globbed examples/*.SLDPRT and found none). The corpus is what
        # task.toml declares; an undeclared folder is parked, not graded.
        declared = HB.declared_examples(task_dir / "task.toml")
        for d in sorted(q for q in ex.iterdir() if q.is_dir()):
            if declared is not None and d.name not in declared:
                print(f"[skip] examples/{d.name} -- not declared in "
                      f"task.toml [metadata.examples]", file=sys.stderr)
                continue
            p = HC.named_model(d, d.name, glob="*.SLDPRT")
            if p is not None:
                found[d.name] = p
    seed = task_dir / "environment" / "input.SLDPRT"
    if seed.is_file():
        found["input"] = seed
    if not found:
        for p in sorted(task_dir.rglob("*.SLDPRT")):
            label, n = p.stem, 2
            while label in found:
                label, n = f"{p.stem}_{n}", n + 1
            found[label] = p
    ordered = {k: found[k] for k in BATCH_ORDER if k in found}
    for k, v in found.items():
        ordered.setdefault(k, v)
    return ordered


DEFAULT_TASK_DIR = HERE.parents[2]
DEFAULT_CAPTURE_DIR = DEFAULT_TASK_DIR / "results" / "captures"


def envelope_from(report, weights=None):
    """report -> the graded envelope. Same contract as every other task."""
    weights = weights if weights is not None else PS3Harness.WEIGHTS
    checks = {n: (n, clamp01(c.get("score", 0.0)), c.get("evidence", ""))
              for n, c in report["criteria"].items()}
    env = finalize(PS3Harness.task_dir(), checks, version=HARNESS_VERSION,
                   must_pass=PS3Harness.MUST_PASS, weights=weights)
    return annotate_envelope(env, report)


def _score_stored(path):
    # quiet: harness_cli prints the summary itself after scoring
    measured = json.loads(Path(path).read_text(encoding="utf-8"))
    return score_capture(measured, weights=PS3Harness.WEIGHTS, quiet=True)


def _capture_note(cap):
    xs = cap.get("xsection") or {}
    return (f"{len(cap.get('bodies') or [])} bodies, "
            f"{xs.get('n_rays', 0)} rays in {xs.get('seconds', 0)}s")


SPEC = HC.Spec(
    harness_file=__file__,
    version=HARNESS_VERSION,
    capture_schema=CAPTURE_SCHEMA,
    baseline_schema=BASELINE_SCHEMA,
    criteria=ALL_CRITERIA,
    short=SHORT,
    order=BATCH_ORDER,
    discover=discover_models,
    default_task_dir=DEFAULT_TASK_DIR,
    default_capture_dir=DEFAULT_CAPTURE_DIR,
    model_glob="*.SLDPRT",
    model_noun=("part", "parts"),
    model_width=52,
    measure=lambda path: measure_candidate(path, close_after=bool(path)),
    dump=lambda cap: json.dumps(cap, indent=1, default=str),
    capture_note=_capture_note,
    score=_score_stored,
    summarise=lambda report: summarise(report, PS3Harness.WEIGHTS),
    envelope=envelope_from,
    capture_baseline=capture_baseline,
    extra_modes={"--capture-seed-rebuild":
                 lambda argv: capture_seed_rebuild(
                     argv[0] if argv else None,
                     argv[1] if len(argv) > 1 else None)},
    extra_usage="  harness.py --capture-seed-rebuild SEED.SLDPRT [out.json]\n",
    harness_cli=PS3Harness.cli,
)


def cli(argv=None):
    HC.cli(SPEC, argv)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:                                       # noqa: BLE001
        pass
    cli()
