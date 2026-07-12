"""
ingest_pod_results.py — bring a pod run home: visualizer candidates + catalog entries.

Takes the extracted pod results (out/ research-10 and/or out170/ 10x17 sweep) and:

1. VISUALIZER — copies every out170/<model>/listNN_<category>.glb into
   benchmark/results/listNN/<category>/<model>.glb, then rebuilds candidates.json,
   so each AI appears as a labelled, emblem-badged candidate next to TripoSR
   raw/improved (compare against TripoSG — it sorts right after "ours").

2. CATALOG (IFC-gated) — for every mesh, runs the app's real post-generation
   pipeline: archetype repair packs -> saveIFC (the app's exporter) -> IFC4
   validation. ONLY meshes whose IFC export passes get copied into
   data/generated_assets/ and appended to its manifest with the engine badge
   (TSG / TRL2 / SAM3D / SF3D / TRL / IM) the picker shows. Non-compliant meshes
   are reported and skipped — nothing enters the catalog unverified.

Usage (after scp'ing and extracting results_*.tar.gz from the pod):

    python ingest_pod_results.py <results_root> [--dry-run] [--limit-per-category N]

<results_root> is the folder holding out/ and/or out170/. Idempotent: items
already in the generated-assets manifest (id pod_<model>_<key>) are skipped.
"""
from __future__ import annotations
import argparse, csv, json, re, shutil, sys, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent          # benchmark/
REPO = HERE.parent
SCRIPTS = REPO / "backend" / "python-scripts"
GEN_DIR = REPO / "data" / "generated_assets"
GEN_MANIFEST = GEN_DIR / "manifest.json"
RESULTS = HERE / "results"
IFC_DIR = HERE / "ifc"                           # per-AI IFC folders: ifc/<engine>/<key>.ifc

sys.path.insert(0, str(SCRIPTS))
import trimesh                                   # noqa: E402
from repair_packs import repair_mesh             # noqa: E402
import saveIFC                                   # noqa: E402

# engine badge codes, same vocabulary as room_api's picker badge (<=8 chars)
ENGINE_BADGE = {"triposr": "TSR", "triposg": "TSG", "trellis": "TRL",
                "trellis2": "TRL2", "instantmesh": "IM", "sam3d": "SAM3D",
                "sf3d": "SF3D"}
KEY170 = re.compile(r"^(list\d+)_(.+)$")         # list01_bookshelf -> (list01, bookshelf)


def _ifc_valid(path: Path) -> tuple[bool, str]:
    """IFC4 compliance gate. ifcopenshell parse when available, header sniff as fallback."""
    if not path.exists() or path.stat().st_size < 5000:
        return False, "missing or too small"
    try:
        import ifcopenshell
        f = ifcopenshell.open(str(path))
        if not f.schema.startswith("IFC4"):
            return False, f"schema {f.schema}, expected IFC4"
        if not f.by_type("IfcFurniture") and not f.by_type("IfcFurnishingElement"):
            return False, "no furniture product in file"
        return True, f"IFC4 ok ({len(f.by_type('IfcProduct'))} products)"
    except ImportError:
        head = path.read_bytes()[:2048].decode("ascii", errors="ignore")
        ok = "FILE_SCHEMA(('IFC4" in head
        return ok, "header sniff (ifcopenshell not installed)" if ok else "no IFC4 header"
    except Exception as e:
        return False, f"parse error: {e}"


def _render_thumb(glb: Path, dest: Path) -> str | None:
    """Reuse the app's thumbnail renderer when importable; None is fine (badge is the signal)."""
    try:
        import room_api
        if room_api._render_thumb(glb, dest):
            return dest.name
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results_root", help="folder containing out/ and/or out170/ from the pod")
    ap.add_argument("--dry-run", action="store_true",
                    help="run repair + IFC gate and report, but write nothing permanent")
    ap.add_argument("--limit-per-category", type=int, default=0,
                    help="cap catalog inserts per (engine, category); 0 = no cap")
    args = ap.parse_args()
    root = Path(args.results_root).resolve()

    # ---- collect meshes: (model, key, list_name|None, category, glb_path)
    meshes = []
    for sub, is170 in (("out170", True), ("out", False)):
        base = root / sub
        if not base.is_dir():
            continue
        for mdir in sorted(p for p in base.iterdir() if p.is_dir()):
            for glb in sorted(mdir.glob("*.glb")):
                m = KEY170.match(glb.stem)
                if is170 and m:
                    meshes.append((mdir.name, glb.stem, m.group(1), m.group(2), glb))
                else:
                    meshes.append((mdir.name, glb.stem, None, glb.stem, glb))
    if not meshes:
        sys.exit(f"no out/ or out170/ model GLBs under {root}")
    print(f"found {len(meshes)} meshes from models: "
          f"{sorted({m[0] for m in meshes})}")

    # ---- 1. visualizer drop (raw pod mesh, so the gallery compares generators fairly)
    dropped = 0
    for model, key, lst, cat, glb in meshes:
        if not lst:
            continue
        dest = RESULTS / lst / cat / f"{model}.glb"
        if not args.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(glb, dest)
        dropped += 1
    print(f"visualizer: {dropped} candidate meshes -> benchmark/results/ "
          f"{'(dry-run, not copied)' if args.dry_run else ''}")

    # ---- 2. IFC-gated catalog ingestion
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        man = json.loads(GEN_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        man = {"items": []}
    have = {e.get("id") for e in man.get("items", [])}
    work = HERE / "_ingest_work"
    work.mkdir(exist_ok=True)
    per_cat: dict[tuple, int] = {}
    rows, added = [], 0

    for model, key, lst, cat, glb in meshes:
        uid = f"pod_{model}_{key}"
        row = {"id": uid, "model": model, "category": cat, "repair": "", "ifc": "", "catalog": ""}
        rows.append(row)
        if uid in have:
            row["catalog"] = "already ingested"
            continue
        capkey = (model, cat)
        if args.limit_per_category and per_cat.get(capkey, 0) >= args.limit_per_category:
            row["catalog"] = "category cap"
            continue
        try:
            mesh = trimesh.load(glb, force="mesh")
            faces_in = len(mesh.faces)
            mesh, _rep = repair_mesh(mesh, label=cat, category=cat)
            rglb = work / f"{uid}.glb"
            mesh.export(rglb)
            row["repair"] = f"ok {faces_in}->{len(mesh.faces)}f"
        except Exception as e:
            row["repair"] = f"FAIL {e}"
            continue
        ifc = work / f"{uid}.ifc"
        try:
            saveIFC.save_ifc_project([{"glbPath": str(rglb), "name": key, "category": cat,
                                       "ifc_class": "IfcFurniture"}], str(ifc))
        except Exception as e:
            row["ifc"] = f"FAIL export {e}"
            continue
        ok, why = _ifc_valid(ifc)
        row["ifc"] = ("ok " if ok else "FAIL ") + why
        if not ok:
            row["catalog"] = "rejected — not IFC compliant"
            continue
        if not args.dry_run:                     # per-AI IFC folder, compliant files only
            dest_ifc = IFC_DIR / model / f"{key}.ifc"
            dest_ifc.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ifc, dest_ifc)
        if args.dry_run:
            row["catalog"] = "would add (dry-run)"
            per_cat[capkey] = per_cat.get(capkey, 0) + 1
            continue
        fn = f"{uid}.glb"
        shutil.copy2(rglb, GEN_DIR / fn)
        ext = mesh.extents
        thumb = _render_thumb(GEN_DIR / fn, GEN_DIR / f"{uid}.thumb.png")
        man.setdefault("items", []).append({
            "id": uid, "category": cat, "glb": fn,
            "dims_m": [round(float(v), 4) for v in ext] if ext is not None else None,
            "thumb": thumb, "generated": True,
            "source_file": str(glb),
            "engine": ENGINE_BADGE.get(model, model.upper()[:8]),
        })
        per_cat[capkey] = per_cat.get(capkey, 0) + 1
        added += 1
        row["catalog"] = "added"
        if added % 25 == 0:                      # progressive flush — items appear in the
            GEN_MANIFEST.write_text(json.dumps(man, indent=1), encoding="utf-8")
            print(f"[ingest] {added} in catalog so far", flush=True)

    if not args.dry_run:
        GEN_MANIFEST.write_text(json.dumps(man, indent=1), encoding="utf-8")
    report = HERE / "ingest_report.csv"
    with report.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "model", "category", "repair", "ifc", "catalog"])
        w.writeheader()
        w.writerows(rows)
    passed = sum(1 for r in rows if r["ifc"].startswith("ok"))
    print(f"IFC gate: {passed}/{len(rows)} passed · catalog: {added} added "
          f"{'(dry-run)' if args.dry_run else ''} · report: {report}")
    if not args.dry_run and dropped:
        import subprocess
        subprocess.run([sys.executable, str(HERE / "build_candidates.py")], check=False)


if __name__ == "__main__":
    main()
