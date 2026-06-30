# Asset catalogue — 400 real 3D meshes

Source: **Amazon Berkeley Objects (ABO)** — real Amazon products as 3D meshes. Licence
**CC-BY-4.0** (commercial-safe). 8 office-furniture categories, 50 meshes each = **400 total**.

- `catalog_400.csv` — every mesh: id, category, source ASIN, product type, real dimensions
  (m), face count, file size, licence, source.
- `contact_<category>.png` — thumbnail contact sheet (50 per category).

| category | meshes | contact sheet |
|----------|--------|---------------|
| bookshelf | 50 | contact_bookshelf.png |
| cabinet | 50 | contact_cabinet.png |
| desk | 50 | contact_desk.png |
| lamp | 50 | contact_lamp.png |
| office_chair | 50 | contact_office_chair.png |
| sofa | 50 | contact_sofa.png |
| stool | 50 | contact_stool.png |
| table | 50 | contact_table.png |

Each mesh is a real 3D model (GLB) with true metric dimensions; thumbnails are ABO's
rendered previews. Retrieval (DINOv2 + FAISS) matches a photographed object to the nearest
of these 400. Provenance/attribution per item is in the CSV and the project manifest.
