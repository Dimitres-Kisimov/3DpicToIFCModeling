"""
Sprint 8 — End-to-end pipeline test runner
Tests each model adapter with a synthetic test image and validates output.

Usage:
  python test_pipeline.py [--model triposr|instantmesh|trellis|hunyuan3d|all]
                          [--image path/to/image.jpg]
                          [--output-dir ./test_outputs]

Exit code 0 = all selected tests passed
Exit code 1 = one or more tests failed
"""

import sys
import os
import json
import time
import argparse
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

MODELS_DIR   = Path(__file__).parent.parent.parent / "models"
SCRIPTS_DIR  = Path(__file__).parent

MODELS = ["triposr", "instantmesh", "trellis", "hunyuan3d"]


def _create_test_image(output_path, size=256):
    """Create a solid-colour test PNG if no real image is provided."""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (size, size), (180, 140, 100))
        draw = ImageDraw.Draw(img)
        # Draw a simple chair silhouette outline
        draw.rectangle([60, 80, 190, 200], outline=(50, 40, 30), width=4)
        draw.rectangle([60, 60, 190, 90],  fill=(130, 100, 70))
        draw.line([70, 200, 70, 240],  fill=(50, 40, 30), width=6)
        draw.line([180, 200, 180, 240], fill=(50, 40, 30), width=6)
        img.save(output_path)
        return True
    except ImportError:
        print("[WARN] Pillow not available — cannot create test image", file=sys.stderr)
        return False


def _run_script(script, args, timeout=300):
    """Run a Python script and return (success, stdout_data, stderr, elapsed)."""
    import subprocess
    cmd = [sys.executable, str(SCRIPTS_DIR / script)] + args
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        elapsed = time.time() - t0
        try:
            data = json.loads(proc.stdout)
        except Exception:
            data = {"raw": proc.stdout}
        return proc.returncode == 0, data, proc.stderr, elapsed
    except subprocess.TimeoutExpired:
        return False, {}, "TIMEOUT", time.time() - t0


def test_model(model, image_path, output_dir):
    script_map = {
        "triposr":    "run_triposr.py",
        "instantmesh":"run_instantmesh.py",
        "trellis":    "run_trellis.py",
        "hunyuan3d":  "run_hunyuan3d.py",
    }
    script = script_map.get(model)
    if not script:
        return {"model": model, "status": "skip", "reason": "unknown model"}

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    out_glb = str(Path(output_dir) / f"test_{model}_{int(time.time())}.glb")

    print(f"\n[TEST] {model}: {script}")
    ok, data, stderr, elapsed = _run_script(script, [image_path, out_glb], timeout=600)

    glb_exists = Path(out_glb).exists()
    glb_size   = Path(out_glb).stat().st_size if glb_exists else 0

    result = {
        "model":      model,
        "status":     "pass" if (ok and glb_exists and glb_size > 0) else "fail",
        "elapsed_s":  round(elapsed, 2),
        "glb_size":   glb_size,
        "glb_exists": glb_exists,
        "method":     data.get("data", {}).get("method", "unknown"),
        "lrm_used":   data.get("data", {}).get("lrm_used"),
    }

    if not ok or not glb_exists:
        result["error"] = stderr[-500:] if stderr else "unknown error"

    status_str = "✓ PASS" if result["status"] == "pass" else "✗ FAIL"
    print(f"  {status_str} — {elapsed:.1f}s — GLB: {glb_size:,} bytes — method: {result['method']}")
    if result.get("error"):
        print(f"  Error: {result['error'][:200]}")

    return result


def test_ifc_export(glb_path, output_dir):
    """Test IFC export from a GLB file."""
    out_ifc = str(Path(output_dir) / f"test_export_{int(time.time())}.ifc")
    objects_json = json.dumps([{
        "id": "test_obj", "name": "Test Chair",
        "position": [0, 0, 0], "rotation": [0, 0, 0], "scale": [1, 1, 1],
        "glbPath": glb_path,
    }])

    print("\n[TEST] IFC export (saveIFC.py)")
    ok, data, stderr, elapsed = _run_script("saveIFC.py", [out_ifc, objects_json], timeout=120)
    ifc_exists = Path(out_ifc).exists()
    ifc_size   = Path(out_ifc).stat().st_size if ifc_exists else 0

    result = {
        "test":     "ifc_export",
        "status":   "pass" if (ok and ifc_exists and ifc_size > 1000) else "fail",
        "elapsed_s": round(elapsed, 2),
        "ifc_size":  ifc_size,
    }
    if not ok:
        result["error"] = stderr[-300:]

    status_str = "✓ PASS" if result["status"] == "pass" else "✗ FAIL"
    print(f"  {status_str} — {elapsed:.1f}s — IFC: {ifc_size:,} bytes")
    if result.get("error"):
        print(f"  Error: {result['error'][:200]}")

    return result


def test_classify(image_path):
    """Test object classification."""
    print("\n[TEST] classify_object.py")
    ok, data, stderr, elapsed = _run_script("classify_object.py", [image_path], timeout=120)
    primary = data.get("data", {}).get("primary", {})
    result = {
        "test":       "classification",
        "status":     "pass" if ok else "fail",
        "elapsed_s":  round(elapsed, 2),
        "class":      primary.get("class_name", "unknown"),
        "confidence": primary.get("confidence", 0.0),
    }
    status_str = "✓ PASS" if result["status"] == "pass" else "✗ FAIL"
    print(f"  {status_str} — detected: {result['class']} ({result['confidence']:.2f})")
    return result


def test_layout():
    """Test spatial layout solver."""
    print("\n[TEST] spatial_layout.py")
    room    = json.dumps({"width": 6.0, "depth": 5.0, "height": 3.0})
    objects = json.dumps([
        {"id": "chair_1", "category": "chair", "width": 0.6, "depth": 0.6},
        {"id": "desk_1",  "category": "desk",  "width": 1.4, "depth": 0.7},
        {"id": "chair_2", "category": "chair", "width": 0.6, "depth": 0.6},
    ])
    ok, data, stderr, elapsed = _run_script("spatial_layout.py", [room, objects], timeout=60)
    placements = data.get("data", {}).get("placements", [])
    result = {
        "test":      "spatial_layout",
        "status":    "pass" if (ok and len(placements) == 3) else "fail",
        "elapsed_s": round(elapsed, 2),
        "placed":    len(placements),
    }
    status_str = "✓ PASS" if result["status"] == "pass" else "✗ FAIL"
    print(f"  {status_str} — placed {len(placements)}/3 objects")
    return result


def run_tests(models, image_path, output_dir):
    print("=" * 60)
    print("3DpicToIFC — Sprint 8 Pipeline Test Runner")
    print("=" * 60)

    results = []
    first_glb = None

    for model in models:
        r = test_model(model, image_path, output_dir)
        results.append(r)
        if r["status"] == "pass" and first_glb is None:
            glb_candidates = list(Path(output_dir).glob(f"test_{model}_*.glb"))
            if glb_candidates:
                first_glb = str(sorted(glb_candidates)[-1])

    # IFC export test (uses the first successfully generated GLB)
    if first_glb:
        results.append(test_ifc_export(first_glb, output_dir))
    else:
        print("\n[SKIP] IFC export test — no GLB produced")

    results.append(test_classify(image_path))
    results.append(test_layout())

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(1 for r in results if r.get("status") == "pass")
    failed = sum(1 for r in results if r.get("status") == "fail")
    skipped = len(results) - passed - failed

    for r in results:
        name = r.get("model") or r.get("test", "?")
        s    = r.get("status", "?")
        icon = "✓" if s == "pass" else ("✗" if s == "fail" else "–")
        print(f"  {icon} {name:<20} {s}")

    print(f"\n  {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sprint 8 pipeline test runner")
    parser.add_argument("--model", default="all",
                        help="Model to test (triposr|instantmesh|trellis|hunyuan3d|all)")
    parser.add_argument("--image", default=None, help="Input image path")
    parser.add_argument("--output-dir", default="./test_outputs")
    args = parser.parse_args()

    models = MODELS if args.model == "all" else [args.model]

    # Create synthetic test image if none provided
    test_img = args.image
    if not test_img or not Path(test_img).exists():
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            test_img = tmp.name
        if not _create_test_image(test_img):
            print("ERROR: No test image and cannot create synthetic one", file=sys.stderr)
            sys.exit(1)
        print(f"[INFO] Using synthetic test image: {test_img}")

    passed = run_tests(models, test_img, args.output_dir)
    sys.exit(0 if passed else 1)
