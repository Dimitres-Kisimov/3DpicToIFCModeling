"""repair_glb.py — apply the archetype repair packs to an existing GLB.

Used by the big-engine adapter (backend/ai/bigEngine.js): external engines
(TripoSG / TRELLIS.2 / SAM 3D) produce a raw GLB in their own venv; this runs
in the APP's pinned Python and gives their output the same quality layer the
built-in TripoSR path gets. Same kill-switch: SCS_REPAIR_PACKS=0 copies through.

    python repair_glb.py <in.glb> <out.glb> [label]

Prints one JSON line: {"success": true, "faces": N, "archetype": "..."}.
"""
import sys, os, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"success": False, "error": "usage: repair_glb.py in.glb out.glb [label]"}))
        return 2
    src, dst = sys.argv[1], sys.argv[2]
    label = sys.argv[3] if len(sys.argv) > 3 else None

    import trimesh
    mesh = trimesh.load(src, force="mesh")
    faces_in = len(mesh.faces)
    archetype = "off"
    if os.environ.get("SCS_REPAIR_PACKS", "1") != "0":
        from repair_packs import repair_mesh
        mesh, rep = repair_mesh(mesh, label=label)
        archetype = rep.get("archetype", "?")
    mesh.export(dst)
    print(json.dumps({"success": True, "faces_in": faces_in, "faces": len(mesh.faces),
                      "archetype": archetype, "output": dst}))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)
