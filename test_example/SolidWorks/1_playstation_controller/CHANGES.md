# CHANGES — PS3 controller harness 2.3.1 → 3.0.0 → 3.1.0

## 3.1.0 — red-team hardening

A red-team pass attacked 3.0.0 offline. It built synthetic variants of
the reference capture: valid solutions modelled differently, and wrong
solutions. It never opened SolidWorks or touched the repository, and every
number was reproduced by re-running its scripts.

Each finding then got:
- a test in `tests/task/harness/test_harness.py`, `RedTeam`, with its variants in `redteam_variants.py`;
- a run showing the test fails on 3.0.0;
- a fix;
- a run showing it passes.

Findings not fixed are pinned by expected-failure tests. Those tests document
the limitation and will flag the day it is fixed.

The criteria and weights are unchanged. What criteria 2, 3, 5, 6 and 7
measure changed, and the capture records one new thing, hence 3.1.0.

### Findings

Totals are on the fresh 3.1.0 captures, scored by 3.0.0 (the commit
`7c8039e`) and by 3.1.0.

| ID | Finding | Type | 3.0.0 | 3.1.0 | Fix (justification) |
|---|---|---|---:|---:|---|
| RT01 | Clusters **copied, not moved**: the swapped clusters present, the originals left on their side (Mirror Body keeps its sources by default) | false pass | 10.000 | 8.000 | #3 averages the side score over every copy of a cluster. A d-pad-shaped cross is a d-pad (the seed has no other); a round cross counts as the face cluster only if it carries a face symbol. Duplicate clusters also count as controls in #2's fit: the capture's census already covers them. |
| RT02 | A 15 × 15 × 1 mm pocket on a grip beside a cluster | false pass | 10.000 | 9.500 | #7's mask around swapped features is looked up outboard only, 0…h. A feature carried out by h warps exactly onto its mirrored seed position; one at the exact mirror sits up to h inboard. The old ±h sweep was twice as wide as that. With all masks together, a 1 mm change was visible on only 14.5 % of the reference's top surface; it is now 19 %. |
| RT03 | A hole drilled through the housing, 6 / 12 mm | false pass | 10.000 | 9.709 / 9.500 | The silhouette band now grows from cells empty in **both** maps. Growing it from either map swallowed every hole only one map has, so the existing one-sided term could never fire. |
| RT04 | A left-over copy of a stick (Move/Copy with "copy" ticked) | false pass + body-order dependence | 8.917 / 10.000 by order | 9.500 in every order | Kept bodies are congruent by fingerprint, then **assigned by position** (the seed's, carried out by h). A congruent body left over costs #7: new component `no_duplicate_parts`; the seed has one of each standard part. |
| RT05 | Clusters at the right x but 4 mm too high (floating), or 6 mm off in z | false pass | 10.000 | 8.442 / 8.000 | #2's placement × `score_error(max(|dz|, |dtop|), 0.5, 5)`. Mirroring moves a cluster in x only, and these are the same tolerances as every other y/z drift. It reads the cluster's **top**, not its centroid: a rebuilt button moves its centroid (the reference's by 2.5–3 mm) but not its top (0.02 mm). |
| RT06 | A stray 40 × 12 × 20 mm block standing on the housing | false pass | 10.000 | 9.500 | #7's top view counts cells where a body with no role rises above the housing's top surface. Decision 3 stands: hardware inside the shell is still not scored. The reference's screws and LED domes rise above nothing. |
| RT07 | △ engraved upside down | false pass | 9.771 | 9.000 | #5 tests each item against the wrong readings its own engraving does **not** reproduce (△: not its mirror, but its 180° turn). The label normal is now the cut direction, read off the walls; the old PCA axis leaned 2.5° on shallow engravings and misplaced a turned symbol by more than 0.3 mm. |
| RT16 | ○ deleted | false pass | 10.000 | 9.000 | **New measurement** (capture `/8`, baseline `/7`): the large planar faces of every non-housing body. Every symbol has a floor, an upward planar face at the engraving depth (seed: ○ 49.8, □ 44.2, △ 38.7, ✕ 32.4 mm²; the shared button faces are curved or face down). #6 reads ○ by its floor on the button in its place: area within 2×, offset from the button centre and depth below its top within 0.3 mm. |
| RT08 | Housing left as three bodies, grip / centre / grip (cut at 37.5 / 47.5 / 61.5 mm) | false penalty | 9.000 / 0.000 / 3.500 | 10.000 | A housing body spans ≥ 35 % of the part in X **or Z**. Seed: the controls span at most 16.8 % of X and 26.4 % of Z (both a stick); a grip spans the full depth. No corpus capture changes housing set. |
| RT09 | D-pad moulded in one piece | false penalty | 8.000 | 10.000 | With no four-arm cross, one body counts as the d-pad if: its plan is square (aspect ≤ 1.115); it is larger than any seed button; it is nearer the seed d-pad's plan size than the face cluster's; and it sits outside the centre region. Every bound is a seed measurement. |
| RT10 | Labels re-cut with differently split faces: START/SELECT 50/50 or 30/70, all four labels 50/50 | false penalty | 8.551 / 8.239 / 8.167 | 10.000 | A face cut into two **coplanar** pieces keeps its total area and area-weighted centroid. A pair of coplanar candidate faces may stand for one seed face: as an anchor, to complete a partial match, or for an unmatched face. Same 0.3 mm and ±25 % tolerances; pieces must share one plane. |
| RT11 | A 0.05 / 0.1 mm pip at the housing's lowest point | false penalty | 9.877 / 9.500 | 10.000 | Y/Z is aligned on one extreme point, so the pip offset the whole map. Each view now removes a uniform height offset first. The offset is the median over more compared cells than twice the zero area, so a scoring change can never be the majority it is read from. A real span change is still charged by `housing_yz_spans`. |

### Limitations kept, each an expected-failure test

| ID | Finding | 3.1.0 | Why it is not fixed |
|---|---|---:|---|
| RT12 | Buttons swapped, housing seats left unconverted (no clash) | 10.000 | A seat check would compare the housing around each cluster with the mirrored seed. The reference itself leaves 23 of its 291 deciding cells reading "unconverted". For comparison, the seed reads 0 of 527 converted, and the red team's swapped-seats variant about half. A full-credit threshold would be a number only the reference justifies. Buttons that collide with old seats are still charged by #2 fit. |
| RT13 | A 30 × 20 × 2 mm pocket in the underside | 10.000 | Bottom, front and back are reported, not scored (decision 6). The reference itself makes symmetric 0.2–0.8 mm changes there: the grip tips, the front of the grips, 1,900 mm² of the back bridge. No seed-derived rule passes those and catches an equivalent groove. |
| RT14 | START/SELECT re-typed 5 % larger | 9.055 | Matching is positional (0.3 mm), and the instruction gives no size tolerance to search over. Arguably a different engraving. |
| RT15 | Symmetric symbols mirrored in place (e.g. the cluster mirrored, then □ and ○ swapped back) | 9.000 | Found while fixing RT07, and present in 3.0.0 too. □ is a symmetric shape, but its engraving's faces, walls included, are split asymmetrically (self-match under mirror 0.30). A mirrored □ therefore reads as flipped. Telling an invisible split from a visible flip needs the engraving's **shape** (its tessellation), a larger redesign of #5/#6. |
| — | A part rotated as a whole | 9.5 at 0.05°, 9.47 at 0.5° (approximate synthesis) | The frame is the seed's axes, and the task never rotates the part. Fingerprints stay robust (2.4e-4 at 1°). |

Checked and not an issue:
- a single-body housing;
- the reference without its screws and LED domes;
- a 15 mm filler body left separate at the plane;
- R/L labels placed on the other side;
- sticks, triggers and bumpers mirrored (indistinguishable: seed x-skews ≤ 0.028).

All of these score 10.0.

### Effect on the corpus

On fresh captures of all ten parts with 3.1.0 (`--batch --capture-only`,
then `--score-from`):
- the reference is **10.000** (`passed`), the seed **3.000**;
- every example fails exactly the criteria it failed before.

Two totals moved:
- **only_one_button_cluster_mirrored, 8.000 → 7.500.** Its face buttons
  were copied onto the d-pad's side and the originals left in place (the
  render shows face buttons on both sides). #3 now counts that copy:
  0.5 → 0.25.
- **unwidened_shell_with_correct_clusters, 3.148 → 3.103.** Its displaced
  d-pad stands 1.3 mm higher than the seed's. #2 now reads that: 0.125 →
  0.103.

feature_tree's round, symbol-less d-pad is not mistaken for a face-button
copy: 4.823, unchanged.

### Side effects to know

- **Orientation margin.** Pair matching lets two coplanar pieces of L
  stand for one of its faces under the mirror hypothesis. L's self-match
  against its own mirror rises from 0.343 to 0.644, and the orientation
  margin M, derived from those self-matches, from 0.1985 to 0.1778. L stays
  testable (< 0.75), and text_mirrored still scores #5 = 0.
- **The cut-direction normal.** It undoes most of the rise pair matching
  caused in R's self-match under rotation: 0.186 in 3.0.0, 0.423 with pairs
  alone, 0.202 in 3.1.0. The upside-down test is cleaner for every label
  with walls; START and SELECT have none and keep the old axis.
- **Bug found by the tests while adding the floor measurement.**
  `translate_yz` did not move the new planar faces, so a part moved 5 mm in
  Y read its ○ floor at the wrong depth. Fixed before release; the
  origin-moved test pins it.
- **The existing cluster-jitter valid variant.** It now moves clusters
  0.4 mm in y and z instead of 1 mm, because y/z is scored with the 0.5 mm
  band of every other y/z drift.
- **Timing.**
  - Scoring a part takes about 5 s instead of 3 s (pair matching).
  - The test suite takes about 3.5 min.
  - Capture time is unchanged, within noise.
- **Re-captures.** The baseline was re-frozen (`/7`): every shared field is
  identical to `/6` once body ids are mapped, and the 448 engraving faces
  and the height maps are bit-identical. The ten parts and a second live
  capture of the reference were re-captured with 3.1.0; the two reference
  captures agree to round-off.

### Files

- `harness.py`;
- `test_harness.py`;
- `redteam_variants.py` (new);
- the 11 fixtures (re-captured);
- `tests/task/prompt/input.json` (re-frozen);
- `README.md`, with a red-team section;
- this file;
- `task.toml` notes.

---

## 3.0.0 — the rewrite

`tests/task/harness/harness.py` was rewritten in five stages on branch
`harness-v3`. Each stage ended with a working harness, a commit, and a
table for the reference, the eight examples and the seed:

| stage | commit | content |
|---|---|---|
| A | `543f4a6` | v2 fixes: `--batch` finds the examples, no rebuild gate, incremental census (2.4.0) |
| B | `6fdc9d3` | final rubric (max 10.0), structural roles, criteria 1–4 |
| C | `cb61f71` | criteria 6 and 8; baseline re-frozen (`/5`) |
| D | `84f8fc0` | criterion 5 by label registration |
| E | `0cc8d14` | criterion 7 reads the housing surface |
| final | `7c8039e` | v2 leftovers removed, a Y/Z frame bug fixed, baseline re-frozen (`/6`), offline tests, docs |

Every number below comes from a real run. The final table comes from
`--batch --capture-only` with 3.0.0 on 5 Oct 2026, followed by
`--batch --score-from results\final\captures`.

## 1. Scores

### 3.0.0 (max 10.0)

| model | width | space | swap | st/sel | orient | logos | unreq | rebld | score |
|---|---|---|---|---|---|---|---|---|---|
| solution | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | **10.000** (passed) |
| input (seed) | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 3.000 |
| feature_tree_with_errors | 0.00 | 0.16 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 4.823 |
| missing_glyphs | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | **0.00** | 1.00 | 1.00 | 9.000 |
| only_one_button_cluster_mirrored | 1.00 | **0.50** | **0.50** | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 8.000 |
| text_mirrored_incorrectly | 1.00 | 1.00 | 1.00 | 1.00 | **0.00** | 1.00 | 1.00 | 1.00 | 9.000 |
| unrequested_change_elsewhere | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | **0.00** | 1.00 | 9.500 |
| unwidened_shell_with_correct_clusters | 0.02 | 0.12 | 0.50 | 0.85 | 1.00 | 0.00 | 0.00 | 0.00 | 3.148 |
| widened_15mm_clusters_at_original_spacing | 1.00 | **0.00** | **0.00** | **0.00** | 1.00 | 1.00 | 1.00 | 1.00 | 5.000 |
| widened_by_30mm | **0.00** | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 8.000 |

### 2.3.1, as found (max 8.0)

| model | heal | hyg | C1 | C2 | C3 | C4 | C5 | C6 | score |
|---|---|---|---|---|---|---|---|---|---|
| solution | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 8.000 (passed) |
| input (seed) | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 | 3.000 |
| feature_tree_with_errors | 0.74 | 0.80 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.769 |
| missing_glyphs | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 7.000 |
| only_one_button_cluster_mirrored | 1.00 | 1.00 | 1.00 | 0.38 | 1.00 | 0.50 | 1.00 | 1.00 | 6.062 |
| text_mirrored_incorrectly | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.15 | 1.00 | 1.00 | 6.300 |
| unrequested_change_elsewhere | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | **8.000 (passed)** |
| unwidened_shell_with_correct_clusters | 0.39 | 0.60 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.496 |
| widened_15mm_clusters_at_original_spacing | 1.00 | 1.00 | **0.00** | 0.00 | 0.00 | 0.00 | 1.00 | 1.00 | 2.500 |
| widened_by_30mm | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 6.500 |

(C1 widened, C2 clusters mirrored, C3 no new interference, C4 left-handed
layout, C5 no unrequested changes, C6 markings preserved.)

### Totals stage by stage

A and 2.3.1 are out of 8.0; the rest are out of 10.0. B to E were scored
from the stage C captures; "final" comes from the fresh captures.

| model | 2.3.1 | A | B | C | D | E | final |
|---|---|---|---|---|---|---|---|
| solution | 8.000 | 8.000 | 10.000 | 10.000 | 10.000 | 10.000 | 10.000 |
| input (seed) | 3.000 | 3.000 | 3.000 | 3.000 | 3.000 | 3.000 | 3.000 |
| feature_tree_with_errors | 0.769 | 4.589 | 5.192 | 4.823 | 4.823 | 4.823 | 4.823 |
| missing_glyphs | 7.000 | 7.000 | 9.000 | 9.000 | 9.000 | 9.000 | 9.000 |
| only_one_button_cluster_mirrored | 6.062 | 6.062 | 8.000 | 8.000 | 8.000 | 8.000 | 8.000 |
| text_mirrored_incorrectly | 6.300 | 6.300 | 9.000 | 9.000 | 9.000 | 9.000 | 9.000 |
| unrequested_change_elsewhere | 8.000 | 8.000 | 10.000 | 10.000 | 10.000 | 9.500 | 9.500 |
| unwidened_shell_with_correct_clusters | 0.496 | 1.617 | 3.307 | 3.111 | 3.148 | 3.148 | 3.148 |
| widened_15mm_clusters_at_original_spacing | 2.500 | 2.500 | 5.000 | 5.000 | 5.000 | 5.000 | 5.000 |
| widened_by_30mm | 6.500 | 6.500 | 8.000 | 8.000 | 8.000 | 8.000 | 8.000 |

What each stage changed:
- **A:** removing the rebuild gate un-zeroed feature_tree and unwidened.
- **C:** rebuild health became a count. feature_tree's 15 new failures now
  reach zero, where v2's broken-fraction formula gave 0.74.
- **D:** START/SELECT text joined criterion 4. This moved unwidened 3.111 →
  3.148.
- **E:** the housing surface caught the unrequested cut.

### What moved, and why

- **unrequested_change_elsewhere: 8.0/8 → 9.5/10.** v2 passed it, because
  the housing was exempt from its reshape check. v3 compares the housing's
  top surface with the seed's and finds the cut: two strips totalling
  301 mm², 0.15–0.19 mm deep, at u = ±(10…40) mm, z = −26…−22 mm. That
  costs criterion 7 and nothing else.
- **widened_15mm_clusters_at_original_spacing: 2.5/8 → 5.0/10.** v2 read
  "not widened" because it measured the controls, which did not move. v3
  reads the shell: the grips moved apart by 15.0 mm, so width scores 1.0.
  The model then loses what it actually got wrong. The clusters were not
  re-spaced (0), not swapped (0), and START/SELECT were not mirrored (0).
- **feature_tree_with_errors: 0.769/8 → 4.823/10.** The rebuild gate is
  gone, so the geometry is graded as rebuilt (see section 5).
- **unwidened_shell_with_correct_clusters: 0.496/8 → 3.148/10.** It was
  gated by v2 as well. Ungated, it loses on most criteria:
  - its shell grew 0.2 mm (width 0.02);
  - its face buttons are missing from their holes (logos 0; the render shows the empty holes);
  - the two small bodies on the plane moved 7.6 mm off it (unrequested 0);
  - it has new failing features (rebuild 0).
- **text_mirrored_incorrectly: 6.3/8 → 9.0/10.** v2 caught it only because
  the engraved "R" label (v2's "port-light glyphs") changed side, and C4
  charged it as a layout fault. v3 registers every label. START and SELECT
  read mirrored: the mirrored reading explains 100 % of their engraved area,
  the unmirrored one 50 % and 39 %. L and R read correctly. Only criterion 5
  is charged.
- **widened_by_30mm: 6.5/8 → 8.0/10.** Only the width is wrong (+45 mm
  against +15: 200 % relative error, so 0). Its clusters follow its own
  stance, so re-spacing scores 1.0 and the wrong widening is charged once.
- **only_one_button_cluster_mirrored: 6.06/8 → 8.0/10.** The face buttons
  sit at their mirrored position, with a placement residual of 0.04 mm. The
  d-pad cluster is gone: no cross of four elongated buttons exists, and a
  second set of round face buttons is reported as a duplicate cluster.
  Re-spacing and swap each score 0.5.
- **missing_glyphs: 7.0/8 → 9.0/10.** □△✕ are gone, so logos scores 0. The
  same failure, re-weighted.
- **The seed drops from 37.5 % to 30 %.** It collects criteria 5–8 and
  nothing else.

## 2. Rubric

Total 10.0. `score_err(e, p, z)` is 1 inside p, falling linearly to 0 at
z. Every number is either stated in the instruction or measured on the
seed. Its justification is in a comment next to it in `TOL`, or next to the
constant.

| # | criterion (w) | clause | measurement | tolerance → score | catches |
|---|---|---|---|---|---|
| 1 | widened 15 mm at the grips (2.0) | "Widen the body by 15mm by increasing the separation between the two hand-grip halves (not by scaling the overall housing)" | +X rays at 187 (y, z) positions (a 6 mm lattice over the 1,680 where the seed's section is exactly two grips); Δ grip-lobe separation and Δ body X extent (`GetExtremePoint`); lobe-width change | mean of `score_err(\|Δ−15\|, 0.5, 15)` over the two; ×(0.5 + 0.5·not-scaled). 15 is stated to the mm (±0.5 is rounding); zero at 100 % error (0 or 30 mm). Not-scaled reaches zero at the lobe-width change that an X-scale reaching +15 mm would cause (2.93 mm). | widened_by_30mm, feature_tree, unwidened, seed |
| 2 | clusters re-spaced to the stance (2.0) | "re-space the button clusters to match the wider stance" | Each cluster's x against −u_seed ∓ h. Multiplied, each factor floored at 0.5, by: rigidity (pair spacings), followers (sticks, triggers, bumpers at \|u_seed\| + h) and fit (new interference volume) | `score_err(dx, 0.5, 7.5)`; zero at the full per-side move, so an unmoved cluster earns nothing. Rigidity zero at 5 mm (¼ of the 19.8 mm button offset). Fit perfect ≤ 1 mm³ (boolean noise; the seed reads 0), zero at 50 mm³ (≈ 0.15 mm overlap over a face button's 353 mm²). | widened_15mm_at_original_spacing, only_one, feature_tree, unwidened, seed |
| 3 | d-pad and face buttons swapped (2.0) | "swapping the D-pad and face-button clusters to the opposite side" | Side of each cluster's centre relative to the candidate's own plane | `clamp01(0.5 + σ·u / 2R)`, R = seed cluster radius (14.8 / 19.8 mm). A missing cluster, or a copy of the other in its place, scores 0. | widened_15mm_at_original_spacing, only_one, feature_tree, unwidened, seed |
| 4 | START/SELECT mirrored (1.0) | "The button clusters, START/SELECT labels … should end up in mirrored positions" | START and SELECT button bodies and text labels: distance to the band [mirror(u_seed), mirror + h outboard] | Buttons `score_err(d, 0.5, \|u_seed\|)`. Text is perfect within one letter pitch (3.216 mm, the seed's own lettering), zero at \|u_seed\|, i.e. never crossed the plane. | widened_15mm_at_original_spacing, seed, unwidened |
| 5 | text and logos oriented (1.0) | "must remain legible and correctly oriented — a naive geometric mirror that flips the labels backwards … is incorrect" | Each chiral seed label registered against the candidate's engraving faces as moved (T), x-mirrored (R) or turned 180° (Rot); □'s side of its cluster and its reading; the START pointer's x-skew sign | `clamp01(0.5 + (f_T − max(f_R, f_Rot)) / 2M)`, M = half the seed's own smallest reading margin (0.199). Side ramp over one button offset. Pointer full credit beyond the seed's skew noise floor (0.10). Weakest item decides; absent items are skipped (charged by 6). | text_mirrored_incorrectly |
| 6 | text and logos preserved (1.0) | "any text, logos … must remain legible" | Share of each seed label's (START, SELECT, L, R) and symbol's (□△✕) engraved area found again, any orientation | `score_ratio(f, 0.90, 0.25)`; weakest item decides. Under a quarter of a label is illegible. | missing_glyphs, unwidened |
| 7 | no unrequested changes (0.5) | implicit: only the asked-for edits | Min of four parts. (a) Shape of the bodies the edit leaves alone (fingerprint distance). (b) Their y/z, plus u for the two bodies on the plane. (c) Housing Y/Z spans. (d) Housing top height map vs the seed's, warped by h. Masked: the seam, swapped features, control footprints, slopes > 45°, silhouettes. | (a) `score_err(d, 0.01, 0.08)`: unchanged B-rep repeats to 1e-5, 1 % is the smallest deliberate resize. (b, c) `score_err(·, 0.5, 5)` mm. (d) Cells deviating by more than t = 0.1115 mm (p99 of the seed's own left/right map noise), area `score_err(A, A_letter, 10·A_letter)`, A_letter = 4.97 mm² (median START/SELECT letter face). | unrequested_change_elsewhere, unwidened |
| 8 | rebuilds cleanly (0.5) | task.toml: "preserving design intent and feature tree references" | After `EditRebuild3`: new failing features + sketches over-defined / no solution / invalid + ½ × new warnings, counted, never matched by name | `score_err(n, 0, 0.05 × 199)`: the seed rebuilds with none, so every one was introduced; 5 % of the tree broken is "riddled". | feature_tree, unwidened |

The asked-for edits (1–4) carry 7.0, the named constraints (5–6) 2.0 and
the implicit ones (7–8) 1.0. A do-nothing part scores 3.0.

## 3. What changed in the harness, and why

### Measurement
- **Extents from `IBody2.GetExtremePoint`**, not `GetBodyBox`. The API docs
  call `GetBodyBox` approximate, and on the seed housing it is 2.6 mm loose.
  It fed v2's Y/Z span check and its cluster plan shapes.
- **Width is measured on the shell, not on the controls.** v2's C1 was the
  growth of the stick/trigger/bumper separation, so a shell widened with
  its controls left in place read as "not widened".
- **Ray sections.** v3 casts +X rays through the housing with the
  documented `swRayPtsOpts` values (NORMALS 1 | ENTRY_EXIT 4). Every hit
  is validated as lying on its own ray to within 10 µm before it is read.
  `common/solidworks_rays.py` has the two option values swapped and is not
  used.
- **Engraving faces and height maps.** Each face below 15 mm² is recorded
  by area, tessellated centroid and normal (`IFace2.GetTessTriangles`).
  The housing's tessellation is rasterised into top, bottom, front and back
  height maps at 1 mm cells. Each body's x-skew is recorded too.
- **Rebuild.** The saved part is brought up to date with `EditRebuild3`
  and measured as saved. `ForceRebuild3` runs last, repeated until its
  census is stable, as an unscored diagnostic (see decision 1).
- **Every part is measured from disk.** `open_document` reuses a document
  that is already open, and a rebuild mutates it. `open_fresh` closes all
  documents first, and the baseline commands close theirs afterwards.

### Identity (no names, no order)
- Housing: every body spanning ≥ 35 % of the part's X extent. The seed's
  housing spans 100 %, its widest control 11 %, and the reference splits
  the shell into two.
- Kept bodies (sticks, triggers, bumpers, the two small bodies on the
  plane) are matched by shape fingerprint under an optimal assignment.
  Fingerprint = volume, area and sorted principal moments. Assignments are
  rejected beyond half the smallest distance between two different seed
  roles (0.068).
- Button clusters: crosses of four congruent bodies. The d-pad is the one
  with elongated arms. Structural, because the reference rebuilds both
  clusters (decision 2).
- START/SELECT: scale-invariant shape, within the band between the seed
  position and the mirrored position carried outboard by h.
- Frame: P is the candidate's own grip-lobe midline, h its own half
  separation growth. Y/Z are aligned on the housing's extent minimum.

### Scoring
- No gates. v2 zeroed all geometry on any new tree error. The modelling-
  hygiene component is now report-only.
- Removed, because they are tuned to the reference rather than derived:
  `cluster_perfect_mm = 4.0`, `span_perfect_mm = 2.0` and
  `suppressed_perfect = 1`.
- Removed, because something more direct replaces them:
  - the port-light, housing-moment and detail-side witnesses (criterion 5 reads the labels themselves);
  - the small-face count (criterion 6 reads the engraved area).

### CLI and files
- `--batch` finds `examples/<name>/<name>.SLDPRT`. v2 globbed
  `examples/*.SLDPRT` and silently skipped all eight. The batch order is the
  seed, the reference, then `task.toml`'s examples.
- `--score-from` prints each part's readable summary once (it was printed
  twice).
- **`tests/task/prompt/input.json` was re-frozen twice.**
  - At stage C (`/5`), to add the measurements v3 reads: engraving faces, height maps and skews.
  - Now (`/6`), to drop two v2 fields nothing reads any more.

  Both times, every field shared with the previous file came back
  identical once body ids were mapped by centroid (`GetBodies2` order
  differs between sessions): volumes and areas to 1.5e-14 relative,
  centroids to 7e-17 m. The 448 engraving faces, the skews and the height
  maps are bit-identical.
- `task.toml`: `max_score = 10.0`. The notes are rewritten; they described
  v2 and a `load_scoring_weights` function that does not exist.
- `README.md` is rewritten for 3.0.0. `tests/test.sh` and
  `solution/solve.sh` now say 10.0 ("5/5" and 7.0 before).
- New: `tests/task/harness/test_harness.py` and `fixtures/`, the ten
  captures from the final run plus a second live capture of the reference.
- Measuring takes 110–125 s per edited part (24 s for the seed), inside
  `task.toml`'s 300 s verifier timeout. Two thirds of that is the unscored
  forced-rebuild diagnostic: three `ForceRebuild3` passes, 74–83 s. The
  rest is mostly 187 rays through the shells (19 s). Dropping the
  diagnostic would cut a part to about 45 s and change no score. Scoring
  takes about 3 s.

## 4. Decisions and stop-rule events

**Decided after stopping with the evidence:**

1. **Rebuild mode.** `ForceRebuild3` is not idempotent on these files. The
   reference settles at two failing DeleteFace features plus two warnings.
   The seed's first forced pass after opening fails 18 features. → Score
   the incremental census; keep the forced rebuild as an unscored
   diagnostic.
2. **The reference rebuilds its buttons.** Face buttons are −53 % volume,
   d-pad arms +66 %. Its 3 mm "cluster residual" is in Y only; x agrees to
   0.1 mm. → Structural cluster identity, y/z drift reported, not scored.
3. **The reference shells and splits the housing** and adds two screws,
   four LED domes and a PS button three times the size. → Criterion 7
   reads the outer shell and the kept bodies. Added hardware is reported.

**Decided during the overnight run (to review).** Each one keeps the
reference at full marks without a reference-only number:

4. **START pointer.** The reference's rebuilt START button skews 0.139 in
   x, the seed's 0.252; same sign. → Score the sign, with full credit from
   the seed's skew noise floor (0.10). The magnitude is not scored. A
   magnitude rule would have cost the reference.
5. **SELECT text 1.53 mm inboard of the exact mirror** in the reference. →
   The text-position perfect band is one letter pitch of the seed's own
   lettering (3.216 mm, the smallest gap between adjacent letters). A label
   moved by less than a letter still sits by the same button.
6. **The reference remodels the housing's bottom, front and back** (the
   shell parting line, rear LED windows, shoulder openings) and its stick
   openings on top. → Score the top view only, with each control's
   footprint masked (the housing under a control is its seat). The other
   three views are compared and reported.
7. **Orientation margin.** Mirrored/rotated readings are judged against
   half the seed's own smallest margin between its true reading and its
   mirror or rotation (M = 0.199, from L). Symbol side is ramped over one
   button offset rather than snapped. Partially lost labels (as in
   feature_tree) therefore read as partial, not as flipped.
8. **Engraving matching is position-led.** Strict 2 % area matching found
   only 60 % of the regenerated R/L labels in widened_15mm. Each seed face
   now takes credit from the nearest candidate face within 0.3 mm, if its
   area is within 2×.
9. **Criterion 7's height threshold.** It was the seed's shallowest
   engraving (0.586 mm), but the slot in unrequested_change_elsewhere is
   only 0.19 mm deep. → t = the 99th percentile of the seed's own
   |map − mirror(map)| over its symmetric surface: the method's noise,
   since the two halves are tessellated independently. That is 0.1115 mm
   on top.
   - On the seed's symmetric surface: p50 0.001, p90 0.021, p99 0.110, p99.9 0.370 mm.
   - At t = 0.10 or 0.12 mm, every model shows 0 deviation cells except that slot (300 / 301 mm²).
   - The reference shows 20 cells at 0.08 mm and none from 0.10 mm.

   p99.9 (0.37 mm) would miss the slot.
10. **Bug found while writing the tests: `translate_yz`.** It moved the
    height maps' origin but not the heights they store, which are absolute
    y and z. A reference moved 5 mm in Y would have scored 9.5 (criterion
    7 = 0). Fixed; a test moves the reference in X, Y and Z and asserts
    10.0. No capture in the corpus was affected: every frame offset is
    ≤ 0.002 mm.

## 5. adversarial_feature_tree_with_errors

- **Rebuild: 0.00.** `EditRebuild3` leaves 15 new failing features and 3
  new warnings:
  - Cut-Extrude24, DeleteFace33/34/37/41–46, Fillet64/76/80/86, Mirror8 fail;
  - Boss-Extrude18, Fillet47 and Sketch123 warn.

  Counted: 15 + ½·3 = 16.5, beyond the zero at 9.95. No sketch is in an
  error state (29 under-defined, 35 fully defined). Unscored, forced
  rebuilds stabilise after 3 passes at 17 failing features and 5 warnings,
  and the body volumes move by 63.6 mm³.
- **Geometry, graded as rebuilt:**
  - **width 0.00:** the grips are 30.0 mm apart and the body is 30.4 mm wider, against +15.
  - **re-spacing 0.16:** the d-pad arms rebuild round, so no d-pad cross exists. The face buttons sit 0.88 mm from their target (for its own h = 15 mm), their spacing drifts 2.13 mm, and new interference is 2,047 mm³.
  - **swap 0.50:** the face buttons are on the correct side; the d-pad is missing.
- START/SELECT, labels, symbols and the housing surface are all intact
  (1.00).

## 6. Acceptance criteria — evidence

1. **The reference scores full marks:** 10.000/10.0, `passed: true`, in
   the final batch. It scores the same again in a separate single-part
   live run (`harness.py solution\solution.SLDPRT`).
   - The two live captures agree to floating-point round-off: volumes 1.2e-15 relative, centroids 6e-17 m.
   - Their engraving faces, height maps, ray hits and rebuild census are bit-identical.

   `Corpus.test_reference_full_marks` and
   `Determinism.test_second_live_capture_of_the_reference` check this.
2. **Each example loses only on what it gets wrong.** See the table and
   section 1. `Corpus.test_each_example_loses_only_what_it_gets_wrong`
   asserts the exact set of criteria below 1.0 for every model.
3. **Geometry only.** No name, id, body order or tree structure is read.
   - Shuffled body order with new ids and names scores identically (`test_body_order_ids_and_names`).
   - So does a reference moved ±20 mm in X, 5 mm in Y and Z, or one grip moved 15 mm (`test_origin_moved`).
   - So do rebuilt buttons (±5 % size), clusters jittered within tolerance, and START/SELECT at either end of the mirrored band.
   - Nothing is keyed on a file name or hash. Batch labels only name output files.
4. **Continuous components.** Every criterion is a clamped linear ramp,
   a product of ramps, or a minimum of ramps. The corpus shows partial
   values:
   - 0.16 and 0.50 (feature_tree);
   - 0.02, 0.12, 0.50 and 0.85 (unwidened);
   - 0.50 (only_one).

   The controls in the tests produce others:
   - re-spacing 0.83, when two of the six followers are left behind;
   - width 0.40, for a seed housing X-scaled to the same +15 mm. Its grips
     separate by only 8.9 mm, and its lobes widen by 2.93 mm, exactly the
     scale's signature.
   `max_score` = Σ weights = 10.0 (`Documents.test_task_toml_max_score`).
5. **Envelope shape.** `finalize()` is unchanged and called as before. The
   single-part live run printed exactly one envelope on stdout, with the
   keys `task_id`, `score`, `max_score`, `passed`, `subscores` and
   `harness_version`; the readable summary went to stderr. It is copied
   in `README.md`.
6. **CHANGES and tables:** this file. `README.md` carries the rubric and
   the corpus table.

`python -m unittest discover -s tests/task/harness -v`: 20 tests, all
passing, in 46 s. The fixtures are the eleven gzip captures from the final
run, 3.7 MB in total. Nearly all of that is the housing height maps,
about 0.3 MB per part, which do not compress further.

## 7. Not verifiable, or uncertain

- **Handedness of △, ✕ and the joystick caps.** They match their own
  mirror (stick x-skew 0.000), so a flipped copy is the same geometry.
  They are reported as achiral. □ and all four text labels are chiral, and
  they are graded.
- **○ is not read.** None of its faces is below the 15 mm² engraving-scale
  ceiling. A candidate that loses only the circle would not lose
  criterion 6.
- **The L1/L2 ↔ R1/R2 assignment swap.** The shoulder bodies are mirror
  pairs of one shape, so the swap has no geometric signature.
- **A label re-cut with a different face split.** Matching is face by face
  (2× area, 0.3 mm), so a label whose faces split differently would be
  under-counted by criterion 6. No model in the corpus does this.
- **Height-map margin.** Criterion 7's t = 0.1115 mm sits just above the
  reference's largest top-view deviation (< 0.10 mm) and below the 0.19 mm
  slot. A valid model remodelled more heavily than the reference near the
  top surface could cross it.
- **A re-oriented part.** The frame is the seed's axes; a rotated part is
  not re-aligned.
- **Ergonomics.** Whether the clusters are within thumb reach is
  `task.toml`'s judged question, not a dimension.
- **Grid phase.** The corpus covers both alignments of the 1 mm map grid
  against the seed's: h = 7.5 mm gives half a cell (reference and most
  examples), and h = 15 mm gives a whole cell (feature_tree). Other phases
  are not exercised.

## 8. Found outside the harness (not edited)

- `common/solidworks_rays.py`: `RAY_ENTRY_EXIT = 2` and `RAY_TOPOLS = 4`.
  The documented `swRayPtsOpts_e` values are 4 and 2.
- `common/solidworks_capture.modelling_census` calls
  `ListExternalFileReferences` (nine out-parameters) and `GetDependencies2`
  (three arguments) with no arguments. External references therefore
  always read "unavailable".
- `common/solidworks_session.open_document` returns an already-open
  document of the same path, in whatever state an earlier run left it.
  The harness works around this with `open_fresh`.
- `tests/task/reference/solution.{STL,png}` are byte-identical to
  `adversarial_missing_glyphs.*`; `task.toml` lists the same sha256 for
  both. Grading does not use them.
- `test_example/.mcp.json` has unescaped `\` in its Windows paths, so it is
  not valid JSON and the `solidworks-api` server does not start from it.
  The COM signatures were checked against the same documentation corpus
  on disk instead.

## Inconsistencies in the task docs, resolved

| was | now |
|---|---|
| `max_score` 8.0 (toml), 7.0 (README, test.sh), "5/5" (solve.sh) | 10.0 everywhere, from `ALL_CRITERIA`; a test keeps toml and code equal |
| README 2.1.5 vs code 2.3.1 | 3.0.0 in both; a test checks the README names the version |
| README cites `tools/selftest_synthetic.py` (absent) | Not recreated. The README points to `test_harness.py` |
| README's adversarials vs what was fetched | All eight are present, and their hashes match `task.toml`. The batch corpus is `task.toml`'s `[metadata.examples]` |
