# Research Matching Upgrade Report

Date: 2026-02-14

## Objective
Upgrade the skill matching pipeline from simple overlap scoring to a more research-aligned approach for real-world job matching behavior.

## Files Changed
- `RP-Server/CV_extractor/job_skill_pipeline.py`
- `RP-Server/CV_extractor/skill_config.py`

## Implemented Improvements
1. Skill normalization + canonicalization
- Added alias-to-canonical mapping using `SKILL_LEXICON`.
- Added fuzzy canonicalization fallback (RapidFuzz, threshold `92`) for noisy inputs.
- Effect: user skills like `nodejs` can map to canonical `node.js`.

2. Must-have vs nice-to-have modeling
- Added section-level inference for skill priority:
  - Must-have hints: `requirements`, `must`, `core skills`, `technical skills`, `qualification`, etc.
  - Nice-to-have hints: `preferred`, `bonus`, `nice to have`, etc.
- Produced new fields:
  - `must_have_skills`, `nice_to_have_skills`, `core_skills`
  - `matched_must_have`, `missing_must_have`
  - `must_have_gate_pass`, `must_have_gate_reason` (via explanations)

3. Weighted multi-factor score
- Added weighted score components:
  - `must_have_coverage` (45%)
  - `core_weighted_coverage` (35%)
  - `nice_to_have_coverage` (15%)
  - `signal_coverage` (5%)
- Added IDF-style weighting across jobs for core-skill coverage.
- Final score:
  - Blend of old baseline overlap and weighted score:
    - `final = 0.2 * baseline + 0.8 * weighted`
  - If must-have gate fails, weighted score is penalized.

4. Explainability
- Added `explanations` per ranked job to justify score and failures.
- Added `weighted_components` to expose scoring internals.

5. Backward compatibility
- Preserved existing fields used by frontend/backend:
  - `match_percent`, `missing`, `skills_found`, `job_skill_count`, etc.
- Existing API consumers sorting by `match_percent` continue to work.

6. Section coverage expansion
- Extended `SECTION_HEADERS` in `skill_config.py` with common hiring headers:
  - `must-have`, `mandatory requirements`, `preferred qualifications`, `good to have`, etc.

## Validation Run
Command executed:
```powershell
py RP-Server\CV_extractor\job_skill_pipeline.py `
  --scraped_folder RP-Server\scr_output\topjobs_ads `
  --user_skills "python,sql,fastapi,django,docker,kubernetes,aws,react,javascript,git,linux" `
  --out_json ranked_jobs.research.json
```

Output file:
- `RP-Server/scr_output/topjobs_ads/ranked_jobs.research.json`

Quick run statistics:
- Jobs ranked: `39`
- Average final score (`match_percent`): `32.66`
- Average baseline score (`baseline_match_percent`): `18.98`
- Jobs with detected must-have section skills: `14`
- Gate-failed jobs: `13`

## Research Notes
- The new score is still heuristic (not a supervised ranker).
- It is now significantly closer to a real-world candidate-job fit setup:
  - priority-aware matching
  - gating behavior
  - rarity-weighted coverage
  - explainable outputs

## Suggested Next Research Steps
1. Add labeled relevance data (`cv, job -> relevance`) and evaluate with `nDCG@K`, `MAP`, `Precision@K`.
2. Run ablations:
- remove must-have gate
- remove IDF weighting
- remove fuzzy canonicalization
3. Add semantic similarity model (embeddings) as an additional score component.
