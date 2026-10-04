#!/usr/bin/env python3
"""
Task 1 (SolidWorks) -- PS3 controller: widen 15 mm + left-handed layout.

Grades a candidate .SLDPRT against tests/task/prompt/input.json, the frozen
measurements of the seed part. GEOMETRY ONLY: mass properties, exact extreme
points, ray sections, tessellated engraving faces and housing height maps --
never feature or body names, and never body order (IPartDoc::GetBodies2 "may
vary the order in which bodies are returned"). A candidate who solves the
task a different valid way scores the same as the reference.
What changed from 2.3.1 and why: CHANGES.md in the task directory.

RUBRIC -- weights live in ALL_CRITERIA, each next to the clause it comes from
  1  widened 15 mm at the grips        2.0   grip-lobe separation growth and
                                             body X extent; x not-scaled check
  2  clusters re-spaced to the stance  2.0   cluster x vs mirror + h; times
                                             rigidity, followers (sticks,
                                             triggers, bumpers) and fit (no
                                             new interference)
  3  d-pad and face buttons swapped    2.0   side of each cluster (continuous)
  4  START/SELECT mirrored             1.0   START/SELECT buttons and text at
                                             mirrored positions
  5  text and logos oriented           1.0   every chiral label registered as
                                             moved / mirrored / upside down;
                                             symbol arrangement; START pointer
  6  text and logos preserved          1.0   share of each seed label's
                                             engraved area found again
  7  no unrequested changes            0.5   shape/position of the bodies the
                                             edit leaves alone, housing Y/Z
                                             spans, housing top surface
                                             outside the edit zones
  8  rebuilds cleanly                  0.5   new failing features, sketches in
                                             an error state, new warnings

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
Offline tests (no SolidWorks), from the task directory:
    python -m unittest discover -s tests/task/harness -v
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
                                 score_error, score_ratio, write_env)

BASELINE_PATH = TASK_DIR / "prompt" / "input.json"

PASS, PARTIAL, FAIL, UNVERIFIABLE = "PASS", "PARTIAL", "FAIL", "UNVERIFIABLE"

HARNESS_VERSION = "3.0.0"
#: /7: v2's small-face counts and "light cluster" dropped (criteria 5 and 6
#: read the engraving faces instead). /6 added the engraving-scale faces of
#: every body (area, tessellated centroid, normal), the housing's height
#: maps and each body's X-skew; /5 exact extreme points, the +X ray section
#: of the housing, the raw EditRebuild3 census and the unscored
#: forced-rebuild diagnostic.
CAPTURE_SCHEMA = "ps3-capture/7"
#: /6: the same two v2 fields dropped. /5 added the seed's engraving faces,
#: height maps and skews; /4 its structural roles, cluster geometry,
#: grip-lobe rays and the thresholds derived from them (see derive_seed).
BASELINE_SCHEMA = "ps-annotation-baseline/6"

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
    # -- 7 unrequested ----------------------------------------------------
    # (the housing-surface threshold and area are read off the seed: see
    # seed_map_scales)
    "fp_perfect": 0.01,          # unchanged B-rep mass props repeat to ~1e-5;
                                 # 1 % is the smallest deliberate resize
    "fp_zero": 0.08,
    "drift_perfect_mm": 0.5,     # the instruction moves nothing in y or z
    "drift_zero_mm": 5.0,        # a third of the requested change
    "span_perfect_mm": 0.5,      # housing Y/Z spans: X only is asked for
    "span_zero_mm": 5.0,
    # -- 8 rebuild ---------------------------------------------------------
    # Counted, name-free: new hard errors + sketches in an error state +
    # half of each new warning. The seed rebuilds with none, so every one is
    # introduced by the edit; zero at 5 % of the seed's 199 features (~10)
    # -- a tree with that many broken references is "riddled".
    "rebuild_zero_frac": 0.05,
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
#: Engraving-scale faces: the 15 mm2 ceiling v2 used. The largest single
#: face of an engraved letter on the seed is below it; structural faces of
#: the housing are far above.
GLYPH_FACE_MAX_AREA = 15e-6
#: Height maps of the housing: 1 mm cells. The seed's lettering strokes are
#: about 1 mm wide, and any cut worth calling a feature is wider than that.
MAP_STEP_M = 0.001

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


def _enc(arr):
    """float32 -> zlib -> base64: a height map in a JSON capture."""
    import base64
    import zlib
    import numpy as np
    return base64.b64encode(zlib.compress(
        np.asarray(arr, np.float32).tobytes(), 6)).decode("ascii")


def _dec(s, shape):
    import base64
    import zlib
    import numpy as np
    return np.frombuffer(zlib.decompress(base64.b64decode(s)),
                         np.float32).reshape(shape).astype(np.float64)


def _face_tris(face):
    """IFace2::GetTessTriangles(NoConversion=True): x, y, z (m) of three
    vertices per triangle; None when the face has no tessellation."""
    import numpy as np
    try:
        t = face.GetTessTriangles(True)
    except Exception:                                       # noqa: BLE001
        return None
    if not t:
        return None
    a = np.asarray(t, dtype=np.float64)
    if a.size < 9 or a.size % 9:
        return None
    return a.reshape(-1, 3, 3)


def _tri_area_centroid(tris):
    import numpy as np
    e1 = tris[:, 1] - tris[:, 0]
    e2 = tris[:, 2] - tris[:, 0]
    ar = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    tot = float(ar.sum())
    if tot <= 0:
        return None, 0.0
    return (tris.mean(1) * ar[:, None]).sum(0) / tot, tot


def _face_normal(face):
    """IFace2::Normal: unit normal of a PLANAR face, (0, 0, 0) otherwise."""
    try:
        n = [float(v) for v in z(face.Normal)]
        return n if any(abs(v) > 1e-9 for v in n) else None
    except Exception:                                       # noqa: BLE001
        return None


def body_faces(body, glyphs=True, tess=True):
    """(glyph faces, triangles) of one body. A glyph face is [area, cx, cy,
    cz, nx, ny, nz] (m2, m), centroid from the face's own tessellation (box
    centre as fallback), normal zeros when the face is not planar."""
    import numpy as np
    out, tris_all = [], []
    for f in (z(body.GetFaces) or []):
        try:
            area = float(z(f.GetArea))
        except Exception:                                   # noqa: BLE001
            continue
        small = glyphs and area < GLYPH_FACE_MAX_AREA
        tris = _face_tris(f) if (tess or small) else None
        if tess and tris is not None:
            tris_all.append(tris)
        if small:
            c = _tri_area_centroid(tris)[0] if tris is not None else None
            if c is None:
                try:
                    box = z(f.GetBox)
                    c = [(float(box[k]) + float(box[k + 3])) / 2
                         for k in range(3)]
                except Exception:                           # noqa: BLE001
                    continue
            out.append([area] + [float(v) for v in c]
                       + (_face_normal(f) or [0.0, 0.0, 0.0]))
    return out, (np.concatenate(tris_all) if tris_all else None)


def surface_skew_x(tris):
    """Area-weighted standardised third moment of a body's surface along X.
    It flips sign under an X-mirror and ignores translation: a pointer-shaped
    START button reads clearly non-zero, a symmetric button ~0."""
    import numpy as np
    if tris is None or not len(tris):
        return None
    e1 = tris[:, 1] - tris[:, 0]
    e2 = tris[:, 2] - tris[:, 0]
    ar = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    if ar.sum() <= 0:
        return None
    w = ar / ar.sum()
    x = tris[:, :, 0].mean(1)
    m = (w * x).sum()
    m2 = (w * (x - m) ** 2).sum()
    m3 = (w * (x - m) ** 3).sum()
    return float(m3 / m2 ** 1.5) if m2 > 0 else 0.0


def raster(tris, axes, hax, origin, step, shape, mode="max", batch=400000):
    """Per grid cell, the max (or min) of coordinate `hax` over the triangles
    covering the cell centre; NaN where none does. tris (N, 3, 3); `axes`
    the two coordinates spanning the grid; cell (i, k) centre = origin +
    (i + .5, k + .5) * step. Vectorised: each triangle is expanded into the
    cells of its bounding box, tested barycentrically, max/min-accumulated."""
    import numpy as np
    ni, nk = shape
    out = np.full(ni * nk, -np.inf if mode == "max" else np.inf)
    P = tris[:, :, list(axes)].astype(np.float64)
    H = tris[:, :, hax].astype(np.float64)
    A = P[:, 0]
    v0, v1 = P[:, 2] - A, P[:, 1] - A
    d00 = (v0 * v0).sum(1)
    d01 = (v0 * v1).sum(1)
    d11 = (v1 * v1).sum(1)
    den = d00 * d11 - d01 * d01
    keep = np.abs(den) > 1e-24
    lo, hi = P.min(1), P.max(1)
    i0 = np.clip(np.ceil((lo[:, 0] - origin[0]) / step - 0.5),
                 0, ni - 1).astype(np.int64)
    i1 = np.clip(np.floor((hi[:, 0] - origin[0]) / step - 0.5),
                 -1, ni - 1).astype(np.int64)
    k0 = np.clip(np.ceil((lo[:, 1] - origin[1]) / step - 0.5),
                 0, nk - 1).astype(np.int64)
    k1 = np.clip(np.floor((hi[:, 1] - origin[1]) / step - 0.5),
                 -1, nk - 1).astype(np.int64)
    keep &= (i1 >= i0) & (k1 >= k0)
    idx = np.nonzero(keep)[0]
    cnt = ((i1 - i0 + 1) * (k1 - k0 + 1))[idx]
    start = 0
    while start < len(idx):
        csum = np.cumsum(cnt[start:])
        stop = start + max(1, int(np.searchsorted(csum, batch)))
        t, c = idx[start:stop], cnt[start:stop]
        rep = np.repeat(t, c)
        j = np.arange(len(rep)) - np.repeat(np.cumsum(c) - c, c)
        w = (i1 - i0 + 1)[rep]
        ii = i0[rep] + j % w
        kk = k0[rep] + j // w
        v2x = origin[0] + (ii + 0.5) * step - A[rep, 0]
        v2k = origin[1] + (kk + 0.5) * step - A[rep, 1]
        d20 = v2x * v0[rep, 0] + v2k * v0[rep, 1]
        d21 = v2x * v1[rep, 0] + v2k * v1[rep, 1]
        dd = den[rep]
        u = (d11[rep] * d20 - d01[rep] * d21) / dd
        v = (d00[rep] * d21 - d01[rep] * d20) / dd
        inside = (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)
        hval = H[rep, 0] + u * (H[rep, 2] - H[rep, 0]) + v * (H[rep, 1]
                                                             - H[rep, 0])
        flat = (ii * nk + kk)[inside]
        if mode == "max":
            np.maximum.at(out, flat, hval[inside])
        else:
            np.minimum.at(out, flat, hval[inside])
        start = stop
    out[~np.isfinite(out)] = np.nan
    return out.reshape(ni, nk)


def housing_maps(tris, hext, step=None):
    """Height maps of the housing's own tessellation, anchored at its own
    extent minimum: top (max y) / bottom (min y) over X-Z, front (max z) /
    back (min z) over X-Y; NaN where there is no housing."""
    step = step or MAP_STEP_M
    x0, y0, z0 = hext[0], hext[1], hext[2]
    nx = int(math.ceil((hext[3] - x0) / step))
    ny = int(math.ceil((hext[4] - y0) / step))
    nz = int(math.ceil((hext[5] - z0) / step))
    maps = {
        "top": raster(tris, (0, 2), 1, (x0, z0), step, (nx, nz), "max"),
        "bottom": raster(tris, (0, 2), 1, (x0, z0), step, (nx, nz), "min"),
        "front": raster(tris, (0, 1), 2, (x0, y0), step, (nx, ny), "max"),
        "back": raster(tris, (0, 1), 2, (x0, y0), step, (nx, ny), "min"),
    }
    return {"step_m": step, "origin_m": [x0, y0, z0],
            "shape_xz": [nx, nz], "shape_xy": [nx, ny],
            "triangles": int(len(tris)),
            **{k: _enc(v) for k, v in maps.items()}}


def capture_surfaces(raw, bodies, hids, hext):
    """Glyph faces of every body, the housing's height maps and each
    non-housing body's X-skew. Role-free on purpose: scoring decides which
    bodies matter, so a role rule changed later still finds its data."""
    import numpy as np
    t0 = time.time()
    glyphs, skew, htris = {}, {}, []
    for b, rb in zip(bodies, raw):
        is_h = b["id"] in hids
        try:
            g, tris = body_faces(rb, glyphs=True, tess=True)
        except Exception:                                   # noqa: BLE001
            g, tris = [], None
        glyphs[b["id"]] = g
        if is_h:
            if tris is not None:
                htris.append(tris)
        else:
            skew[b["id"]] = surface_skew_x(tris)
    maps = None
    if htris and hext:
        maps = housing_maps(np.concatenate(htris), hext)
    return {"glyph_faces": glyphs, "body_skew_x": skew, "housing_maps": maps,
            "surfaces_seconds": round(time.time() - t0, 2)}


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
        cos = (abs(off[a][0] * off[c][0] + off[a][1] * off[c][1])
               / (r[a] * r[c]))
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


# --------------------------------------------------------------------------
# text and logos: where (and which way round) does a seed engraving reappear?
# --------------------------------------------------------------------------

#: POSITION carries a face's identity; area only rules out a different
#: feature at the same spot. Measured: the seed's own "R" regenerated in a
#: seed-derived part keeps every face within 0.06 mm but re-trims its areas
#: (largest face -2.5 %, slivers up to 6x), and IFace2::GetArea is documented
#: as approximate. So a seed face matches the nearest candidate face within
#: GLYPH_POS_TOL_M whose area is within a factor GLYPH_AREA_RATIO, credited
#: with the smaller of the two areas; placements are proposed by faces within
#: GLYPH_ANCHOR_TOL in area.
GLYPH_AREA_RATIO = 2.0
GLYPH_ANCHOR_TOL = 0.25
#: Tessellation centroids reproduce to ~1e-3 mm; 0.3 mm admits a re-trimmed
#: face and stays far below the 3.2 mm letter pitch of the seed's text.
GLYPH_POS_TOL_M = 0.0003
#: Engravings closer than this belong to one label. Measured on the seed:
#: letters of START / SELECT sit 3.2-4.4 mm apart, the nearest other
#: engraving is >= 9 mm from any label.
LABEL_LINK_M = 0.0045
#: A label is present when 90 % of its engraved area is found (a re-split
#: of the same engraving still reaches that), absent below a quarter.
PRESENCE_FULL, PRESENCE_ZERO = 0.90, 0.25
#: A label that matches its own reflection this well has no handedness to
#: read; it is excluded from the orientation check and reported.
ACHIRAL_SELF = 0.75
#: Surface X-skew below this is noise: the seed's mirror-symmetric buttons
#: read |skew| <= 0.062 (their engraved symbols), its START pointer 0.252.
SKEW_MIN = 0.10
HYPOTHESES = ("T", "R", "Rot")


def label_frame(F):
    """Area-weighted centroid and unit normal of a label: the normal is the
    smallest-variance axis of the face centroids, turned to the +Y side."""
    import numpy as np
    a, P = F[:, 0], F[:, 1:4]
    c = (P * a[:, None]).sum(0) / a.sum()
    X = (P - c) * np.sqrt(a)[:, None]
    n = np.linalg.eigh(X.T @ X)[1][:, 0]
    return c, (n if n[1] >= 0 else -n)


def _hyp(rel, hyp, n):
    import numpy as np
    if hyp == "T":                 # moved, read the same way round
        return rel
    if hyp == "R":                 # what a naive X-mirror does
        out = rel.copy()
        out[:, 0] = -out[:, 0]
        return out
    return 2.0 * np.outer(rel @ n, n) - rel   # "Rot": upside down in-plane


def register(seed, cand, anchors=3):
    """{hyp: {"fraction", "centroid_m", "matched"}}: the largest share of a
    seed label's engraved AREA found among `cand` faces under each
    hypothesis, and where its centroid lands. Each candidate face of
    matching area proposes a placement for one of the label's largest faces;
    the placement explaining the most area wins."""
    import numpy as np
    seed, cand = np.asarray(seed, float), np.asarray(cand, float)
    out = {hy: {"fraction": 0.0, "centroid_m": None, "matched": 0}
           for hy in HYPOTHESES}
    if not len(seed) or not len(cand):
        return out
    a_s, P = seed[:, 0], seed[:, 1:4]
    c, n = label_frame(seed)
    rel = P - c
    A = a_s.sum()
    a_c, Q = cand[:, 0], cand[:, 1:4]
    ratio = a_c[None, :] / np.maximum(a_s[:, None], 1e-30)
    anchor_ok = np.abs(ratio - 1.0) <= GLYPH_ANCHOR_TOL
    area_ok = (ratio <= GLYPH_AREA_RATIO) & (ratio >= 1.0 / GLYPH_AREA_RATIO)
    big_first = np.argsort(-a_s, kind="stable")
    for hy in HYPOTHESES:
        relH = _hyp(rel, hy, n)
        best, tried = out[hy], set()
        for i in big_first[:anchors]:
            for j in np.nonzero(anchor_ok[i])[0]:
                origin = Q[j] - relH[i]
                key = tuple(np.round(origin / GLYPH_POS_TOL_M).astype(int))
                if key in tried:
                    continue
                tried.add(key)
                d = np.linalg.norm((origin + relH)[:, None, :] - Q[None],
                                   axis=2)
                ok = area_ok & (d <= GLYPH_POS_TOL_M)
                used, got, cnt = set(), 0.0, 0
                for s in big_first:
                    js = np.nonzero(ok[s])[0]
                    for jj in js[np.argsort(d[s, js], kind="stable")]:
                        if int(jj) not in used:
                            used.add(int(jj))
                            got += min(a_s[s], a_c[jj])
                            cnt += 1
                            break
                if got / A > best["fraction"] + 1e-12:
                    best.update(fraction=float(got / A),
                                centroid_m=origin.tolist(), matched=cnt)
    return out


def _clusters(F, link):
    """Single-linkage groups of glyph faces by centroid distance."""
    import numpy as np
    n = len(F)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    P = F[:, 1:4]
    d = np.linalg.norm(P[:, None] - P[None], axis=2)
    for i, j in zip(*np.nonzero(np.triu(d <= link, 1))):
        parent[find(int(i))] = find(int(j))
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return [sorted(g) for g in groups.values()]


def _glyphs(capture, ids):
    import numpy as np
    rows = [f for i in ids for f in ((capture.get("glyph_faces") or {})
                                      .get(i) or [])]
    return np.asarray(rows, float).reshape(-1, 7)


def seed_labels(baseline):
    """The seed's text labels and logos, located by structure, with their
    faces and handedness. Text: the engraving cluster nearest each centre
    button (outside the button's own footprint) and the one above each
    bumper. Logos: each face button's engraving."""
    import numpy as np
    seed = baseline["seed"]
    by = {b["id"]: b for b in baseline["bodies"]}
    F = _glyphs(baseline, seed["roles"]["housing"])
    groups = _clusters(F, LABEL_LINK_M)
    cents = [(F[g][:, 1:4] * F[g][:, :1]).sum(0) / F[g][:, 0].sum()
             for g in groups]

    def nearest(x, z, exclude=None):
        best = None
        for g, c in zip(groups, cents):
            if exclude and exclude(c):
                continue
            d = math.hypot(c[0] - x, c[2] - z)
            if best is None or d < best[0]:
                best = (d, g)
        return best[1] if best else []

    labels = {}
    for role, name in (("select", "SELECT"), ("start", "START")):
        b = by[seed["roles"][role][0]]
        e = extent_of(b)

        def inside(c, e=e):
            return (e[0] - 0.001 <= c[0] <= e[3] + 0.001
                    and e[2] - 0.001 <= c[2] <= e[5] + 0.001)
        labels[name] = F[nearest(b["centroid_m"][0], b["centroid_m"][2],
                                 inside)]
    for bid in seed["roles"]["bumpers"]:
        b = by[bid]
        name = "R" if b["centroid_m"][0] > seed["plane_x_m"] else "L"
        labels[name] = F[nearest(b["centroid_m"][0], b["centroid_m"][2])]
    fb = seed["clusters"]["face_buttons"]
    cx = seed["plane_x_m"] + fb["u_m"]
    symbols = {}
    for bid in seed["roles"]["face_buttons"]:
        g = _glyphs(baseline, [bid])
        if not len(g):
            continue
        c = by[bid]["centroid_m"]
        symbols[bid] = {"faces": g, "du_m": c[0] - cx,
                        "dz_m": c[2] - fb["z_m"]}
    out = {"text": {}, "symbols": {}}
    for name, g in labels.items():
        self_r = register(g, g)
        out["text"][name] = {
            "faces": g, "area_m2": float(g[:, 0].sum()) if len(g) else 0.0,
            "centroid_m": label_frame(g)[0].tolist() if len(g) else None,
            "self_R": self_r["R"]["fraction"],
            "self_Rot": self_r["Rot"]["fraction"],
            "chiral": max(self_r["R"]["fraction"],
                          self_r["Rot"]["fraction"]) < ACHIRAL_SELF}
    for bid, s in symbols.items():
        self_r = register(s["faces"], s["faces"])
        out["symbols"][bid] = {**s, "area_m2": float(s["faces"][:, 0].sum()),
                               "chiral": max(self_r["R"]["fraction"],
                                             self_r["Rot"]["fraction"])
                               < ACHIRAL_SELF}
    sk = (baseline.get("body_skew_x") or {}).get(seed["roles"]["start"][0])
    out["start_skew"] = sk
    out["clusters"] = [len(g) for g in groups]
    # The seed's letter pitch: adjacent letter faces of START / SELECT along
    # X (island faces inside A and R, under a quarter of the median letter,
    # are not letters).
    gaps = []
    for name in ("START", "SELECT"):
        F = labels[name]
        if len(F) < 2:
            continue
        med = float(np.median(F[:, 0]))
        xs = sorted(F[F[:, 0] >= 0.25 * med][:, 1])
        gaps += [b - a for a, b in zip(xs, xs[1:])]
    out["letter_pitch_m"] = min(gaps) if gaps else None
    return out


# --------------------------------------------------------------------------
# housing surface: height maps compared under the widening warp
# --------------------------------------------------------------------------

#: Beside the seam where the widening inserts material: the warp jumps by
#: 2h there, and a bilinear sample straddles the jump for one cell on each
#: side, plus one cell for rounding h -- two 1 mm cells.
SEAM_MARGIN_M = 0.002
#: Around every feature the conversion swaps: the same two cells (a feature
#: mirrored about a plane that falls mid-cell lands up to a cell off).
MASK_DILATE_M = 0.002
#: Steeper than 45 deg, a sub-cell lateral shift reads as a height change.
SLOPE_MAX = 1.0
#: Cells this close to a silhouette are not compared (sampling there is
#: unstable by half a cell either way).
EDGE_CELLS = 2
MAP_VIEWS = (("top", "shape_xz", 2), ("bottom", "shape_xz", 2),
             ("front", "shape_xy", 1), ("back", "shape_xy", 1))


def _bilinear(m, fi, fk):
    """m sampled at fractional cell indices; NaN if any of the four
    neighbours is NaN or outside the map."""
    import numpy as np
    ni, nk = m.shape
    i0 = np.floor(fi).astype(int)
    k0 = np.floor(fk).astype(int)
    out = np.full(fi.shape, np.nan)
    ok = (i0 >= 0) & (k0 >= 0) & (i0 + 1 < ni) & (k0 + 1 < nk)
    i, k = i0[ok], k0[ok]
    t1, t2 = (fi - i0)[ok], (fk - k0)[ok]
    out[ok] = (m[i, k] * (1 - t1) * (1 - t2) + m[i + 1, k] * t1 * (1 - t2)
               + m[i, k + 1] * (1 - t1) * t2 + m[i + 1, k + 1] * t1 * t2)
    return out


def _dilate(mask, r):
    import numpy as np
    out = mask.copy()
    for ax in (0, 1):
        acc = out.copy()
        for s in range(1, r + 1):
            acc |= np.roll(out, s, axis=ax) | np.roll(out, -s, axis=ax)
        out = acc
    return out


def seed_swap_mask(m, x0, step, plane, t):
    """Cells where the seed differs from its own mirror image by more than t
    (or where only one side is housing), mirrored onto both sides and
    dilated: exactly the features a left-hand conversion swaps."""
    import numpy as np
    ni, nk = m.shape
    xs = x0 + (np.arange(ni) + 0.5) * step
    fi = np.repeat((((2 * plane - xs) - x0) / step - 0.5)[:, None], nk, 1)
    fk = np.repeat(np.arange(nk, dtype=float)[None, :], ni, 0)
    mir = _bilinear(m, fi, fk)
    fin, finm = np.isfinite(m), np.isfinite(mir)
    asym = (fin & finm & (np.abs(m - mir) > t)) | (fin ^ finm)
    asym |= np.nan_to_num(_bilinear(asym.astype(float), fi, fk)) > 0
    return _dilate(asym, int(round(MASK_DILATE_M / step)))


def compare_view(seed_m, s_x0, s_k0, cand_m, c_x0, c_k0, step, plane_s,
                 plane_c, h, t, swap):
    """Deviation cells of one candidate view against the seed's, the seed
    warped by the candidate's own half-widening h. Masked: the seam strip,
    swapped features (anywhere between their mirrored position and h further
    out), steep cells and silhouette bands."""
    import numpy as np
    ni, nk = cand_m.shape
    uc = c_x0 + (np.arange(ni) + 0.5) * step - plane_c
    xs = plane_s + uc - np.sign(uc) * h
    fi = np.repeat(((xs - s_x0) / step - 0.5)[:, None], nk, 1)
    kc = c_k0 + (np.arange(nk) + 0.5) * step
    fk = np.repeat(((kc - s_k0) / step - 0.5)[None, :], ni, 0)
    s = _bilinear(seed_m, fi, fk)
    gx, gk = np.gradient(np.nan_to_num(seed_m, nan=0.0), step)
    slope = _bilinear(np.hypot(gx, gk), fi, fk)
    sm = np.zeros((ni, nk), bool)
    span = int(np.ceil(abs(h) / step)) + 1
    swf = swap.astype(float)
    for j in range(-span, span + 1):
        sm |= np.nan_to_num(_bilinear(swf, fi + j, fk)) > 0
    seam = np.repeat((np.abs(uc) <= abs(h) + SEAM_MARGIN_M)[:, None], nk, 1)
    fc, fs = np.isfinite(cand_m), np.isfinite(s)
    edge = _dilate(~fc | ~fs, EDGE_CELLS)
    excluded = seam | sm | edge
    dev = ((fc & fs & (np.abs(cand_m - s) > t) & (slope <= SLOPE_MAX))
           | (fc ^ fs)) & ~excluded
    return dev, {"compared": int((~excluded & (fc | fs)).sum()),
                 "masked": int(excluded.sum()),
                 "deviation_cells": int(dev.sum())}


#: The noise floor is this percentile of the seed's own left/right map
#: differences: 1 cell in 100 of the seed's symmetric surface differs from
#: its mirror by more (tessellation and half-cell interpolation on slopes).
MAP_NOISE_PERCENTILE = 99.0


def seed_map_scales(baseline, view="top"):
    """(t, A_letter, info), all read off the seed:
      engraving depth -- the shallowest engraved label (R / L) on its top
          map: what the seed itself calls a deliberate feature;
      t -- MAP_NOISE_PERCENTILE of |map - mirror(map)| over the seed's
          symmetric surface (differences shallower than that engraving, on
          the cells the comparison reads): the method's own noise, since
          the two halves are tessellated independently;
      A_letter -- the median letter face of START / SELECT (one face per
          letter there; the median skips the islands inside A and R).
    A deviation within the noise, or smaller than one letter, is not a
    change."""
    import numpy as np
    hm = baseline["housing_maps"]
    step = hm["step_m"]
    top = _dec(hm["top"], hm["shape_xz"])
    x0, z0 = hm["origin_m"][0], hm["origin_m"][2]
    sl = seed_labels(baseline)
    depths = []
    for name in ("R", "L"):
        F = sl["text"][name]["faces"]
        lo, hi = F[:, 1:4].min(0), F[:, 1:4].max(0)
        i0, i1 = (int((v - x0) / step) for v in (lo[0], hi[0]))
        k0, k1 = (int((v - z0) / step) for v in (lo[2], hi[2]))
        box = top[i0:i1 + 1, k0:k1 + 1]
        ring = top[max(0, i0 - 4):i1 + 5, max(0, k0 - 4):k1 + 5]
        if np.isfinite(box).any() and np.isfinite(ring).any():
            depths.append(float(np.nanmedian(ring) - np.nanmin(box)))
    depth = min(depths) if depths else 0.0005
    shp = "shape_xz" if view in ("top", "bottom") else "shape_xy"
    m = _dec(hm[view], hm[shp])
    ni, nk = m.shape
    plane = baseline["seed"]["plane_x_m"]
    xs = hm["origin_m"][0] + (np.arange(ni) + 0.5) * step
    fi = np.repeat((((2 * plane - xs) - hm["origin_m"][0]) / step
                    - 0.5)[:, None], nk, 1)
    fk = np.repeat(np.arange(nk, dtype=float)[None, :], ni, 0)
    mir = _bilinear(m, fi, fk)
    gx, gk = np.gradient(np.nan_to_num(m, nan=0.0), step)
    keep = (np.isfinite(m) & np.isfinite(mir)
            & (np.hypot(gx, gk) <= SLOPE_MAX)
            & ~_dilate(~np.isfinite(m) | ~np.isfinite(mir), EDGE_CELLS))
    d = np.abs(m - mir)[keep]
    d = d[d < depth]
    t = float(np.percentile(d, MAP_NOISE_PERCENTILE)) if len(d) else depth
    letters = [f[0] for name in ("START", "SELECT")
               for f in sl["text"][name]["faces"]]
    a = statistics.median(letters) if letters else None
    return t, a, {"engraving_depth_m": depth, "label_depths_m": depths,
                  "noise_cells": int(len(d))}


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
    controls = sorted({i for r in CONTROL_ROLES for i in roles.get(r, [])}
                      | {i for g in rdiag.get("duplicate_clusters", [])
                         for i in g})
    intf = control_interference(raw, bodies, controls, hids)
    surfaces = capture_surfaces(raw, bodies, hids, hext)
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
        "interference": intf,
        **surfaces,
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


def translate_yz(measured, dy, dz):
    """A copy of a capture moved by (0, dy, dz): bodies, extents, glyph
    faces, map origins and the heights the maps store (top / bottom hold
    absolute y, front / back absolute z). X needs no such step -- everything
    along X is read relative to the part's own mirror plane."""
    import copy
    out = copy.deepcopy(measured)
    for b in out.get("bodies", []):
        b["centroid_m"] = [b["centroid_m"][0], b["centroid_m"][1] + dy,
                           b["centroid_m"][2] + dz]
        for key in ("extent_m", "bbox_m"):
            e = b.get(key)
            if e and len(e) == 6:
                b[key] = [e[0], e[1] + dy, e[2] + dz, e[3], e[4] + dy,
                          e[5] + dz]
    for rows in (out.get("glyph_faces") or {}).values():
        for r in rows:
            r[2] += dy
            r[3] += dz
    hm = out.get("housing_maps")
    if hm:
        o = hm["origin_m"]
        hm["origin_m"] = [o[0], o[1] + dy, o[2] + dz]
        for view, shp, kax in MAP_VIEWS:
            if hm.get(view):
                d = dy if kax == 2 else dz      # top/bottom: y; front/back: z
                hm[view] = _enc(_dec(hm[view], hm[shp]) + d)
    return out


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
        # Y / Z: a part whose origin was reset in Y or Z is read in its own
        # frame, aligned on the housing's extent minimum (the requested edit
        # moves nothing in Y or Z; the Y/Z spans are checked in #7).
        sh = self.seed["housing_extent_m"]
        dy, dz = sh[1] - self.hext[1], sh[2] - self.hext[2]
        self.yz_shift_mm = [round(dy * MM, 3), round(dz * MM, 3)]
        if max(abs(dy), abs(dz)) > 1e-6:
            measured = translate_yz(measured, dy, dz)
            self.ms = measured
            self.C = {b["id"]: b for b in measured["bodies"]}
            self.hext = union_extent(measured["bodies"], self.hids)
            if max(abs(dy), abs(dz)) * MM > 0.05:
                self.notes.append(f"housing frame offset {self.yz_shift_mm}"
                                  " mm (y, z) from the seed's; read in its "
                                  "own frame")
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
        self._lab = None

    def u(self, i):
        return self.C[i]["centroid_m"][0] - self.P

    def label_results(self):
        """(seed labels, text registrations, symbol registrations), once."""
        if self._lab is None:
            sl = seed_labels(self.bl)
            Fh = _glyphs(self.ms, self.hids)
            Ff = _glyphs(self.ms, self.roles.get("face_buttons") or [])
            self._lab = (
                sl,
                {name: register(L["faces"], Fh)
                 for name, L in sl["text"].items()},
                {bid: register(S["faces"], Ff)
                 for bid, S in sl["symbols"].items()})
        return self._lab

    @staticmethod
    def symbol_name(s):
        if abs(s["du_m"]) >= abs(s["dz_m"]):
            return "symbol left" if s["du_m"] < 0 else "symbol right"
        return "symbol top" if s["dz_m"] < 0 else "symbol bottom"

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
    def _band_score(self, uc, us, perfect_mm):
        """Distance of u from the mirrored band [mirror(u_seed), mirror +
        h outboard] scored to zero at |u_seed| (not across the plane)."""
        lo, hi = sorted((-us, -us + sgn(-us) * self.h))
        d = 0.0 if lo <= uc <= hi else min(abs(uc - lo), abs(uc - hi))
        return (score_error(d * MM, perfect_mm, abs(us) * MM),
                {"u_mm": round(uc * MM, 2),
                 "band_mm": [round(lo * MM, 2), round(hi * MM, 2)],
                 "outside_band_mm": round(d * MM, 3)})

    def c_stsel(self, with_text=True):
        parts, det = {}, {}
        for role in ("select", "start"):
            rec = self.seed["centre"][role]
            ids = self.roles.get(role) or []
            if not ids:
                parts[f"{role} button"] = 0.0
                det[f"{role} button"] = {"missing": True}
                continue
            s, d = self._band_score(self.u(ids[0]), rec["u_m"],
                                    TOL["stsel_perfect_mm"])
            d["dy_mm_reported"] = round(
                (self.C[ids[0]]["centroid_m"][1] - rec["y_m"]) * MM, 3)
            parts[f"{role} button"], det[f"{role} button"] = s, d
        if with_text and self.bl.get("glyph_faces") \
                and self.ms.get("glyph_faces"):
            sl = self.label_results()[0]
            pitch = sl.get("letter_pitch_m")
            for name, uc in self.text_positions().items():
                us = sl["text"][name]["centroid_m"][0] - self.seed["plane_x_m"]
                # A label is placed to one letter: a shift under the seed's
                # smallest letter pitch leaves it by the same button.
                s, d = self._band_score(uc, us, (pitch or 0.0005) * MM)
                d["perfect_mm"] = round((pitch or 0.0005) * MM, 3)
                parts[f"{name} text"], det[f"{name} text"] = s, d
        score = mean(parts.values())
        return {"score": round(score, 4), "status": status_of(score),
                "components": {k: round(v, 4) for k, v in parts.items()},
                "detail": det,
                "evidence": "START and SELECT buttons (and their text, where "
                            "present) at the mirror of their seed positions; "
                            "carried outboard by up to h is also mirrored"}

    # -- 5 ---------------------------------------------------------------
    def c_orient(self):
        """Every readable text label must read the seed's way round, the
        face-button symbols must keep their arrangement, and the START
        pointer must point the seed's way. The weakest item decides."""
        if not (self.bl.get("glyph_faces") and self.ms.get("glyph_faces")):
            return {"score": NEUTRAL_UNVERIFIABLE, "status": UNVERIFIABLE,
                    "evidence": "no engraving faces in the baseline or the "
                                "capture (captures before ps3-capture/6 "
                                "lack them)"}
        sl, text, sym = self.label_results()
        items, skipped, det = {}, {}, {}
        # A reading wins clearly once it explains this much more of the label
        # than the alternatives: half the smallest margin by which a seed
        # label's own reading beats its own mirror / rotation (SELECT: 0.5).
        # Partly missing engraving lowers both readings alike, so it is
        # charged once -- by criterion 6 -- and not again here.
        margin = 0.5 * min((1.0 - max(L["self_R"], L["self_Rot"]))
                           for L in sl["text"].values() if L["chiral"])
        for name, r in text.items():
            fr = {hy: round(r[hy]["fraction"], 4) for hy in HYPOTHESES}
            det[f"text {name}"] = fr
            if not sl["text"][name]["chiral"]:
                skipped[f"text {name}"] = "achiral: matches its own mirror"
                continue
            if max(fr.values()) < PRESENCE_ZERO:
                skipped[f"text {name}"] = "absent (criterion 6 charges it)"
                continue
            items[f"text {name}"] = clamp01(
                0.5 + (fr["T"] - max(fr["R"], fr["Rot"])) / (2 * margin))
        det["reading_margin"] = round(margin, 4)
        fb = self.roles.get("face_buttons") or []
        if len(fb) == 4:
            ccx = mean(self.C[i]["centroid_m"][0] for i in fb)
            rad = self.seed["clusters"]["face_buttons"]["radius_m"]
            for bid, S in sl["symbols"].items():
                r = sym[bid]
                name = self.symbol_name(S)
                best = max(HYPOTHESES, key=lambda hy: r[hy]["fraction"])
                if r[best]["fraction"] < PRESENCE_ZERO:
                    skipped[name] = "absent (criterion 6 charges it)"
                    continue
                if abs(S["du_m"]) > abs(S["dz_m"]):
                    # unambiguously on one side beyond half a button offset
                    du = r[best]["centroid_m"][0] - ccx
                    items[f"{name} side"] = clamp01(
                        0.5 + sgn(S["du_m"]) * du / rad)
                    det[f"{name} side"] = {"seed_du_mm": round(S["du_m"] * MM,
                                                               2),
                                           "du_mm": round(du * MM, 2)}
                if S["chiral"]:
                    fr = {hy: r[hy]["fraction"] for hy in HYPOTHESES}
                    items[f"{name} reading"] = clamp01(
                        0.5 + (fr["T"] - max(fr["R"], fr["Rot"]))
                        / (2 * margin))
                    det[f"{name} reading"] = {k: round(v, 4)
                                              for k, v in fr.items()}
        s_seed = sl.get("start_skew")
        st = self.roles.get("start") or []
        if s_seed is not None and abs(s_seed) >= SKEW_MIN and st:
            s_c = (self.ms.get("body_skew_x") or {}).get(st[0])
            if s_c is not None:
                # WHICH WAY it points, not how sharply: a rebuilt pointer may
                # be blunter (the reference's reads 0.139 against the seed's
                # 0.252, same sign). Full credit from SKEW_MIN (the seed's
                # noise floor) the seed's way, none from SKEW_MIN the other.
                items["START pointer"] = clamp01(
                    0.5 + sgn(s_seed) * s_c / (2 * SKEW_MIN))
                det["START pointer"] = {"seed_skew": round(s_seed, 4),
                                        "skew": round(s_c, 4)}
        if not items:
            return {"score": NEUTRAL_UNVERIFIABLE, "status": UNVERIFIABLE,
                    "detail": {"skipped": skipped},
                    "evidence": "no chiral label could be read"}
        s = min(items.values())
        worst = min(items, key=items.get)
        return {"score": round(s, 4), "status": status_of(s),
                "components": {k: round(v, 4) for k, v in items.items()},
                "detail": {"fractions": det, "skipped": skipped},
                "evidence": f"each label placed on the candidate as moved "
                            f"(T), mirrored (R) or upside down (Rot); the "
                            f"weakest item decides -- {worst}"}

    def text_positions(self):
        """{START, SELECT: candidate u (m)} of the text labels, from their
        best registration; absent labels are left to criterion 6."""
        if not (self.bl.get("glyph_faces") and self.ms.get("glyph_faces")):
            return {}
        sl, text, _ = self.label_results()
        out = {}
        for name in ("START", "SELECT"):
            r = text.get(name)
            if not r:
                continue
            best = max(HYPOTHESES, key=lambda hy: r[hy]["fraction"])
            if r[best]["fraction"] >= PRESENCE_ZERO:
                out[name] = r[best]["centroid_m"][0] - self.P
        return out

    # -- 6 ---------------------------------------------------------------
    def c_kept(self):
        if not (self.bl.get("glyph_faces") and self.ms.get("glyph_faces")):
            return {"score": NEUTRAL_UNVERIFIABLE, "status": UNVERIFIABLE,
                    "evidence": "no engraving faces in the baseline or the "
                                "capture (captures before ps3-capture/6 "
                                "lack them)"}
        sl, text, sym = self.label_results()
        items = {}
        for name, r in text.items():
            f = max(r[hy]["fraction"] for hy in HYPOTHESES)
            items[f"text {name}"] = f
        for bid, r in sym.items():
            f = max(r[hy]["fraction"] for hy in HYPOTHESES)
            items[self.symbol_name(sl["symbols"][bid])] = f
        scores = {k: score_ratio(f, PRESENCE_FULL, PRESENCE_ZERO)
                  for k, f in items.items()}
        s = min(scores.values()) if scores else NEUTRAL_UNVERIFIABLE
        worst = min(scores, key=scores.get) if scores else None
        return {"score": round(s, 4), "status": status_of(s),
                "components": {k: round(v, 4) for k, v in scores.items()},
                "detail": {"engraved_area_found": {k: round(f, 4)
                                                   for k, f in items.items()},
                           "seed_label_faces": {
                               k: len(v["faces"])
                               for k, v in sl["text"].items()}},
                "evidence": f"share of each seed label's engraved area found "
                            f"again on the candidate (any orientation); the "
                            f"weakest decides -- {worst}: "
                            f"{items.get(worst, 0):.0%}"}

    # -- 7 (housing surface) ---------------------------------------------
    def surface_deviation(self):
        """Housing height maps against the seed's, warped by this part's own
        widening. SCORED: the top view -- the controller's visible face, where
        every requested edit and every label lives -- with each control's
        plan footprint masked (the housing under a control is its seat; the
        reference rebuilds those). REPORTED: bottom, front, back, which the
        reference itself changes (shoulder openings, rear LED windows, the
        shell parting line). Added hardware is not masked, so adding a body
        cannot hide a cut."""
        import numpy as np
        sm, cm = self.bl.get("housing_maps"), self.ms.get("housing_maps")
        if not (sm and cm):
            return None
        plane_s = self.seed["plane_x_m"]
        step = sm["step_m"]
        controls = [i for r in CONTROL_ROLES for i in self.roles.get(r, [])]
        out = {"views": {}}
        for view, shp, kax in MAP_VIEWS:
            t, a_letter, info = seed_map_scales(self.bl, view)
            if view == "top":
                out.update({"t_mm": round(t * MM, 4),
                            "a_letter_mm2": round(a_letter * 1e6, 3),
                            "seed_engraving_depth_mm": round(
                                info["engraving_depth_m"] * MM, 3)})
            S = _dec(sm[view], sm[shp])
            C = _dec(cm[view], cm[shp])
            swap = seed_swap_mask(S, sm["origin_m"][0], step, plane_s, t)
            dev, st = compare_view(S, sm["origin_m"][0], sm["origin_m"][kax],
                                   C, cm["origin_m"][0], cm["origin_m"][kax],
                                   step, plane_s, self.P, self.h, t, swap)
            if view == "top":
                ni, nk = C.shape
                xs = cm["origin_m"][0] + (np.arange(ni) + 0.5) * step
                zs = cm["origin_m"][2] + (np.arange(nk) + 0.5) * step
                foot = np.zeros((ni, nk), bool)
                pad = MASK_DILATE_M
                for i in controls:
                    e = extent_of(self.C[i])
                    if e:
                        foot |= np.outer(
                            (xs >= e[0] - pad) & (xs <= e[3] + pad),
                            (zs >= e[2] - pad) & (zs <= e[5] + pad))
                dev = dev & ~foot
                st["deviation_cells"] = int(dev.sum())
                st["control_footprint_cells"] = int(foot.sum())
            st["area_mm2"] = round(st["deviation_cells"] * (step * MM) ** 2, 1)
            if st["deviation_cells"]:
                ii, kk = np.nonzero(dev)
                u = cm["origin_m"][0] + (ii + 0.5) * step - self.P
                kv = cm["origin_m"][kax] + (kk + 0.5) * step
                st["where_u_mm"] = [round(u.min() * MM), round(u.max() * MM)]
                st[f"where_{'z' if kax == 2 else 'y'}_mm"] = [
                    round(kv.min() * MM), round(kv.max() * MM)]
            st["scored"] = view == "top"
            st["t_mm"] = round(t * MM, 4)
            out["views"][view] = st
        out["scored_area_mm2"] = out["views"]["top"]["area_mm2"]
        a_mm2 = out["a_letter_mm2"]
        out["score"] = score_error(out["scored_area_mm2"], a_mm2, 10 * a_mm2)
        return out

    # -- 7 ---------------------------------------------------------------
    def c_unreq(self, with_surface=True):
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
        if with_surface:
            surf = self.surface_deviation()
            if surf is not None:
                parts["housing_surface"] = surf["score"]
                det["housing_surface"] = surf
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
                "evidence": "the weakest part decides: bodies the edit leaves "
                            "alone keep shape and y/z, the housing keeps its "
                            "Y/Z spans and, outside the edit zones, its top "
                            "surface. Added hardware is reported, not scored"}

    # -- 8 ---------------------------------------------------------------
    def c_rebuild(self):
        census = self.rebuild.get("census")
        if census is None:
            return {"score": NEUTRAL_UNVERIFIABLE, "status": UNVERIFIABLE,
                    "evidence": "no rebuild census in the capture"}
        seed_c = (self.bl.get("rebuild") or {}).get("feature_errors") or {}

        def counts(c):
            return (sum(1 for v in c.values() if not v[1]),
                    sum(1 for v in c.values() if v[1]))

        def sketch_errors(model):
            st = (((model or {}).get("sketches") or {})
                  .get("status_counts") or {})
            # swConstrainedStatus_e: 4 over-, 5 no solution, 6 invalid
            return sum(int(v) for k, v in st.items() if k in ("4", "5", "6"))
        hc, wc = counts(census)
        hs, ws = counts(seed_c)
        skc = sketch_errors(self.ms.get("modelling"))
        sks = sketch_errors(self.bl.get("modelling"))
        n = (max(0, hc - hs) + max(0, skc - sks) + 0.5 * max(0, wc - ws))
        feats = (self.bl.get("rebuild") or {}).get("features") or 199
        zero = TOL["rebuild_zero_frac"] * feats
        s = score_error(n, 0.0, zero)
        return {"score": round(s, 4), "status": status_of(s),
                "detail": {"new_hard_errors": max(0, hc - hs),
                           "new_sketch_errors": max(0, skc - sks),
                           "new_warnings": max(0, wc - ws),
                           "weighted_count": n, "zero_at": round(zero, 2),
                           "failing_features_reported": sorted(
                               k for k, v in census.items())[:20]},
                "evidence": f"{max(0, hc - hs)} new failing feature(s), "
                            f"{max(0, skc - sks)} sketch(es) in an error "
                            f"state, {max(0, wc - ws)} new warning(s) after "
                            f"EditRebuild3 (counted, not matched by name); "
                            f"zero at {zero:.1f}"}

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
                          "modelling", "rebuild", "glyph_faces",
                          "housing_maps")
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
        "glyph_faces": cap["glyph_faces"],
        "body_skew_x": cap["body_skew_x"],
        "housing_maps": cap["housing_maps"],
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
    hm = cap.get("housing_maps") or {}
    nglyph = sum(len(v) for v in (cap.get("glyph_faces") or {}).values())
    return (f"{len(cap.get('bodies') or [])} bodies, "
            f"{xs.get('n_rays', 0)} rays in {xs.get('seconds', 0)}s, "
            f"{nglyph} glyph faces, {hm.get('triangles', 0)} housing "
            f"triangles in {cap.get('surfaces_seconds', 0)}s")


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
