#!/usr/bin/env python3
"""
Offline tests of harness.py -- no SolidWorks, only stored captures.

Run from the task directory (1_playstation_controller):

    python -m unittest discover -s tests/task/harness -v

fixtures/<model>.json.gz are the captures harness 3.0.0 took of the ten
shipped parts (`harness.py --batch --capture-only`) against the baseline in
tests/task/prompt/input.json; solution_repeat is a second, independent live
capture of the reference. They prove three things:

  corpus          the reference scores full marks, the untouched seed 3.0,
                  and every example loses points only on what it gets wrong;
  valid variants  the reference changed the way a different valid answer
                  would differ (body order and names, origin, placement
                  within tolerance, rebuilt bodies) keeps full marks;
  controls        a defect injected into the reference costs the criterion
                  that names it.

The transforms edit a capture the way SolidWorks would have measured the
transformed part. They are written here, independently of the harness's
own frame code, so a bug there cannot cancel itself out.
"""
from __future__ import annotations

import base64
import copy
import gzip
import importlib.util
import json
import math
import random
import sys
import tomllib
import unittest
import zlib
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TASK_DIR = HERE.parents[2]
FIXTURES = HERE / "fixtures"

_spec = importlib.util.spec_from_file_location("ps3_harness",
                                               HERE / "harness.py")
H = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = H     # finalize() finds the task dir through it
_spec.loader.exec_module(H)

BASELINE = json.loads((HERE.parent / "prompt" / "input.json")
                      .read_text(encoding="utf-8"))

WIDTH, SPACE, SWAP, STSEL = H.C_WIDTH, H.C_SPACE, H.C_SWAP, H.C_STSEL
ORIENT, KEPT, UNREQ, REBUILD = H.C_ORIENT, H.C_KEPT, H.C_UNREQ, H.C_REBUILD
ALL = set(H.ALL_CRITERIA)

#: What each shipped model gets wrong, from its README entry and its render;
#: every criterion not listed must stay at 1.0.
LOSES = {
    "solution": set(),
    "input": {WIDTH, SPACE, SWAP, STSEL},
    # widened 30 mm, d-pad arms rebuilt round, 15 new failing features
    "adversarial_feature_tree_with_errors": {WIDTH, SPACE, SWAP, REBUILD},
    "adversarial_missing_glyphs": {KEPT},
    "adversarial_only_one_button_cluster_mirrored": {SPACE, SWAP},
    "adversarial_text_mirrored_incorrectly": {ORIENT},
    "adversarial_unrequested_change_elsewhere": {UNREQ},
    # shell not widened, face buttons missing from their holes, the two
    # small bodies on the plane moved 7.6 mm, new failing features
    "adversarial_unwidened_shell_with_correct_clusters": {
        WIDTH, SPACE, SWAP, STSEL, KEPT, UNREQ, REBUILD},
    "adversarial_widened_15mm_clusters_at_original_spacing": {
        SPACE, SWAP, STSEL},
    "adversarial_widened_by_30mm": {WIDTH},
}

#: The totals the corpus scores (regression guard). Two moved in 3.1.0 on the
#: same criteria they already failed: only_one 8.0 -> 7.5 (its face buttons
#: were copied, the originals left in place: #3 counts the copy) and
#: unwidened 3.148 -> 3.103 (its displaced d-pad stands 1.3 mm high: #2
#: now reads a cluster's y/z).
TOTALS = {
    "solution": 10.0,
    "input": 3.0,
    "adversarial_feature_tree_with_errors": 4.823,
    "adversarial_missing_glyphs": 9.0,
    "adversarial_only_one_button_cluster_mirrored": 7.5,
    "adversarial_text_mirrored_incorrectly": 9.0,
    "adversarial_unrequested_change_elsewhere": 9.5,
    "adversarial_unwidened_shell_with_correct_clusters": 3.103,
    "adversarial_widened_15mm_clusters_at_original_spacing": 5.0,
    "adversarial_widened_by_30mm": 8.0,
}

_CACHE: dict = {}


def capture(name):
    if name not in _CACHE:
        _CACHE[name] = json.loads(gzip.decompress(
            (FIXTURES / f"{name}.json.gz").read_bytes()))
    return copy.deepcopy(_CACHE[name])


def grade(cap):
    return H.score_capture(cap, baseline=BASELINE, quiet=True)


def scores(report):
    return {k: v["score"] for k, v in report["criteria"].items()}


def dec(s, shape):
    return np.frombuffer(zlib.decompress(base64.b64decode(s)),
                         np.float32).reshape(shape).astype(np.float64)


def enc(a):
    return base64.b64encode(zlib.compress(
        np.asarray(a, np.float32).tobytes(), 6)).decode("ascii")


def grader(cap):
    return H.Grader(BASELINE, cap)


# -- transforms ------------------------------------------------------------

def relabel(cap, seed=7):
    """Bodies in another order, under other ids and names."""
    c = copy.deepcopy(cap)
    rng = random.Random(seed)
    bodies = list(c["bodies"])
    rng.shuffle(bodies)
    new = {b["id"]: f"b{n:02d}" for n, b in enumerate(bodies)}
    for b in bodies:
        b["id"] = new[b["id"]]
        b["name"] = f"Body-Move/Copy{rng.randrange(10 ** 6)}"
    c["bodies"] = bodies
    c["housing_ids"] = sorted(new[i] for i in c["housing_ids"])
    for key in ("glyph_faces", "planar_faces", "body_skew_x"):
        if key in c:
            c[key] = {new[k]: v for k, v in c[key].items()}
    for p in (c.get("interference") or {}).get("pairs", []):
        p["a"], p["b"] = new[p["a"]], new[p["b"]]
    for key in ("capture_roles", "capture_role_diag", "widening_at_capture"):
        c.pop(key, None)
    return c


def move(cap, d):
    """The whole part translated by d (m)."""
    dx, dy, dz = d
    c = copy.deepcopy(cap)
    for b in c["bodies"]:
        b["centroid_m"] = [v + d[k] for k, v in enumerate(b["centroid_m"])]
        for key in ("extent_m", "bbox_m"):
            if b.get(key):
                b[key] = [v + d[k % 3] for k, v in enumerate(b[key])]
    for key in ("glyph_faces", "planar_faces"):
        for rows in (c.get(key) or {}).values():
            for r in rows:
                r[1] += dx
                r[2] += dy
                r[3] += dz
    xs = c["xsection"]
    xs["y0_m"] += dy
    xs["z0_m"] += dz
    for hits in xs["rays"].values():
        for hit in hits:
            hit[0] += dx
    hm = c["housing_maps"]
    hm["origin_m"] = [v + d[k] for k, v in enumerate(hm["origin_m"])]
    for view, shape, kax in H.MAP_VIEWS:
        # top/bottom store y heights over X-Z, front/back z over X-Y
        hm[view] = enc(dec(hm[view], hm[shape]) + (dy if kax == 2 else dz))
    for key in ("housing_extent_m",):
        if c.get(key):
            c[key] = [v + d[k % 3] for k, v in enumerate(c[key])]
    return c


def move_bodies(c, ids, d):
    """Some bodies (and the engraving on them) translated by d, in place."""
    for b in c["bodies"]:
        if b["id"] in ids:
            b["centroid_m"] = [v + d[k]
                               for k, v in enumerate(b["centroid_m"])]
            for key in ("extent_m", "bbox_m"):
                if b.get(key):
                    b[key] = [v + d[k % 3] for k, v in enumerate(b[key])]
    for key in ("glyph_faces", "planar_faces"):
        for i in ids:
            for r in (c.get(key) or {}).get(i, []):
                r[1] += d[0]
                r[2] += d[1]
                r[3] += d[2]
    return c


def resize_bodies(c, ids, f):
    """Some bodies rebuilt uniformly f times larger, in place."""
    for b in c["bodies"]:
        if b["id"] in ids:
            b["volume_m3"] *= f ** 3
            b["area_m2"] *= f ** 2
            b["inertia_com"] = {k: v * f ** 5
                                for k, v in b["inertia_com"].items()}
    return c


def label_faces(c, name):
    """(housing id, row indices, origin) of a text label as the reference
    carries it: the faces nearest the seed label's faces placed by its
    registered translation."""
    g = grader(c)
    sl, text, _ = g.label_results()
    origin = np.asarray(text[name]["T"]["centroid_m"])
    seed = np.asarray(sl["text"][name]["faces"], float)
    a = seed[:, 0]
    centre = (seed[:, 1:4] * a[:, None]).sum(0) / a.sum()
    want = origin + (seed[:, 1:4] - centre)
    # back into the capture's own frame (the grader aligns y/z first)
    dy, dz = (v / H.MM for v in g.yz_shift_mm)
    want = want - np.array([0.0, dy, dz])
    out = []
    for hid in c["housing_ids"]:
        rows = np.asarray(c["glyph_faces"][hid], float).reshape(-1, 7)
        if not len(rows):
            continue
        dist = np.linalg.norm(rows[None, :, 1:4] - want[:, None, :], axis=2)
        near = dist.argmin(1)
        hit = dist[np.arange(len(want)), near] <= H.GLYPH_POS_TOL_M
        out += [(hid, int(j)) for j in near[hit]]
    return out, origin


# -- the corpus ------------------------------------------------------------

class Corpus(unittest.TestCase):
    def test_reference_full_marks(self):
        rep = grade(capture("solution"))
        self.assertEqual(rep["weighted_score"], 10.0)
        self.assertEqual(rep["overall"], H.PASS)
        env = H.envelope_from(rep)
        self.assertEqual(env["score"], 10.0)
        self.assertEqual(env["max_score"], 10.0)
        self.assertTrue(env["passed"])

    def test_seed_floor(self):
        s = scores(grade(capture("input")))
        self.assertEqual({k for k, v in s.items() if v == 0.0},
                         {WIDTH, SPACE, SWAP, STSEL})
        self.assertEqual({k for k, v in s.items() if v == 1.0},
                         {ORIENT, KEPT, UNREQ, REBUILD})

    def test_each_example_loses_only_what_it_gets_wrong(self):
        for name, loses in LOSES.items():
            with self.subTest(model=name):
                s = scores(grade(capture(name)))
                self.assertEqual(set(s), ALL)
                self.assertEqual({k for k, v in s.items() if v < 1.0}, loses)

    def test_totals(self):
        for name, total in TOTALS.items():
            with self.subTest(model=name):
                rep = grade(capture(name))
                self.assertAlmostEqual(rep["weighted_score"], total, places=3)

    def test_examples_score_below_the_reference(self):
        for name in LOSES:
            if name != "solution":
                with self.subTest(model=name):
                    self.assertLess(grade(capture(name))["weighted_score"],
                                    10.0)


class Determinism(unittest.TestCase):
    def test_scoring_twice_is_identical(self):
        a = json.dumps(grade(capture("solution")), sort_keys=True,
                       default=str)
        b = json.dumps(grade(capture("solution")), sort_keys=True,
                       default=str)
        self.assertEqual(a, b)

    def test_second_live_capture_of_the_reference(self):
        if not (FIXTURES / "solution_repeat.json.gz").exists():
            self.skipTest("no repeat capture in fixtures/")
        a = grade(capture("solution"))
        b = grade(capture("solution_repeat"))
        self.assertEqual(scores(a), scores(b))
        self.assertEqual(a["weighted_score"], b["weighted_score"])


# -- valid variants keep full marks ----------------------------------------

class ValidVariants(unittest.TestCase):
    def assertFullMarks(self, cap):
        rep = grade(cap)
        self.assertEqual(scores(rep), {k: 1.0 for k in ALL},
                         msg=json.dumps(rep.get("notes")))
        self.assertEqual(rep["weighted_score"], 10.0)

    def test_body_order_ids_and_names(self):
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                self.assertFullMarks(relabel(capture("solution"), seed))

    def test_origin_moved(self):
        # A reset origin, or one grip moved 15 mm instead of both 7.5 mm
        # (a symmetric widening plus a translation).
        for d in ((0.020, 0, 0), (-0.0075, 0, 0), (0, 0.005, 0),
                  (0, 0, -0.005), (0.020, 0.005, -0.005)):
            with self.subTest(d_mm=[v * 1000 for v in d]):
                self.assertFullMarks(move(capture("solution"), d))

    def test_clusters_placed_within_tolerance(self):
        # 0.4 mm in every axis: inside the 0.5 mm perfect band of x and,
        # since 3.1.0 scores a cluster's y/z too, of y and z.
        c = capture("solution")
        g = grader(c)
        move_bodies(c, set(g.roles["dpad"]), (0.0004, 0.0004, -0.0004))
        move_bodies(c, set(g.roles["face_buttons"]),
                    (-0.0004, -0.0004, 0.0004))
        self.assertFullMarks(c)

    def test_start_select_anywhere_in_the_mirrored_band(self):
        # Mirrored, or mirrored and carried outboard with the stance: both
        # read as "mirrored positions". Only the buttons move here (their
        # seats do not), so only #4 is asserted.
        base = capture("solution")
        g = grader(base)
        for end in (0.0, 1.0):
            c = copy.deepcopy(base)
            for role in ("select", "start"):
                i = g.roles[role][0]
                us = g.seed["centre"][role]["u_m"]
                target = -us + math.copysign(end * g.h, -us)
                move_bodies(c, {i}, (target - g.u(i), 0.0, 0.0))
            with self.subTest(band_end=end):
                self.assertEqual(scores(grade(c))[STSEL], 1.0)

    def test_rebuilt_buttons_and_kept_bodies_within_noise(self):
        c = capture("solution")
        g = grader(c)
        resize_bodies(c, set(g.roles["dpad"]), 1.05)
        resize_bodies(c, set(g.roles["face_buttons"]), 0.95)
        resize_bodies(c, set(g.roles["select"]) | set(g.roles["start"]),
                      1.03)
        resize_bodies(c, set(g.roles["sticks"]), 1.001)
        self.assertFullMarks(c)


# -- injected defects cost their own criterion -----------------------------

class Controls(unittest.TestCase):
    def assertOnlyBelow(self, cap, below):
        s = scores(grade(cap))
        self.assertEqual({k for k, v in s.items() if v < 1.0}, below,
                         msg=str(s))
        return s

    def test_text_reflected_in_place(self):
        c = capture("solution")
        for name in ("START", "SELECT"):
            faces, origin = label_faces(c, name)
            self.assertGreater(len(faces), 5)
            for hid, j in faces:
                r = c["glyph_faces"][hid][j]
                r[1] = 2 * origin[0] - r[1]
                r[4] = -r[4]
        s = self.assertOnlyBelow(c, {ORIENT})
        self.assertEqual(s[ORIENT], 0.0)

    def test_symbols_deleted(self):
        c = capture("solution")
        for i in grader(c).roles["face_buttons"]:
            c["glyph_faces"][i] = []
        s = self.assertOnlyBelow(c, {KEPT})
        self.assertEqual(s[KEPT], 0.0)

    def test_groove_outside_the_edit_zones(self):
        c = capture("solution")
        g = grader(c)
        hm = c["housing_maps"]
        top = dec(hm["top"], hm["shape_xz"])
        step = hm["step_m"]
        xs = hm["origin_m"][0] + (np.arange(top.shape[0]) + 0.5) * step
        zs = hm["origin_m"][2] + (np.arange(top.shape[1]) + 0.5) * step
        u = xs - g.P
        rows = (u >= 0.012) & (u <= 0.037)
        cols = (zs >= -0.026) & (zs <= -0.024)
        cut = np.outer(rows, cols) & np.isfinite(top)
        self.assertGreater(int(cut.sum()), 40)
        top[cut] -= 0.0003                       # 0.3 mm deep, 2 x 25 mm
        hm["top"] = enc(top)
        s = self.assertOnlyBelow(c, {UNREQ})
        self.assertLess(s[UNREQ], 0.25)

    def test_housing_scaled_instead_of_separated(self):
        # The seed's housing X-scaled about its plane until the body is
        # 15 mm wider: the forbidden way to widen.
        c = capture("input")
        g = grader(c)
        hids = set(c["housing_ids"])
        w = g.hext[3] - g.hext[0]
        f = 1 + 0.015 / w

        def sx(x):
            return g.P + f * (x - g.P)
        for b in c["bodies"]:
            if b["id"] in hids:
                b["centroid_m"][0] = sx(b["centroid_m"][0])
                for key in ("extent_m", "bbox_m"):
                    if b.get(key):
                        b[key][0], b[key][3] = sx(b[key][0]), sx(b[key][3])
        for hits in c["xsection"]["rays"].values():
            for hit in hits:
                hit[0] = sx(hit[0])
        rep = grade(c)
        width = rep["criteria"][WIDTH]
        self.assertLessEqual(width["components"]["not_scaled"], 0.05)
        self.assertLessEqual(width["score"], 0.5)

    def test_sticks_left_at_the_old_stance(self):
        c = capture("solution")
        g = grader(c)
        for i in g.roles["sticks"]:
            move_bodies(c, {i}, (-math.copysign(g.h, g.u(i)), 0.0, 0.0))
        self.assertOnlyBelow(c, {SPACE})
        space = grade(c)["criteria"][SPACE]
        # two of the six followers left behind (triggers and bumpers moved)
        self.assertAlmostEqual(space["components"]["followers"], 4 / 6,
                               places=2)


# -- the red-team pass on 3.0.0 --------------------------------------------

sys.path.insert(0, str(HERE))
import redteam_variants as RV                                     # noqa: E402

TH = sys.modules[__name__]


def below(cap):
    return {k for k, v in scores(grade(cap)).items() if v < 1.0}


class RedTeam(unittest.TestCase):
    """The red-team findings on 3.0.0 (CHANGES.md, "Red team"). Every test
    here failed on 3.0.0. The expected failures are the findings left as
    documented limitations; each says why."""

    # -- wrong solutions 3.0.0 let through -------------------------------
    def test_rt01_clusters_copied_not_moved(self):
        s = scores(grade(RV.clusters_copied(capture("solution"), TH)))
        self.assertEqual({k for k, v in s.items() if v < 1.0}, {SPACE, SWAP},
                         msg=str(s))
        self.assertLessEqual(s[SWAP], 0.5)

    def test_rt02_pocket_beside_a_cluster(self):
        cap = RV.pocket(capture("solution"), TH, u_mm=105.5, z_mm=-25.6)
        self.assertEqual(below(cap), {UNREQ})

    def test_rt03_hole_through_the_housing(self):
        for d in (6.0, 12.0):
            with self.subTest(d_mm=d):
                cap = RV.through_hole(capture("solution"), TH, d_mm=d)
                self.assertEqual(below(cap), {UNREQ})

    def test_rt04_leftover_stick_whatever_the_body_order(self):
        base = capture("solution")
        reports = [grade(RV.leftover_stick(base, TH, first=True)),
                   grade(RV.leftover_stick(base, TH, first=False))]
        reports += [grade(relabel(RV.leftover_stick(base, TH), seed))
                    for seed in range(1, 7)]
        totals = {r["weighted_score"] for r in reports}
        self.assertEqual(len(totals), 1, msg=str(totals))
        self.assertEqual({k for k, v in scores(reports[0]).items()
                          if v < 1.0}, {UNREQ})

    def test_rt05_clusters_off_in_y_or_z(self):
        for dy, dz in ((4.0, 0.0), (0.0, 6.0)):
            with self.subTest(dy_mm=dy, dz_mm=dz):
                cap = RV.clusters_offset(capture("solution"), TH, dy, dz)
                self.assertEqual(below(cap), {SPACE})

    def test_rt06_stray_body_on_the_housing(self):
        cap = RV.block_on_top(capture("solution"), TH)
        self.assertEqual(below(cap), {UNREQ})

    def test_rt07_symbol_upside_down(self):
        cap = RV.symbol_upside_down(capture("solution"), TH, "symbol top")
        self.assertEqual(below(cap), {ORIENT})

    # -- valid solutions 3.0.0 penalised ---------------------------------
    def assertFullMarks(self, cap):
        s = scores(grade(cap))
        self.assertEqual(s, {k: 1.0 for k in ALL}, msg=str(s))

    def test_rt08_housing_in_three_pieces(self):
        for cut in (37.5, 47.5, 61.5):
            with self.subTest(cut_mm=cut):
                self.assertFullMarks(RV.three_piece_housing(
                    capture("solution"), TH, cut_mm=cut))

    def test_rt09_dpad_moulded_in_one_piece(self):
        self.assertFullMarks(RV.one_piece_dpad(capture("solution"), TH))

    def test_rt10_labels_recut_with_split_faces(self):
        for frac, names in ((0.5, ("START", "SELECT")),
                            (0.3, ("START", "SELECT")),
                            (0.5, ("START", "SELECT", "R", "L"))):
            with self.subTest(frac=frac, names=names):
                self.assertFullMarks(RV.labels_resplit(
                    capture("solution"), TH, frac=frac, names=names))

    def test_rt11_pip_at_the_lowest_point(self):
        for d in (0.05, 0.1):
            with self.subTest(delta_mm=d):
                self.assertFullMarks(RV.lowest_point_pip(
                    capture("solution"), TH, delta_mm=d))

    # -- documented limitations ------------------------------------------
    def test_rt16_circle_symbol_deleted(self):
        cap = RV.circle_deleted(capture("solution"), TH)
        self.assertEqual(below(cap), {KEPT})

    @unittest.expectedFailure
    def test_rt12_limit_seats_not_converted(self):
        # The reference itself leaves 23 of its 291 deciding seat cells
        # reading "unconverted"; a full-credit threshold would be tuned to
        # it. Partly covered: buttons colliding with old seats cost #2 fit.
        cap = RV.seats_not_converted(capture("solution"), TH)
        self.assertLess(grade(cap)["weighted_score"], 10.0)

    @unittest.expectedFailure
    def test_rt13_limit_pocket_on_the_underside(self):
        # Bottom/front/back are reported, not scored: the reference makes
        # symmetric 0.2-0.8 mm changes there itself.
        cap = RV.pocket_underneath(capture("solution"), TH)
        self.assertIn(UNREQ, below(cap))

    @unittest.expectedFailure
    def test_rt14_limit_text_retyped_five_percent_larger(self):
        # Matching is positional (0.3 mm); a re-typed label at another size
        # is a different engraving. No instruction-based size tolerance.
        self.assertFullMarks(RV.text_rescaled(capture("solution"), TH))

    @unittest.expectedFailure
    def test_rt15_limit_symmetric_symbols_mirrored_in_place(self):
        # The square is a symmetric shape, but its engraving's faces (walls
        # included: self-match 0.32) are split asymmetrically, so a square
        # mirrored in place reads as flipped. Telling an invisible split
        # from a visible flip needs the engraving's shape (tessellation),
        # not its faces. Found during the red-team fixes; also in 3.0.0.
        self.assertFullMarks(RV.symbols_mirrored_in_place(
            capture("solution"), TH))


# -- the documents agree with the code -------------------------------------

class Documents(unittest.TestCase):
    def test_task_toml_max_score(self):
        meta = tomllib.loads((TASK_DIR / "task.toml")
                             .read_text(encoding="utf-8"))["metadata"]
        self.assertEqual(meta["max_score"], sum(H.ALL_CRITERIA.values()))

    def test_readme_names_version_and_maximum(self):
        text = (TASK_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn(H.HARNESS_VERSION, text)
        self.assertIn(f"{sum(H.ALL_CRITERIA.values()):.1f}", text)

    def test_schemas(self):
        self.assertEqual(BASELINE["schema"], H.BASELINE_SCHEMA)
        for name in LOSES:
            with self.subTest(model=name):
                self.assertEqual(capture(name)["schema"], H.CAPTURE_SCHEMA)


if __name__ == "__main__":
    unittest.main()
