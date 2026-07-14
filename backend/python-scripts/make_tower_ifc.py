"""make_tower_ifc.py — synthesize a tall building from ANY IFC's inhabited floor plate.

    python make_tower_ifc.py <src.ifc> <out.ifc> --copies 4 [--height H]

Method (license note: only use sources whose terms allow derivatives — see
docs/BUILDINGS_PROVENANCE.md):
  * plate = the storey with the most IfcSpaces (walls, doors, windows, spaces)
  * N copies inserted directly above the plate at H-metre steps, each with a
    fresh IfcBuildingStorey, fresh GUIDs and a chained +Z placement (world-exact
    offset regardless of the file's placement hierarchy)
  * every storey originally ABOVE the plate (upper floors, roof) is lifted by
    N*H so the architecture stays intact on top of the new tower
"""
import argparse
import ifcopenshell
import ifcopenshell.guid
import ifcopenshell.util.element as ue


def spaces_of(st):
    out = []
    for rel in (st.IsDecomposedBy or []):
        out += [o for o in rel.RelatedObjects if o.is_a("IfcSpace")]
    return out


def products_of(st):
    out = []
    for rel in (st.ContainsElements or []):
        out += list(rel.RelatedElements)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--copies", type=int, default=4)
    ap.add_argument("--height", type=float, default=0.0,
                    help="storey height; 0 = derive from the file's storey elevations")
    args = ap.parse_args()

    f = ifcopenshell.open(args.src)
    hist = f.by_type("IfcOwnerHistory")[0] if f.by_type("IfcOwnerHistory") else None
    building = f.by_type("IfcBuilding")[0]
    storeys = f.by_type("IfcBuildingStorey")

    plate = max(storeys, key=lambda s: len(spaces_of(s)))
    plate_elev = float(plate.Elevation or 0.0)
    src_spaces, src_products = spaces_of(plate), products_of(plate)

    elevs = sorted({round(float(s.Elevation or 0.0), 3) for s in storeys})
    diffs = [b - a for a, b in zip(elevs, elevs[1:]) if b - a > 1.5]
    H = args.height or (min(diffs) if diffs else 3.0)
    N = args.copies
    lift = N * H
    print(f"plate: {plate.Name} @ {plate_elev} | {len(src_products)} products, "
          f"{len(src_spaces)} spaces | H={H} | +{N} copies, upper storeys lifted {lift}")

    def offset_placement(orig_pl, dz):
        loc = f.createIfcCartesianPoint((0.0, 0.0, float(dz)))
        ax = f.createIfcAxis2Placement3D(loc, None, None)
        return f.createIfcLocalPlacement(orig_pl, ax)

    def copy_with_dz(prod, dz):
        c = ue.copy_deep(f, prod)
        c.GlobalId = ifcopenshell.guid.new()
        c.ObjectPlacement = offset_placement(prod.ObjectPlacement, dz)
        return c

    # 1) lift everything originally above the plate (upper floors, roof)
    for st in storeys:
        if float(st.Elevation or 0.0) > plate_elev + 0.5:
            for p in products_of(st):
                p.ObjectPlacement = offset_placement(p.ObjectPlacement, lift)
            for s in spaces_of(st):
                s.ObjectPlacement = offset_placement(s.ObjectPlacement, lift)
            st.Elevation = float(st.Elevation) + lift
            print(f"  lifted: {st.Name} -> {st.Elevation}")

    # 2) N plate copies directly above the plate
    bagg = next(r for r in f.by_type("IfcRelAggregates") if r.RelatingObject == building)
    new_storeys = []
    for k in range(1, N + 1):
        dz = k * H
        st = f.createIfcBuildingStorey(
            ifcopenshell.guid.new(), hist, f"Tower Level +{k}", "stacked floor plate",
            None, offset_placement(plate.ObjectPlacement, dz), None, None,
            "ELEMENT", plate_elev + dz)
        new_storeys.append(st)
        prods = [copy_with_dz(p, dz) for p in src_products]
        if prods:
            f.createIfcRelContainedInSpatialStructure(
                ifcopenshell.guid.new(), hist, None, None, prods, st)
        sps = [copy_with_dz(s, dz) for s in src_spaces]
        if sps:
            f.createIfcRelAggregates(ifcopenshell.guid.new(), hist, None, None, st, sps)
        print(f"  level @ {plate_elev + dz}: +{len(prods)} products, +{len(sps)} spaces")
    bagg.RelatedObjects = list(bagg.RelatedObjects) + new_storeys

    f.write(args.out)
    import os
    print("written", args.out, os.path.getsize(args.out) // 1048576, "MB")


if __name__ == "__main__":
    main()
