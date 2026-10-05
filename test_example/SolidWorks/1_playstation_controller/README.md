# Harness — PS3 controller: widen 15 mm + left-handed layout

`tests/task/harness/harness.py`, version **3.1.0**. It grades a candidate
`.SLDPRT` against the seed part, frozen as measurements in
`tests/task/prompt/input.json`, and prints one JSON score envelope out of
**10.0**. What changed from 2.3.1, and why, is in [CHANGES.md](CHANGES.md).
That includes the 3.1.0 red-team pass, summarised [below](#red-team-310).

**Geometry only.** The harness reads mass properties, exact extreme points,
ray sections, tessellated faces and height maps. It never reads feature
names, body names, body order (`GetBodies2` "may vary the order") or the
tree's structure. Every body's role is worked out from its shape and its
place in the part. A candidate that solves the task another valid way scores
the same as the reference. Valid variations include:
- a different origin or body order;
- a housing split into other bodies;
- rebuilt buttons, or a d-pad moulded in one piece;
- labels re-cut with differently split faces;
- START/SELECT anywhere between the exact mirror and the mirror carried outboard with the stance.

## What is graded

Each criterion returns a continuous subscore in [0, 1]. None of them is a
gate, so a broken tree no longer zeroes the geometry. Weights live in
`ALL_CRITERIA`, each next to the clause of `instruction.md` it comes from.
`task.toml`'s `max_score` is their sum, and a unit test keeps the two equal.

| # | Criterion | Weight | Measurement |
|---|---|---:|---|
| 1 | widened 15 mm at the grips | 2.0 | Growth of the grip-lobe separation (+X rays through the housing where the seed's section is two grips) and of the body's X extent, both against +15 mm. Multiplied by a not-scaled check: the grip lobes must keep their width. |
| 2 | clusters re-spaced to the stance | 2.0 | Each button cluster's x against its mirrored seed position carried outboard by the candidate's own half-widening h, with its z and the height of its top unchanged. Multiplied by cluster rigidity, by sticks/triggers/bumpers following the stance, and by fit (no new interference, including from left-over copies). |
| 3 | d-pad and face buttons swapped | 2.0 | Which side of the candidate's own mirror plane each cluster sits on, ramped over one seed cluster radius and averaged over every copy of the cluster: a copy left on its original side halves the credit. |
| 4 | START/SELECT mirrored | 1.0 | START and SELECT buttons and their text, each anywhere between the exact mirror of its seed position and that mirror carried outboard by h. |
| 5 | text and logos oriented | 1.0 | Each seed label (START, SELECT, L, R) and symbol is registered against the candidate's engraving faces as moved, mirrored or turned upside down. It is tested against the wrong readings its own engraving does not reproduce, so a △ turned upside down is caught. Also read: which side of the cluster □ sits on, and which way the START pointer points. The weakest item decides. |
| 6 | text and logos preserved | 1.0 | The share of each seed label's and symbol's engraved area found again on the candidate. ○, which has no engraving-scale face, is read by its floor. The weakest item decides. |
| 7 | no unrequested changes | 0.5 | Bodies the edit leaves alone keep their shape and y/z and are not duplicated. The housing keeps its Y/Z spans and, outside the edit zones, its top surface (height map against the seed's, warped by h). A hole through it, or a body rising above it, counts too. |
| 8 | rebuilds cleanly | 0.5 | New failing features, sketches in an error state and new warnings after `EditRebuild3`, counted, never matched by name. |

The asked-for edits (1–4) carry 7.0 and the two constraints the instruction
names (5–6) carry 2.0. The implicit constraints (7–8) carry 1.0. An
untouched seed collects 5–8 and nothing else, so it scores **3.0 / 10**.

Frame: `u = x − P`, where P is the candidate's **own** mirror plane, the
midline of its two grip lobes. h is half the candidate's **own**
grip-separation growth. Re-spacing is judged against the stance the
candidate actually built, so a wrongly sized widening is charged once, by
criterion 1.

Corpus, as graded by 3.1.0:

| model | width | space | swap | st/sel | orient | logos | unreq | rebld | score |
|---|---|---|---|---|---|---|---|---|---|
| solution | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | **10.000** |
| input (untouched seed) | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 3.000 |
| adversarial_feature_tree_with_errors | 0.00 | 0.16 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 4.823 |
| adversarial_missing_glyphs | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 9.000 |
| adversarial_only_one_button_cluster_mirrored | 1.00 | 0.50 | 0.25 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 7.500 |
| adversarial_text_mirrored_incorrectly | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 9.000 |
| adversarial_unrequested_change_elsewhere | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 9.500 |
| adversarial_unwidened_shell_with_correct_clusters | 0.02 | 0.10 | 0.50 | 0.85 | 1.00 | 0.00 | 0.00 | 0.00 | 3.103 |
| adversarial_widened_15mm_clusters_at_original_spacing | 1.00 | 0.00 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.000 |
| adversarial_widened_by_30mm | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 8.000 |

## Running

Every command is run from this task's directory, with SolidWorks **already
open** and your work **saved**. Each run closes the session's open
documents before it opens the next part. Use a Python with pywin32, numpy
and scipy (the repository's `.venv` has them).

The script is `tests\task\harness\harness.py`. If you hand Python the
directory instead of the file, you get `can't find '__main__' module`. That
means the filename is missing, not that the harness is broken.

### The usual run

**1. Prove the connection with one part.**

```bat
python tests\task\harness\harness.py solution\solution.SLDPRT
```

This must come back `10.0/10.0` with `passed: true`. **If the reference is
not 10.000, stop.** The baseline or the machine is wrong, not the reference.

**2. Measure the corpus.** Measuring needs SolidWorks and takes about two
minutes per edited part (25 s for the seed). It only has to happen once:

```bat
python tests\task\harness\harness.py --batch --capture-only
```

With no path, it takes the shipped task directory: the seed, the reference
and the eight examples listed in `task.toml`. Captures land in
`results\captures\`.

**3. Score.** This needs no SolidWorks and takes a few seconds per part:

```bat
python tests\task\harness\harness.py --batch --score-from results\captures
```

You get:
- a table on stdout;
- `results\summary.md` and `.csv`;
- per model, `results\<model>.envelope.json` (the envelope) and `.log` (the readable breakdown);
- per model, `results\full\<model>.report.json` (every measurement and every criterion's detail).

`UNGRADABLE` in a `.log` means the part was **not measured**: it would not
open, has no solid bodies, or has no housing. That is a different verdict
from "measured and wrong", and the reason is printed with it.

Splitting steps 2 and 3 makes the stored captures a regression suite that
needs no CAD. Change a formula, re-run step 3, and see which models moved.
The same split works for a single part:

```bat
python tests\task\harness\harness.py --capture-only part.SLDPRT -o cap.json
python tests\task\harness\harness.py --score-from cap.json
```

Other options: `--only substr,substr`, `--timeout SECONDS` (the default per
part is 900 s), `--out DIR`, and `--help`. `--batch` also accepts explicit
parts or any directory; a directory not laid out like the task is globbed
for `*.SLDPRT`. Each part is measured in its own child process, so one
wedged COM call can be timed out without ending the batch.

### One part, and the envelope

```bat
python tests\task\harness\harness.py path\to\candidate.SLDPRT
```

With no argument, it grades the active document. The readable summary goes
to **stderr**. Exactly one JSON envelope goes to **stdout**; this is the
contract the pipeline reads:

```json
{
 "task_id": "solidworks-0001-playstation-controller",
 "score": 10.0,
 "max_score": 10.0,
 "passed": true,
 "subscores": {
  "widened 15 mm at the grips": 1.0,
  "clusters re-spaced to the stance": 1.0,
  "d-pad and face buttons swapped": 1.0,
  "START/SELECT mirrored": 1.0,
  "text and logos oriented": 1.0,
  "text and logos preserved": 1.0,
  "no unrequested changes": 1.0,
  "rebuilds cleanly": 1.0
 },
 "harness_version": "3.1.0"
}
```

`passed` means flawless, not "good enough": `finalize()` sets it to "every
subscore is 1.0". `score` says how much of the task was done; `passed` says
whether the answer is fully correct. Set `HARNESS_REPORT_JSON` to a path to
keep the full report of a single run (batch mode does this for you).

### How the part is measured

The saved part is brought up to date with `EditRebuild3` and measured as
saved. A forced full rebuild runs **last**, as an unscored diagnostic.
`ForceRebuild3` is not idempotent on these files: the reference settles with
two failing DeleteFace features, and the seed's first forced pass after
opening fails 18 features.

### Re-freeze the baseline

```bat
python tests\task\harness\harness.py --capture-baseline environment\input.SLDPRT
```

This re-measures the seed and rewrites `input.json` (schema
`ps-annotation-baseline/7`). The baseline holds:
- the bodies and their structural roles, the mirror plane (x = 80.5 mm), the grip-lobe rays and the cluster geometry;
- every engraving face, the large planar faces of every non-housing body, the housing height maps and the body skews;
- the seed's own rebuild census.

The thresholds the grader derives from it are recomputed from these at
scoring time, among them the noise floor of the housing maps. Re-run the
re-freeze only when the seed changes or the harness records something new,
then re-capture the corpus. Re-measuring the same seed reproduces the
baseline exactly once body ids are mapped by position (verified for 3.0.0
and 3.1.0).

`--capture-seed-rebuild environment\input.SLDPRT` refreshes only the seed's
rebuild census. That census describes the machine as much as the part, so
run it on the grading machine. On this seed it is empty (199 features, no
errors, no warnings).

### Offline tests

```bat
python -m unittest discover -s tests\task\harness -v
```

These need no SolidWorks. They run against stored captures of the ten
shipped parts (`tests\task\harness\fixtures\*.json.gz`). They check that:
- the reference scores full marks, the seed 3.0, and each example loses only the criteria listed for it;
- valid variants of the reference keep full marks: shuffled body order, ids and names; origin moved in X, Y and Z; clusters within tolerance; START/SELECT anywhere in the mirrored band; rebuilt buttons;
- defects injected into the reference cost their own criterion: reflected text, deleted symbols, a groove outside the edit zones, an X-scaled housing, sticks left at the old stance;
- every red-team finding stays fixed, and every limitation it documents still behaves as documented (`RedTeam`, built by `redteam_variants.py`);
- scoring is deterministic, including on a second live capture of the reference;
- `task.toml` and this README agree with the code.

## Red team (3.1.0)

A red-team pass against 3.0.0 built synthetic variants of the reference
capture: valid solutions modelled differently, and wrong ones. It scored
them offline. Every finding below has a test in `test_harness.py` that
failed on 3.0.0 and passes on 3.1.0. The details and the numbers are in
CHANGES.md.

**Fixed: wrong solutions 3.0.0 let through**
- **Clusters copied instead of moved**, with the originals left on their side (10.0 → 8.0). A copy left behind now halves the swap credit, and its clashes count against fit.
- **A pocket beside a cluster** (10.0 → 9.5). The mask around the swapped features was twice as wide as the geometry needs.
- **A hole drilled through the housing** (10.0 → 9.5). The silhouette band swallowed every hole present in only one map.
- **A left-over copy of a stick.** It scored 10.0, 8.92 or 8.42 depending on body order; it now scores 9.5 in every order. Kept bodies are matched by position among congruent candidates, and a duplicate standard part costs #7.
- **Clusters floating 4 mm above their seats**, or 6 mm off in z (10.0 → 8.44 / 8.0). #2 now reads a cluster's z and the height of its top.
- **A stray body standing on the housing** (10.0 → 9.5).
- **△ engraved upside down** (#5 1.0 → 0).
- **○ deleted** (10.0 → 9.0). Needed a new measurement: the large planar faces of every non-housing body, schema `ps3-capture/8`.

**Fixed: valid solutions 3.0.0 penalised**
- **Housing left in three bodies, grip | centre | grip** (as low as 0.0 → 10.0). A housing body may now span the part in X or in Z.
- **D-pad moulded in one piece** (8.0 → 10.0).
- **Labels re-cut with differently split faces** (as low as 8.17 → 10.0). A pair of coplanar faces now stands for one.
- **A 0.1 mm pip at the housing's lowest point** (9.5 → 10.0). A uniform frame offset is removed before the surface is compared.

**Still limitations, each pinned by an expected-failure test**
- **Buttons swapped, housing seats left unconverted.** Not caught unless the buttons clash. The reference itself leaves 23 of its 291 deciding cells reading "unconverted", so any full-credit threshold would be one only the reference justifies.
- **A change on the bottom, front or back.** Reported, not scored: the reference makes symmetric 0.2–0.8 mm changes there itself.
- **Labels re-typed at a different size** (×1.05: 9.06). Matching is positional, and the instruction gives no size tolerance.
- **Symmetric symbols mirrored in place** (9.0). The □ engraving's faces, walls included, are split asymmetrically. Telling an invisible split from a visible flip needs the engraving's shape, not its faces.

## Not graded, and why

- **Handedness of symbols and parts that match their own mirror.** △ and ✕
  read the same mirrored, and so do the joystick caps (x-skew 0.000). A
  mirrored copy of them is the same geometry, so a naive mirror cannot be
  told from a correct one there. △ is still tested upside down. ○ is
  checked for presence only, by its floor; a single face cannot say which
  way round it reads.
- **The L1/L2 ↔ R1/R2 assignment swap.** The shoulder bodies are mirror
  pairs of one shape, so swapping their assignment leaves no geometric
  trace.
- **Added hardware inside the shell and remodelled internals.** The
  reference adds screws and LED domes, shells the housing and rebuilds the
  buttons. These are reported, not scored. A body that rises above the
  housing's top surface *is* scored, under #7. The bottom, front and back
  height maps are compared and reported; only the top view is scored,
  because the reference itself changes the other three.
- **Tree hygiene.** Suppressed features, the sketch-constraint mix and
  external references are tree structure. They are reported, not scored.
- **Reach and ergonomics.** Whether a thumb still reaches the clusters is
  not a dimension. `task.toml` describes the adversarial that would settle
  it.
- **A rotated part.** The frame is the seed's axes, and a candidate that
  re-orients the whole part is not re-aligned. The red team measured an
  approximate synthetic rotation: 9.5 at 0.05° and 9.47 at 0.5°.
