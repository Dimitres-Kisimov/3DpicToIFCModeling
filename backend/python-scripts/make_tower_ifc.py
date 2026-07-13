# make_tower.py v2 — 7-storey tower from the kleine-wohnung plate:
#   ground (UG01 @0, entrance) · OG01 @3 (28 rooms, original) · OG02 @6 (existing
#   walls get COPIED SPACES) · four full plate copies @9/12/15/18 · roof lifted to 21.
#   => 6 inhabited floors x 28 rooms = 168 rooms, 8-level massing.
import ifcopenshell
import ifcopenshell.guid
import ifcopenshell.util.element as ue
import os

SRC = 'data/buildings/b_fd30573002__kleine_wohnung.ifc'
OUT = os.environ.get('TEMP', '.') + '/SCS_Tower_7F.ifc'
H = 3.0

f = ifcopenshell.open(SRC)
hist = f.by_type('IfcOwnerHistory')[0] if f.by_type('IfcOwnerHistory') else None
building = f.by_type('IfcBuilding')[0]
storeys = {round(float(s.Elevation or 0)): s for s in f.by_type('IfcBuildingStorey')}
og01, og02, roof_st = storeys[3], storeys[6], storeys[9]

def spaces_of(st):
    out = []
    for rel in (st.IsDecomposedBy or []):
        out += [o for o in rel.RelatedObjects if o.is_a('IfcSpace')]
    return out

def products_of(st):
    out = []
    for rel in (st.ContainsElements or []):
        out += list(rel.RelatedElements)
    return out

src_spaces = spaces_of(og01)
src_products = products_of(og01)
print(f'plate: {len(src_products)} products, {len(src_spaces)} spaces')

def offset_placement(orig_pl, dz):
    loc = f.createIfcCartesianPoint((0.0, 0.0, float(dz)))
    ax = f.createIfcAxis2Placement3D(loc, None, None)
    return f.createIfcLocalPlacement(orig_pl, ax)

def copy_with_dz(prod, dz):
    c = ue.copy_deep(f, prod)
    c.GlobalId = ifcopenshell.guid.new()
    c.ObjectPlacement = offset_placement(prod.ObjectPlacement, dz)
    return c

# 1) OG02 (existing walls, no rooms): copy ONLY the spaces up by one floor
sps = [copy_with_dz(s, H) for s in src_spaces]
f.createIfcRelAggregates(ifcopenshell.guid.new(), hist, None, None, og02, sps)
print(f'OG02 @6: +{len(sps)} spaces onto its existing walls')

# 2) four full plate copies at 9 / 12 / 15 / 18
bagg = next(r for r in f.by_type('IfcRelAggregates') if r.RelatingObject == building)
new_storeys = []
for k in range(2, 6):                       # dz = 6, 9, 12, 15  -> elev 9..18
    dz = k * H
    st = f.createIfcBuildingStorey(
        ifcopenshell.guid.new(), hist, f'Tower Level {k + 2}', 'stacked floor plate',
        None, offset_placement(og01.ObjectPlacement, dz), None, None,
        'ELEMENT', 3.0 + dz)
    new_storeys.append(st)
    prods = [copy_with_dz(p, dz) for p in src_products]
    f.createIfcRelContainedInSpatialStructure(
        ifcopenshell.guid.new(), hist, None, None, prods, st)
    sps = [copy_with_dz(s, dz) for s in src_spaces]
    f.createIfcRelAggregates(ifcopenshell.guid.new(), hist, None, None, st, sps)
    print(f'level @{3.0 + dz:.0f}: +{len(prods)} products, +{len(sps)} spaces')
bagg.RelatedObjects = list(bagg.RelatedObjects) + new_storeys

# 3) lift the roof from 9 to 21 (+12): chain-offset every roof product
for p in products_of(roof_st):
    p.ObjectPlacement = offset_placement(p.ObjectPlacement, 4 * H)
roof_st.Elevation = 21.0
roof_st.Name = (roof_st.Name or 'Roof') + ' (lifted to 21m)'
print('roof lifted to 21 m')

f.write(OUT)
print('written', OUT, int(os.path.getsize(OUT) / 1048576), 'MB')
