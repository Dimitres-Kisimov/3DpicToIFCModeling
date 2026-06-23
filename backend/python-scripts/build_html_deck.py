"""
build_html_deck.py — a polished, self-contained bilingual (DE|EN) HTML presentation for
3DpicToIFCModeling. Single file, all images base64-embedded → works offline, opens in any
browser, prints to PDF. Far better styling control than programmatic .pptx.

Run: python backend/python-scripts/build_html_deck.py
Out: deliverable/SCS_Presentation.html
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIG = REPO / "paper_figures"
OUT = REPO / "deliverable" / "SCS_Presentation.html"


def img(name):
    p = FIG / name
    if not p.exists():
        return ""
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f"data:image/png;base64,{b64}"


def col(flag, lines):
    items = "".join(f"<li>{x}</li>" for x in lines)
    return f'<div class="col"><div class="flag">{flag}</div><ul>{items}</ul></div>'


def title_slide():
    return f'''<section class="slide title">
      <div class="t-wrap">
        <h1>Vom Foto zum BIM-Modell</h1>
        <h2>From Photo to BIM Model</h2>
        <p class="sub">KI-gestützte Raummöblierung &amp; Foto→3D-Pipeline für IFC/BIM<br>
        <span>AI room population &amp; photo→3D pipeline for IFC/BIM</span></p>
        <p class="meta">Gülriz · Dimitrius &nbsp;—&nbsp; 23. Juni 2026</p>
      </div>
    </section>'''


def divider(part_de, part_en, who):
    return f'''<section class="slide divider">
      <div class="d-wrap"><div class="accent-line"></div>
        <h1>{part_de}</h1><h2>{part_en}</h2><p class="who">{who}</p></div>
    </section>'''


def content(t_de, t_en, de, en, who, image=None, cap_de="", cap_en=""):
    imghtml = ""
    if image:
        src = img(image)
        imghtml = f'<div class="fig small"><img src="{src}"><p class="cap"><span>{cap_de}</span><span class="en">{cap_en}</span></p></div>'
    return f'''<section class="slide">
      <header><h3>{t_de}</h3><h4>{t_en}</h4></header>
      <div class="cols">{col("🇩🇪 Deutsch", de)}{col("🇬🇧 English", en)}</div>
      {imghtml}
      <footer><span>{who}</span></footer>
    </section>'''


def figure(t_de, t_en, image, cap_de, cap_en, who, image2=None):
    src = img(image)
    if image2:
        src2 = img(image2)
        fightml = f'<div class="two-img"><img src="{src}"><img src="{src2}"></div>'
    else:
        fightml = f'<div class="one-img"><img src="{src}"></div>'
    return f'''<section class="slide">
      <header><h3>{t_de}</h3><h4>{t_en}</h4></header>
      {fightml}
      <p class="cap big"><span>{cap_de}</span><span class="en">{cap_en}</span></p>
      <footer><span>{who}</span></footer>
    </section>'''


def statement(big_de, big_en, sub_de="", sub_en="", who=""):
    sub = ""
    if sub_de or sub_en:
        sub = f'<p class="st-sub"><span>{sub_de}</span><span class="en">{sub_en}</span></p>'
    foot = f'<footer><span>{who}</span></footer>' if who else ""
    return f'''<section class="slide statement">
      <div class="st-wrap"><h1>{big_de}</h1><h2>{big_en}</h2>{sub}</div>{foot}
    </section>'''


G, D = "Gülriz", "Dimitrius"

SLIDES = [
    title_slide(),

    # ---------- PART 1 — Gülriz : comprehensive plain-language introduction ----------
    divider("Teil 1 — Einführung &amp; Ansatz", "Part 1 — Introduction &amp; Approach", "Gülriz"),

    statement("Stell dir vor: ein Foto eines Raumes wird zu einem digitalen Gebäudemodell.",
              "Imagine: a photo of a room becomes a digital building model.",
              "Genau das versuchen wir zu automatisieren.",
              "That is exactly what we set out to automate.", G),

    content("Was ist BIM? (in einfachen Worten)", "What is BIM? (in plain words)",
        ["BIM = ein digitales Modell eines Gebäudes",
         "Nicht nur Formen, sondern Informationen: Was ist es? Wie groß? Welches Material?",
         "IFC = das offene Dateiformat, um dieses Wissen auszutauschen",
         "Genutzt von Architekten, Ingenieuren, Facility-Management"],
        ["BIM = a digital model of a building",
         "Not just shapes, but information: what is it? how big? what material?",
         "IFC = the open file format to exchange that knowledge",
         "Used by architects, engineers, facility managers"], G),

    content("Warum ist das wichtig?", "Why does it matter?",
        ["Bestehende Räume zu digitalisieren ist heute langsam und teuer",
         "Per Hand messen, in CAD nachbauen – Stunden pro Raum",
         "Automatisierung spart Zeit, Geld und vermeidet Fehler",
         "Relevant für Umbau, Verwaltung, Planung, Einrichtung"],
        ["Digitizing existing rooms today is slow and expensive",
         "Measure by hand, rebuild in CAD — hours per room",
         "Automation saves time, money and avoids errors",
         "Relevant for renovation, facility mgmt, planning, furnishing"], G),

    statement("Der Traum: einfach fotografieren – das Modell entsteht von selbst.",
              "The dream: just take photos — the model builds itself.",
              "Aber: ein Foto allein reicht nicht. Warum?",
              "But: a single photo is not enough. Why?", G),

    content("Warum es schwer ist", "Why it is genuinely hard",
        ["Ein Foto zeigt nur eine Seite – die Rückseite ist unbekannt",
         "KI 'errät' den Rest und liegt im Detail immer daneben",
         "Jeder Versuch sieht anders aus (nicht wiederholbar)",
         "Eine 3D-Form ist noch kein 'intelligentes' BIM-Objekt"],
        ["A photo shows only one side — the back is unknown",
         "AI 'guesses' the rest and is always wrong in detail",
         "Every attempt looks different (not repeatable)",
         "A 3D shape is not yet a 'smart' BIM object"], G),

    statement("Unsere Lösung in einem Satz:",
              "Our solution in one sentence:",
              "Die KI rät die Form nicht – sie erkennt das Objekt und holt ein sauberes, fertiges Modell aus einem Katalog. Dann ordnet eine KI alles sinnvoll im Raum an.",
              "The AI does not guess the shape — it recognises the object and pulls a clean, ready-made model from a catalog. Then an AI arranges everything sensibly in the room.", G),

    content("Was Sie heute sehen", "What you will see today",
        ["Teil 1 (Gülriz): das Problem, der Ansatz, Modelle &amp; Kosten",
         "Teil 2 (Dimitrius): das funktionierende System &amp; die Ergebnisse",
         "Ein echter Katalog aus 400 Möbelmodellen",
         "Eine App, die Räume automatisch einrichtet und exportiert"],
        ["Part 1 (Gülriz): the problem, the approach, models &amp; cost",
         "Part 2 (Dimitrius): the working system &amp; the results",
         "A real catalog of 400 furniture models",
         "An app that furnishes rooms automatically and exports them"], G),
    content("Zusammenfassung", "Executive Summary",
        ["Retrieval-+-Layout: Foto → sauberes Katalog-Mesh → KI-Layout → IFC/BIM",
         "400 echte Produktmodelle (ABO, CC-BY-4.0), Matching via DINOv2 + FAISS",
         "Funktionales Layout auf den Zentimeter verifiziert",
         "Einzelbild-3D-Grenze gemessen: Präzision ~0,81 ≫ Recall ~0,09",
         "€0 Lizenzgebühren · ~€185/Monat · <€0,02/Raum"],
        ["Retrieval-+-layout: photo → clean catalog mesh → AI layout → IFC/BIM",
         "400 real product models (ABO, CC-BY-4.0), matched via DINOv2 + FAISS",
         "Functional layout verified to the centimetre",
         "Single-view 3D ceiling measured: precision ~0.81 ≫ recall ~0.09",
         "€0 royalties · ~€185/month · <€0.02/room"], G,
        image="results_plate.png"),

    content("Das Problem — im Detail", "The Problem — in Detail",
        ["Einzelbild-Rekonstruktion ist mathematisch unterbestimmt",
         "Asymmetrische Beine (kein Symmetrie-Prior)",
         "Halluzinierte Rück-/Unterseite",
         "Nicht-deterministisch: gleiches Foto, andere Meshes",
         "Verrauschte Topologie · Mesh ≠ semantisches IFC"],
        ["Single-view reconstruction is mathematically ill-posed",
         "Asymmetric legs (no symmetry prior)",
         "Hallucinated back / underside",
         "Non-deterministic: same photo, different meshes",
         "Noisy topology · mesh ≠ semantic IFC"], G),

    content("Ziel &amp; Umfang", "Objective &amp; Scope",
        ["Bild→IFC-Pipeline für Büromöbel (kein Gebäude-BIM)",
         "Einzelraum, 10–15 Möbelstücke, funktionales Layout",
         "Nur kommerziell sichere Werkzeuge (keine AGPL, keine Umsatzgrenzen)",
         "Saubere, wiederholbare Meshes über einen Katalog"],
        ["Image→IFC pipeline for office furniture (not building BIM)",
         "Single room, 10–15 items, functional layout",
         "Only commercially-safe tools (no AGPL, no revenue caps)",
         "Clean, repeatable meshes via a catalog"], G),

    content("Energie &amp; Kosten", "Energy &amp; Cost",
        ["Strom (Baden-Württemberg 2026): €0,25/kWh",
         "GPU ~0,45–0,6 kW × 24/7 ≈ 324–432 kWh/Monat → €80–108",
         "Hetzner GEX44 €184/Monat · On-Prem ~€175/Monat",
         "Pro Raum ~€0,019 bei 10.000 Räumen/Monat",
         "Lizenzgebühren €0 – für immer"],
        ["Electricity (Baden-Württemberg 2026): €0.25/kWh",
         "GPU ~0.45–0.6 kW × 24/7 ≈ 324–432 kWh/month → €80–108",
         "Hetzner GEX44 €184/month · on-prem ~€175/month",
         "Per room ~€0.019 at 10,000 rooms/month",
         "Licence royalties €0 — forever"], G),

    content("KI-Ansätze", "AI Approaches at a Glance",
        ["Retrieval-first: nur bei Katalog-Miss generieren",
         "Retrieval: DINOv2 / SigLIP 2",
         "Erkennung + Segmentierung: Grounding DINO + SAM 2.1",
         "Tiefe/Maßstab: Depth Anything V2 Small",
         "Generative Reserve: SAM 3D / Stable Fast 3D / TRELLIS / TripoSR"],
        ["Retrieval-first: generate only on a catalog miss",
         "Retrieval: DINOv2 / SigLIP 2",
         "Detection + segmentation: Grounding DINO + SAM 2.1",
         "Depth/scale: Depth Anything V2 Small",
         "Generative fallback: SAM 3D / Stable Fast 3D / TRELLIS / TripoSR"], G),

    content("HuggingFace &amp; Lizenzen", "HuggingFace &amp; Licences",
        ["Sichere HF-Modelle: Apache-2.0 / MIT / SAM-Lizenz",
         "Falle: Hunyuan3D-2 (EU ausgeschlossen), YOLOv8 (AGPL)",
         "Depth Anything Base/Large (CC-BY-NC – nur Small ist Apache)",
         "Stable Fast 3D: Grenze bei $1 Mio. Umsatz",
         "Prinzip: SCS verkauft Ergebnisse, nicht Gewichte"],
        ["Safe HF models: Apache-2.0 / MIT / SAM license",
         "Traps: Hunyuan3D-2 (EU-excluded), YOLOv8 (AGPL)",
         "Depth Anything Base/Large (CC-BY-NC — only Small is Apache)",
         "Stable Fast 3D: $1M revenue cap",
         "Principle: SCS sells outputs, not weights"], G),

    content("Der Strategiewechsel", "The Pivot — Retrieval + Layout",
        ["Statt halluzinieren: Foto → nächstes sauberes Katalog-Mesh",
         "DINOv2 + FAISS über 400 echte ABO-Modelle",
         "Deterministisch, professionell, wiederholbar",
         "Generierung nur als Reserve"],
        ["Instead of hallucinating: photo → nearest clean catalog mesh",
         "DINOv2 + FAISS over 400 real ABO models",
         "Deterministic, professional, repeatable",
         "Generation only as a fallback"], G,
        image="fig00_overview.png"),

    divider("Teil 2 — System &amp; Ergebnisse", "Part 2 — System &amp; Results", "Dimitrius"),

    figure("Systemüberblick", "System Overview", "results_plate.png",
        "Gesamtüberblick: Layouts, Kapazitätsgrenze und Foto→3D-Genauigkeit",
        "Overview: layouts, capacity boundary and photo→3D accuracy", D),

    content("Der 400-Objekt-Katalog", "The 400-item Catalog",
        ["Amazon Berkeley Objects: 400 echte Modelle, 8 Kategorien × 50",
         "Lizenz CC-BY-4.0, echte metrische Maße",
         "Retrieval: DINOv2 + FAISS",
         "Einzelauswahl mit farbigen Vorschaubildern"],
        ["Amazon Berkeley Objects: 400 real models, 8 categories × 50",
         "Licence CC-BY-4.0, real metric dimensions",
         "Retrieval: DINOv2 + FAISS",
         "Per-item picker with colored previews"], D),

    content("Layout-Engine — 3 Schichten", "Layout Engine — 3 Layers",
        ["Schicht 1: Regelpakete (Neufert 6 m²/AP, ADA 0,915 m, Tür 0,90 m)",
         "Schicht 2: CP-SAT-Packung, 10-cm-Raster, Wand-Affinität",
         "Schicht 3: funktionale Verankerung + Sitzausrichtung",
         "Auf den Zentimeter verifiziert"],
        ["Layer 1: rule packs (Neufert 6 m²/ws, ADA 0.915 m, door 0.90 m)",
         "Layer 2: CP-SAT packing, 10 cm grid, wall-affinity",
         "Layer 3: functional anchoring + seat-facing",
         "Verified to the centimetre"], D,
        image="fig01_office_single_montage.png"),

    figure("Layout in Aktion", "Layout in Action", "fig02_office_team_montage.png",
        "Drei Arbeitsplätze: Stühle zum Schreibtisch, Lager an den Wänden, Mitte frei",
        "Three workstations: chairs face desks, storage on walls, centre open", D),

    figure("Randbedingungen &amp; Barrierefreiheit", "Constraints &amp; Accessibility",
        "fig03_office_obstacles_montage.png",
        "Säule + Türfreiraum (links) · ADA breitere Gänge (rechts)",
        "Column + door keep-clear (left) · ADA wider aisles (right)", D,
        image2="fig04_office_ada_montage.png"),

    figure("Verallgemeinerung", "Generalization", "fig05_living_room_montage.png",
        "Wohnzimmer (links) · dichter Arbeitsraum (rechts)",
        "Living room (left) · dense workspace (right)", D,
        image2="fig06_workspace_dense_montage.png"),

    figure("Kapazitätsgrenze", "Capacity Boundary", "fig08_capacity_sweep.png",
        "Raumgröße × Arbeitsplätze: 4×3→2, 5×4→3, 6×5→4, 8×6→6 — skaliert mit der Fläche",
        "Room size × workstations: 4×3→2, 5×4→3, 6×5→4, 8×6→6 — scales with area", D),

    content("Die Web-App", "The Web App",
        ["Flask + xeokit (WebGL)",
         "Auswählen → Generieren → Vorschau → Export",
         "Export: CSV / GLB / IFC4",
         "Flüchtig: nichts gespeichert bis Export"],
        ["Flask + xeokit (WebGL)",
         "Pick → Generate → preview → Export",
         "Export: CSV / GLB / IFC4",
         "Ephemeral: nothing saved until export"], D),

    content("Genauigkeit — Methode", "Accuracy — Method",
        ["ABO-Meshes als Ground Truth",
         "Foto rendern → rekonstruieren → vergleichen",
         "Chamfer-Distanz + F-Score (τ=0,02), Multi-Seed-ICP",
         "Kalibrierung: Identität F=1,0 · anderes Objekt F=0,18"],
        ["ABO meshes as ground truth",
         "Render photo → reconstruct → compare",
         "Chamfer distance + F-score (τ=0.02), multi-seed ICP",
         "Calibration: identity F=1.0 · different object F=0.18"], D),

    figure("Genauigkeit — Ergebnis", "Accuracy — Result", "fig09_accuracy_triposr.png",
        "TripoSR: Chamfer 0,169 · F 0,155 · Präzision ~0,81 ≫ Recall ~0,09 — die Einzelbild-Grenze",
        "TripoSR: chamfer 0.169 · F 0.155 · precision ~0.81 ≫ recall ~0.09 — the single-view ceiling", D),

    content("Ergebnisse &amp; Ausblick", "Outcomes &amp; Roadmap",
        ["Funktionierendes Retrieval-+-Layout-System",
         "Einzelbild-Grenze gemessen, nicht nur behauptet",
         "€0 Lizenz · ~€185/Monat · <€0,02/Raum",
         "Nächste: 4-Wege-Vergleich, Foto→Retrieval, Multi-View, Maßstab, Desktop-App"],
        ["Working retrieval-+-layout system",
         "Single-view limit measured, not just asserted",
         "€0 royalties · ~€185/month · <€0.02/room",
         "Next: 4-way bake-off, photo→retrieval, multi-view, scale, desktop app"], D),
]

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
:root{--accent:#2f81f7;--ink:#16202e;--muted:#5b6675;--line:#e3e8ef;--bgsoft:#f6f9fe}
html,body{height:100%;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;color:var(--ink);background:#fff}
#deck{height:100vh;width:100vw;position:relative;overflow:hidden;background:#fff}
.slide{position:absolute;inset:0;display:none;flex-direction:column;padding:4.5vh 5vw;background:#fff;opacity:1}
.slide.active{display:flex}
header{border-bottom:3px solid var(--accent);padding-bottom:12px;margin-bottom:3vh}
header h3{font-size:3.0vw;font-weight:700;color:var(--ink);line-height:1.05}
header h4{font-size:1.7vw;font-weight:500;color:var(--accent)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:3vw;flex:1;align-content:start}
.col{background:var(--bgsoft);border:1px solid var(--line);border-radius:14px;padding:3vh 2vw}
.col:first-child{background:#f0f6ff}
.flag{font-size:1.4vw;font-weight:700;color:var(--accent);margin-bottom:1.5vh}
.col ul{list-style:none}
.col li{font-size:1.5vw;line-height:1.5;margin-bottom:1.5vh;padding-left:1.4vw;position:relative;color:#22303f}
.col li:before{content:'';position:absolute;left:0;top:.7vh;width:.55vw;height:.55vw;border-radius:50%;background:var(--accent)}
.fig.small{margin-top:2.5vh;text-align:center}
.fig.small img{max-height:30vh;max-width:62vw;border:1px solid var(--line);border-radius:10px;box-shadow:0 6px 22px #0001}
.one-img{flex:1;display:flex;align-items:center;justify-content:center;min-height:0}
.one-img img{max-height:64vh;max-width:88vw;border:1px solid var(--line);border-radius:12px;box-shadow:0 10px 34px #0002}
.two-img{flex:1;display:flex;gap:2vw;align-items:center;justify-content:center;min-height:0}
.two-img img{max-height:60vh;max-width:43vw;border:1px solid var(--line);border-radius:12px;box-shadow:0 10px 30px #0002}
.cap{margin-top:1.5vh;text-align:center;font-size:1.2vw}
.cap span{display:block;color:var(--muted)}
.cap span.en{color:var(--accent)}
.cap.big{font-size:1.35vw;margin-top:2vh}
footer{position:absolute;bottom:2.6vh;left:5vw;right:5vw;display:flex;justify-content:space-between;
  font-size:1.05vw;color:var(--muted)}
/* title */
.slide.title{background:linear-gradient(135deg,#1b2a4a 0%,#2f81f7 100%);color:#fff;align-items:center;justify-content:center;text-align:center}
.title .t-wrap{max-width:80vw}
.title h1{font-size:5.2vw;font-weight:800;letter-spacing:-.01em}
.title h2{font-size:2.8vw;font-weight:500;color:#cfe0ff;margin-top:.5vh}
.title .sub{margin-top:5vh;font-size:1.7vw;line-height:1.7;color:#eaf1ff}
.title .sub span{color:#b9d0ff}
.title .meta{margin-top:5vh;font-size:1.6vw;font-weight:600;color:#fff;border-top:1px solid #ffffff44;display:inline-block;padding-top:2.5vh}
/* divider */
.slide.divider{background:#0f1622;color:#fff;align-items:center;justify-content:center;text-align:center}
.divider .accent-line{width:90px;height:6px;background:var(--accent);border-radius:3px;margin:0 auto 4vh}
.divider h1{font-size:4vw;font-weight:800}
.divider h2{font-size:2.2vw;font-weight:500;color:#8fb8f7;margin-top:1vh}
.divider .who{margin-top:4vh;font-size:1.7vw;color:#c8d0da}
/* statement (big plain-language framing) */
.slide.statement{align-items:center;justify-content:center;text-align:center;
  background:linear-gradient(160deg,#fbfdff 0%,#eef5ff 100%)}
.statement .st-wrap{max-width:82vw}
.statement h1{font-size:3.4vw;font-weight:800;line-height:1.2;color:var(--ink)}
.statement h2{font-size:2.1vw;font-weight:500;color:var(--accent);margin-top:1.5vh;line-height:1.25}
.statement .st-sub{margin-top:4vh;font-size:1.5vw;line-height:1.6}
.statement .st-sub span{display:block;color:var(--muted)}
.statement .st-sub span.en{color:#3a4655}
/* nav */
#nav{position:fixed;bottom:18px;right:22px;display:flex;gap:10px;align-items:center;z-index:50;
  font-family:system-ui}
#nav button{background:#1f6fe0;color:#fff;border:0;width:40px;height:40px;border-radius:10px;font-size:18px;cursor:pointer;opacity:.85}
#nav button:hover{opacity:1}
#count{color:#fff;background:#0008;padding:6px 12px;border-radius:10px;font-size:14px}
@media print{
  #nav{display:none}
  .slide{display:flex!important;position:relative;page-break-after:always;height:100vh;animation:none}
}
"""

JS = """
const slides=[...document.querySelectorAll('.slide')];let i=0;
const count=document.getElementById('count');
function show(n){i=Math.max(0,Math.min(slides.length-1,n));
  slides.forEach((s,k)=>s.classList.toggle('active',k===i));
  count.textContent=(i+1)+' / '+slides.length;}
document.addEventListener('keydown',e=>{
  if(['ArrowRight','PageDown',' '].includes(e.key))show(i+1);
  if(['ArrowLeft','PageUp'].includes(e.key))show(i-1);
  if(e.key==='Home')show(0); if(e.key==='End')show(slides.length-1);});
document.getElementById('prev').onclick=()=>show(i-1);
document.getElementById('next').onclick=()=>show(i+1);
show(parseInt(location.hash.slice(1))||0);
"""


def main():
    body = "\n".join(SLIDES)
    html = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SCS — Vom Foto zum BIM / From Photo to BIM</title>
<style>{CSS}</style></head><body>
<div id="deck">{body}</div>
<div id="nav"><button id="prev">‹</button><span id="count"></span><button id="next">›</button></div>
<script>{JS}</script>
</body></html>"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    mb = OUT.stat().st_size / 1e6
    print(f"-> {OUT}  ({len(SLIDES)} slides, {mb:.1f} MB, self-contained)")


if __name__ == "__main__":
    main()
