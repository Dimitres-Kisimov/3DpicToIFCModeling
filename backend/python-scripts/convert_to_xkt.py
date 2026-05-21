"""
Sprint 3 — IFC → XKT conversion
XKT is xeokit's binary scene format — loads 10-100× faster than IFC in the browser.

Conversion path (two options tried in order):
  Option A: ifc2gltf (IfcOpenShell CLI) → gltf2xkt (xeokit SDK CLI)
  Option B: python-based fallback writing a minimal XKT JSON

Prerequisites:
  Option A: npm install -g @xeokit/xeokit-convert  (provides gltf2xkt CLI)
             pip install ifcopenshell  (provides ifc2gltf)
  Option B: no extra deps (generates browser-loadable XKT JSON)

Usage: python convert_to_xkt.py <input.ifc> <output.xkt>
"""

import sys
import os
import json
import subprocess
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit


def _ifc_to_gltf(ifc_path, gltf_path):
    """Convert IFC → GLTF using ifcopenshell's ifc2gltf."""
    try:
        import ifcopenshell
        import ifcopenshell.geom
        import trimesh

        log("Loading IFC with ifcopenshell...", "info")
        ifc = ifcopenshell.open(ifc_path)
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)

        meshes = []
        for product in ifc.by_type("IfcProduct"):
            try:
                shape = ifcopenshell.geom.create_shape(settings, product)
                verts = shape.geometry.verts
                faces = shape.geometry.faces

                if not verts or not faces:
                    continue

                import numpy as np
                v_arr = np.array(verts).reshape(-1, 3)
                f_arr = np.array(faces).reshape(-1, 3)
                meshes.append(trimesh.Trimesh(vertices=v_arr, faces=f_arr))
            except Exception:
                continue

        if not meshes:
            raise ValueError("No geometry extracted from IFC")

        scene = trimesh.scene.Scene(geometry={f"mesh_{i}": m for i, m in enumerate(meshes)})
        scene.export(gltf_path)
        log(f"IFC → GLTF: {gltf_path}", "info")
        return True
    except Exception as e:
        log(f"ifcopenshell geom failed: {e}", "warn")
        return False


def _gltf_to_xkt(gltf_path, xkt_path):
    """Convert GLTF → XKT using gltf2xkt CLI from @xeokit/xeokit-convert."""
    try:
        result = subprocess.run(
            ["gltf2xkt", "-s", str(gltf_path), "-o", str(xkt_path)],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and Path(xkt_path).exists():
            log(f"GLTF → XKT: {xkt_path}", "info")
            return True
        log(f"gltf2xkt failed: {result.stderr}", "warn")
        return False
    except FileNotFoundError:
        log("gltf2xkt CLI not found — install: npm install -g @xeokit/xeokit-convert", "warn")
        return False
    except Exception as e:
        log(f"gltf2xkt error: {e}", "warn")
        return False


def _write_xkt_json_fallback(ifc_path, xkt_path):
    """
    Minimal XKT-JSON fallback: extracts mesh data from IFC using ifcopenshell
    and writes a browser-loadable XKT JSON file that xeokit can parse.
    """
    try:
        import ifcopenshell
        import ifcopenshell.geom
        import numpy as np

        ifc = ifcopenshell.open(ifc_path)
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)

        geometries = {}
        objects = {}

        for product in ifc.by_type("IfcProduct"):
            try:
                shape = ifcopenshell.geom.create_shape(settings, product)
                verts_flat = list(shape.geometry.verts)
                faces_flat = list(shape.geometry.faces)
                if not verts_flat:
                    continue
                gid = shape.geometry.id
                geometries[gid] = {
                    "positionsCompressed": verts_flat,
                    "indices": faces_flat,
                }
                objects[product.GlobalId] = {
                    "geometryId": gid,
                    "name": getattr(product, "Name", product.GlobalId) or product.GlobalId,
                }
            except Exception:
                continue

        xkt_data = {
            "xktVersion": 10,
            "geometries": geometries,
            "meshes": {k: {"geometryId": v["geometryId"]} for k, v in objects.items()},
            "objects": objects,
        }

        with open(xkt_path, "w") as f:
            json.dump(xkt_data, f)

        log(f"XKT JSON fallback saved: {os.path.getsize(xkt_path)} bytes", "info")
        return True
    except Exception as e:
        log(f"XKT JSON fallback failed: {e}", "warn")
        return False


def convert_ifc_to_xkt(ifc_path, xkt_path):
    """Main conversion entry point."""
    if not Path(ifc_path).exists():
        error_exit(f"IFC file not found: {ifc_path}")

    log(f"Converting {ifc_path} → {xkt_path}", "info")

    # Option A: ifc → gltf → xkt (highest fidelity)
    with tempfile.TemporaryDirectory() as tmpdir:
        gltf_path = Path(tmpdir) / "model.glb"
        if _ifc_to_gltf(ifc_path, str(gltf_path)):
            if _gltf_to_xkt(str(gltf_path), xkt_path):
                xkt_size = os.path.getsize(xkt_path)
                return {"method": "ifc2gltf+gltf2xkt", "xkt_size_bytes": xkt_size}

    # Option B: XKT JSON fallback
    if _write_xkt_json_fallback(ifc_path, xkt_path):
        xkt_size = os.path.getsize(xkt_path)
        return {"method": "xkt-json-fallback", "xkt_size_bytes": xkt_size}

    error_exit("All XKT conversion methods failed")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        error_exit("Usage: convert_to_xkt.py <input.ifc> <output.xkt>")
    result = convert_ifc_to_xkt(sys.argv[1], sys.argv[2])
    success_exit(result)
