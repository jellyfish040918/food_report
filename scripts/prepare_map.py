"""Prepare offline SVG geography from Natural Earth's public-domain 110m GeoJSON.

Input: .tmp/natural-earth-countries.geojson from
https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson
The generated asset is checked in; ordinary builds need no network.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / '.tmp/natural-earth-countries.geojson'
geo = json.loads(source.read_text(encoding='utf-8'))
def xy(lon, lat):
    return round(50 + (lon + 180) * 2.5, 2), round(20 + (85 - lat) * 2.5, 2)
countries = []
for feature in geo['features']:
    p = feature['properties']
    if p['ISO_A3'] == 'ATA':
        continue
    polygons = feature['geometry']['coordinates']
    if feature['geometry']['type'] == 'Polygon':
        polygons = [polygons]
    parts = []
    for polygon in polygons:
        for ring in polygon:
            points = [xy(*point[:2]) for point in ring]
            parts.append('M' + 'L'.join(f'{x},{y}' for x,y in points) + 'Z')
    x,y = xy(p['LABEL_X'], p['LABEL_Y'])
    countries.append({'id':p['ISO_A2_EH'], 'ko':p['NAME_KO'], 'en':p['NAME_EN'], 'path':''.join(parts), 'x':x, 'y':y})
for code, ko, en, lon, lat in [('SG','싱가포르','Singapore',103.82,1.35), ('HK','홍콩','Hong Kong',114.17,22.32)]:
    x,y = xy(lon,lat)
    countries.append({'id':code,'ko':ko,'en':en,'path':'','x':x,'y':y})
asset = {'source':'Natural Earth, 1:110m countries', 'url':'https://www.naturalearthdata.com/downloads/110m-cultural-vectors/', 'license':'Public domain', 'projection':'Equirectangular', 'countries':countries}
(ROOT / 'src/geo/world.json').write_text(json.dumps(asset,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
print(f'Prepared {len(countries)} map areas.')
