"""make_abo_transfer_zip.py — pack the 4.7 GB ABO furniture library for
TransferXL. Paths inside the zip start with data/mesh_library_abo/ so the
recipient extracts it straight INTO the app folder (per the handoff steps).

    python scripts/make_abo_transfer_zip.py
Out: deliverable/local_only/ABO_furniture_catalog.zip
"""
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "data" / "mesh_library_abo"
OUT = REPO / "deliverable" / "local_only" / "ABO_furniture_catalog.zip"


def main():
    # _listings_work is a one-time build cache (raw ABO metadata tar) the app
    # never reads — skipping it keeps the pack under TransferXL's 5 GB tier
    files = sorted(p for p in SRC.rglob("*")
                   if p.is_file() and "_listings_work" not in p.parts)
    total = sum(p.stat().st_size for p in files)
    print(f"{len(files)} files, {total / 1e9:.2f} GB -> {OUT}")
    # GLBs barely deflate; STORED keeps the pack fast and TransferXL-friendly
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for i, p in enumerate(files):
            z.write(p, "data/mesh_library_abo/" + p.relative_to(SRC).as_posix())
            if i % 500 == 0:
                print(f"  {i}/{len(files)}", flush=True)
    print(f"DONE {OUT.stat().st_size / 1e9:.2f} GB")


if __name__ == "__main__":
    main()
