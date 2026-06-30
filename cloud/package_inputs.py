"""package_inputs.py — build the cloud benchmark bundle (run LOCALLY).

Picks ONE 2D image per furniture type, using the SAME `*_input.png` inputs and `*_abo.glb`
ground-truth meshes that TripoSR was already tested on locally — so the cloud models
(TripoSG / TRELLIS / InstantMesh) are compared on *identical data* with the *identical metric*.

Only types that have FULL local TripoSR coverage (input + abo + sam2 + rembg GLBs) are chosen,
so every row in the final table also carries the TripoSR·SAM2 and TripoSR·rembg baselines.

Produces:
  deliverable/cloud_bundle/            -> staged bundle (inputs/, gt/, scripts, manifest.json)
  deliverable/cloud_bundle.tar.gz      -> upload THIS to the pod
  deliverable/local_scoring_manifest.json -> drives the unified LOCAL re-scoring of every model
"""
import json, shutil, tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUTPUTS = REPO / "outputs"
BUNDLE_SRC = REPO / "cloud" / "bundle"
STAGE = REPO / "deliverable" / "cloud_bundle"
EVAL_PY = REPO / "backend" / "python-scripts" / "eval_accuracy.py"

# prefer clean ABO renders first, then the other rounds
FOLDER_ORDER = ["abo_test", "abo_test_random", "abo_test_cats",
                "abo_test_realphoto", "abo_test_polyhaven", "abo_test_objaverse"]

def load_scores(folder):
    p = OUTPUTS / folder / "scores.json"
    if not p.exists():
        return {}
    return {r["base"]: r for r in json.loads(p.read_text(encoding="utf-8")).get("rows", [])}

chosen = {}   # type -> dict
for folder in FOLDER_ORDER:
    d = OUTPUTS / folder
    rj = d / "results.json"
    if not rj.exists():
        continue
    scores = load_scores(folder)
    for r in json.loads(rj.read_text(encoding="utf-8"))["results"]:
        t = r["type"]
        if t in chosen:
            continue
        base = r["base"]
        files = {s: d / f"{base}_{s}" for s in
                 ("input.png", "abo.glb", "sam2.glb", "rembg.glb")}
        if all(f.exists() for f in files.values()):
            sc = scores.get(base, {})
            chosen[t] = {
                "type": t, "folder": folder, "base": base,
                "source_id": r.get("source_id", ""),
                "files": files,
                "triposr_sam2_f": (sc.get("sam") or {}).get("fscore"),
                "triposr_rembg_f": (sc.get("rem") or {}).get("fscore"),
            }

assert chosen, "no fully-covered items found — check outputs/abo_test*/"

# ---- stage the bundle (inputs + GT + scripts) -------------------------------
if STAGE.exists():
    shutil.rmtree(STAGE)
(STAGE / "inputs").mkdir(parents=True)
(STAGE / "gt").mkdir(parents=True)

manifest = []           # for the POD (relative paths)
local_manifest = []     # for LOCAL unified scoring (absolute local paths)
for t, c in sorted(chosen.items()):
    key = t
    shutil.copy(c["files"]["input.png"], STAGE / "inputs" / f"{key}.png")
    shutil.copy(c["files"]["abo.glb"], STAGE / "gt" / f"{key}.glb")
    manifest.append({"key": key, "type": t, "source_id": c["source_id"],
                     "input": f"inputs/{key}.png", "gt": f"gt/{key}.glb"})
    local_manifest.append({
        "key": key, "type": t,
        "gt": str(c["files"]["abo.glb"]),
        "triposr_sam2_glb": str(c["files"]["sam2.glb"]),
        "triposr_rembg_glb": str(c["files"]["rembg.glb"]),
        "triposr_sam2_f_local": c["triposr_sam2_f"],
        "triposr_rembg_f_local": c["triposr_rembg_f"],
    })

(STAGE / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

# bundle the pod-side scripts + the validated metric (no code duplication)
for p in BUNDLE_SRC.glob("*"):
    if p.is_file():
        shutil.copy(p, STAGE / p.name)
shutil.copy(EVAL_PY, STAGE / "eval_accuracy.py")

# ---- tarball for the pod ----------------------------------------------------
tar_path = REPO / "deliverable" / "cloud_bundle.tar.gz"
with tarfile.open(tar_path, "w:gz") as tar:
    tar.add(STAGE, arcname="cloud_bundle")

# ---- local scoring manifest (TripoSR baselines + where cloud GLBs will land) -
(REPO / "deliverable" / "local_scoring_manifest.json").write_text(
    json.dumps(local_manifest, indent=2), encoding="utf-8")

mb = tar_path.stat().st_size / 1e6
print(f"chosen {len(chosen)} furniture types: {', '.join(sorted(chosen))}")
print(f"bundle staged: {STAGE}")
print(f"tarball:       {tar_path}  ({mb:.1f} MB)  <- upload this to the pod")
print(f"local scoring: deliverable/local_scoring_manifest.json")
