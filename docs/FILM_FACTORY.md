# Film Factory (Zynorva) — OpenMontage + Muse2

Implements the Zahna postmortem architecture on this OpenMontage fork.

## Layout

| Path | Role |
|------|------|
| `lib/film_factory/` | First-frame roles, aspect DAR gate, assemble policy, take storage, state ledger, series manager, prompt packs, QA tiers |
| `tools/video/muse2_video.py` | Muse2 adapter → local muse2api |
| `tools/video/pass_only_assemble.py` | PASS-only gate before FFmpeg/Remotion compose |
| `tools/analysis/frame_integrity_scan.py` | One-frame sheet/board flash heuristics |
| `tools/analysis/visual_qa_film.py` | PASS/REVIEW/FAIL scoring |
| `tools/analysis/audio_qa_asmr.py` | ASMR audio checks |
| `packs/<category>/v1/` | Versioned PromptPacks |
| `packs/projects/<id>/` | Project overlays (cast/hardcode/bible) |
| `pipeline_defs/*-{asmr,observational,cartoon}.yaml` | Channel pipelines |
| `tests/film_factory/` | Regression gates |

## Env

```
MUSE2API_BASE_URL=http://127.0.0.1:18610
MUSE2API_KEY=...
```

## Smoke

```bash
python scripts/film_factory/smoke_muse2.py          # dry-run
python scripts/film_factory/smoke_muse2.py --live   # one real Muse clip (uses quota)
pytest tests/film_factory -q
```

## Deferred

Channel account binding (6 Muse / 2 per channel) — after workflow proves out.
