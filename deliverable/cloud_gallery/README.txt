SCS single-image -> 3D comparison gallery (portable export)
============================================================
10 furniture types, each compared across:
  2D input | TripoSR-SAM2 | TripoSR-rembg | TRELLIS | TripoSG | real ABO mesh
Scored by F-score@0.02 vs the real ABO mesh (shown under each panel).

TO VIEW (interactive, spinning 3D):
  1) Double-click  serve.bat   (needs Python + internet once for the 3D viewer library).
  2) It starts a tiny local server and opens index.html in your browser.
  3) Drag any panel to orbit; every panel is locked to one front-facing camera.

RESULTS (mean F-score@0.02 vs real mesh):
  ABO 1.00  >  TripoSG 0.393  >  TRELLIS 0.347  >  TripoSR-rembg 0.295  >  TripoSR-SAM2 0.278
Real catalog mesh still beats the best generator ~2.5x.

Self-contained: assets/ holds all the .glb meshes. Move/zip this folder anywhere.
