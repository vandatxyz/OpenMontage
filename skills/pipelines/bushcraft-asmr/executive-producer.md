# Executive Producer — Bushcraft ASMR (Muse2 Film Factory)

## When to Use

Orchestrate photoreal **solo bushcraft / survival ASMR** episodes using OpenMontage + **muse2_video**.

## Film-factory locks

- Category pack: `bushcraft_asmr` @ `v1` (`packs/bushcraft_asmr/v1`)
- Project overlay: `solo_survival`
- Video tool: **only** `muse2_video` (provider `muse2`) — never auto-select Kling/Seedance for this pipeline
- First Frame Controller: semantic roles; Mode A/B/C; sheets never Image 1
- Aspect: episode `16:9`; wrong DAR → FAIL; same DAR different res → normalize
- Assemble: PASS only (REVIEW needs human `approved`)
- Minimal State Ledger before multi-clip chains

## Stage flow

script → scene_plan → assets → generate (muse2 + integrity + visual QA + audio QA) → compose (PASS-only)

## Tools

- `muse2_video`, `frame_integrity_scan`, `visual_qa_film`, `audio_qa_asmr`
- Compose via existing `video_compose` / `video_stitch` after `filter_pass_clips`

## Do not

- Run 120-clip batches before regression gates pass
- Fall back to cartoon draft prompts
- Promote planned state to validated without evidence
