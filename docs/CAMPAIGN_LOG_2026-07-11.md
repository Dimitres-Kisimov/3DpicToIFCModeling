
## Final state — 2026-07-12 15:20 local

Catalog: 605 engine-badged IFC-gated items (TSG 196, TRL 197, SF3D 192, SAM3D 10, IM 10).
Per-AI IFC folders: instantmesh, sam3d, sf3d, trellis, triposg. Gate pass rate final pass: 30/40
(rejections per engine in benchmark/ingest_report.csv). Pod: stopped at zero balance; Study E +
3DTopia-XL logs + any late meshes recoverable from the volume via top-up. TRELLIS 2.0: software
proven (PIPELINE_OK), awaiting Meta DINOv3 grant. Visualizer: 998 variants; 11 list pages with
engine columns; 8-way TSG upgrade menu awaiting user votes.

## Hourly check — 2026-07-12 21:45 local — CAMPAIGN CLOSED, cron retiring

Pod ssh: connection refused (instance stopped at zero balance 2026-07-12 ~15:00; volume retained).
No new markers possible; final markers on record: CAMPAIGN_FULLY_COMPLETE, SAM3D_CAMPAIGN_COMPLETE.
TRELLIS 2.0 remains blocked ONLY on the Meta DINOv3 grant (still pending) — retry scripts are
committed and armed on the volume. Completion condition of this hourly job is therefore met.

This push lands the last local campaign artefacts: lists 01-11 + candidates.json (engine columns,
641 new candidate entries), 596 engine render thumbnails (45 MB), and the per-AI IFC folders
benchmark/ifc/{triposg,trellis,sf3d,sam3d,instantmesh} (139 MB, all IFC4-gate survivors).
Hourly campaign-push job DELETED after this final push. DINOv3 hourly gate check continues separately.
