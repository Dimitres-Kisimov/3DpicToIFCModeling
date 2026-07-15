"""make_presentation_pack.py — EVERY presentation document as PDF, one folder.
Markdown docs get styled HTML → Chrome print-to-pdf; live app pages print
directly; Excel cost packs are copied beside them. (server must be running)

    python scripts/make_presentation_pack.py
Out: deliverable/local_only/presentation_pack/
"""
import shutil
import subprocess
from pathlib import Path

import markdown

REPO = Path(__file__).resolve().parents[1]
PACK = REPO / "deliverable" / "local_only" / "presentation_pack"
TMP = PACK / "_tmp"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

CSS = """<style>
body{font:14px/1.65 "Segoe UI",system-ui,sans-serif;color:#1f2733;max-width:820px;
     margin:24px auto;padding:0 18px}
h1{font-size:23px;color:#1f2733} h2{font-size:17px;margin-top:24px;color:#2f6bff}
h3{font-size:15px;margin-top:16px}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin:10px 0}
th,td{border:1px solid #c9d4e0;padding:6px 9px;text-align:left}
th{background:#2f6bff;color:#fff}
code{background:#eef2f7;padding:1px 5px;border-radius:4px;font-size:12px}
pre{background:#eef2f7;padding:10px;border-radius:8px;overflow-x:hidden;font-size:11.5px}
blockquote{border-left:4px solid #2f6bff;margin:12px 0;padding:4px 14px;background:#eef3ff}
img{max-width:100%}
</style>"""

MD_DOCS = [  # (output name, source md, title note)
    ("01_Presentation_Handoff",  REPO / "deliverable/local_only/PRESENTATION_HANDOFF.md"),
    ("03_ROI_Cost_Savings",      REPO / "docs/roi/ROI_ANALYSIS.md"),
    ("04_Procurement_Method_and_Limitations", REPO / "docs/PROCUREMENT_METHOD.md"),
    ("06_ASR_Compliance_German_Standard",     REPO / "docs/ASR_COMPLIANCE.md"),
    ("07_Item_Logic_Register",   REPO / "docs/ITEM_LOGIC_REGISTER.md"),
    ("08_Drop_Test_7_Storey",    REPO / "docs/DROP_TEST_REPORT.md"),
    ("09_User_Guide",            REPO / "docs/USER_GUIDE.md"),
    ("10_v2_Feature_Patch",      REPO / "docs/PATCH_V2.md"),
]
LIVE_PAGES = [  # JS pages printed from the running app
    ("05_Procurement_Study_bed_chair_stool", "http://localhost:3000/procurement_study.html", 15000),
    ("11_ROI_Interactive_Table",             "http://localhost:3000/roi.html", 8000),
]
COPIES = [
    (REPO / "docs/room_type_gallery/Room_Type_Gallery_A4.pdf", "02_Room_Type_Gallery_A4.pdf"),
    (REPO / "deliverable/local_only/SCS_Studio_Presentation_v3.pptx", "12_Slide_Deck_35_slides.pptx"),
    (REPO / "docs/roi/roi_analysis.xlsx", "cost_ROI_analysis.xlsx"),
    (REPO / "docs/procurement_study/stool-TSG-cloud.xlsx", "cost_procurement_stool_TripoSG.xlsx"),
    (REPO / "docs/procurement_study/bed-TRELLIS-cloud.xlsx", "cost_procurement_bed_TRELLIS.xlsx"),
    (REPO / "docs/procurement_study/chair-SAM3D-cloud.xlsx", "cost_procurement_chair_SAM3D.xlsx"),
    # the benchmark-gallery images the study items come from (the user's source)
    (REPO / "deliverable/cloud_gallery/assets/bed_input.png", "img_bed_input_photo.png"),
    (REPO / "deliverable/cloud_gallery/assets/bed_trellis.png", "img_bed_TRELLIS_F0.67.png"),
    (REPO / "deliverable/cloud_gallery/assets/chair_input.png", "img_chair_input_photo.png"),
    (REPO / "deliverable/cloud_gallery/assets/stool_input.png", "img_stool_input_photo.png"),
    (REPO / "deliverable/cloud_gallery/assets/stool_triposg.png", "img_stool_TripoSG_F0.99.png"),
    (REPO / "deliverable/cloud_gallery/assets/stool_abo_gt.png", "img_stool_ground_truth.png"),
]


def print_pdf(src_url, out_pdf, budget=6000):
    subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                    f"--print-to-pdf={out_pdf}", "--no-pdf-header-footer",
                    f"--virtual-time-budget={budget}", src_url],
                   capture_output=True, timeout=180)
    return Path(out_pdf).exists()


def main():
    PACK.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(exist_ok=True)
    made = []
    for name, md_path in MD_DOCS:
        if not md_path.exists():
            print(f"SKIP {name}: {md_path.name} missing")
            continue
        body = markdown.markdown(md_path.read_text(encoding="utf-8"),
                                 extensions=["tables", "fenced_code"])
        html = TMP / (name + ".html")
        html.write_text("<!doctype html><meta charset='utf-8'>" + CSS + body,
                        encoding="utf-8")
        ok = print_pdf(html.as_uri(), PACK / (name + ".pdf"))
        print(("PDF  " if ok else "FAIL ") + name, flush=True)
        if ok:
            made.append(name + ".pdf")
    for name, url, budget in LIVE_PAGES:
        ok = print_pdf(url, PACK / (name + ".pdf"), budget)
        print(("PDF  " if ok else "FAIL ") + name, flush=True)
        if ok:
            made.append(name + ".pdf")
    for src, dst in COPIES:
        if not src.exists():
            print("SKIP", dst, "(source missing)")
            continue
        try:
            shutil.copy(src, PACK / dst)
            made.append(dst)
            print("COPY", dst, flush=True)
        except PermissionError:
            print("SKIP", dst, "(open in another program — close it and rerun)")
    (PACK / "00_README.txt").write_text(
        "SCS STUDIO - PRESENTATION PACK (Dimitres Kisimov)\n"
        "=================================================\n\n"
        "01  Presentation handoff - the complete brief (feed to any AI or human)\n"
        "02  Room-type gallery, A4 print-ready - all 18 room types, plans + X-rays\n"
        "03  ROI / cost savings - the business case (PDF)\n"
        "04  Procurement method + LIMITATIONS + practical evaluation\n"
        "05  Procurement study - TRELLIS bed & chair, TripoSG stool, tiered offers\n"
        "06  German ASR compliance mapping (legal citations)\n"
        "07  Item Logic Register - every placement rule vs the German standard\n"
        "08  7-storey IFC drop test report\n"
        "09  User guide - every tab and button\n"
        "10  v2 feature patch notes (rotation, delete, safety, capacity)\n"
        "11  ROI interactive table (printed from the live app)\n"
        "12  The 35-slide deck (PowerPoint)\n"
        "13  Look-alike matching v1/v2/v3 - findings, honest grading, further-development roadmap\n"
        "cost_*.xlsx  - the finance packs: ROI + 3 procurement studies\n\n"
        "Screenshots: ..\\presentation_shots\\ (57+ JPEGs, INDEX.txt)\n"
        "Catalog for TransferXL: ..\\ABO_furniture_catalog.zip (4.85 GB)\n",
        encoding="utf-8")
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(made)} files -> {PACK}")


if __name__ == "__main__":
    main()
