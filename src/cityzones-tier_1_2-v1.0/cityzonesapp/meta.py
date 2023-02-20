'''
Metaprogramming functions.

These functions are responsible for generating JSON configuration files for the
riskzones background app.
'''

from datetime import datetime
import os
import geojson

def make_polygon(polygon: list) -> dict:
    '''
    Generate a GeoJSON structure for the polygon.
    '''
    polygon.append(polygon[0])
    geojson_polygon = geojson.Polygon([polygon])
    geojson_feature = geojson.Feature(geometry=geojson_polygon)
    geojson_collection = geojson.FeatureCollection([geojson_feature])
    
    return geojson_collection

def get_polygon(collection: dict) -> list:
    '''
    Get the polygon from a GeoJSON FeatureCollection.
    '''
    geojson_collection = geojson.loads(str(collection).replace("'", '"'))
    polygon = []

    try:
        if geojson_collection.type == 'FeatureCollection':
            if geojson_collection.features[0].geometry.type == 'Polygon':
                polygon = geojson_collection.features[0].geometry.coordinates[0]
            elif geojson_collection.features[0].geometry.type == 'MultiPolygon':
                polygon = geojson_collection.features[0].geometry.coordinates[0][0]
    except AttributeError:
        pass
    
    return polygon

def make_config_file(polygon: list, zl: int, edus: int, edu_alg: str) -> tuple:
    '''
    Generate a JSON configuration for the riskzones rool.
    '''
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    base_filename = f"task_{timestamp}"

    # Calculate AoI boundaries
    left = right = polygon[0][0]
    top = bottom = polygon[0][1]

    for point in polygon[1:]:
        if point[0] < left:   left   = point[0]
        if point[0] > right:  right  = point[0]
        if point[1] < bottom: bottom = point[1]
        if point[1] > top:    top    = point[1]
    
    base_conf = {
        "base_filename": base_filename,
        "left": left,
        "bottom": bottom,
        "right": right,
        "top": top,
        "zone_size": zl,
        "cache_zones": False,
        "M": int(os.getenv('RZ_M')),
        "edus": edus,
        "geojson": f"{base_filename}.geojson",
        "pois": f"{base_filename}.osm",
        "pois_types": {
            "amenity": {},
            "railway": {}
        },
        "edu_alg": edu_alg,
        "output": f"{base_filename}_map.csv",
        "output_edus": f"{base_filename}_edus.csv",
        "output_roads": f"{base_filename}_roads.csv",
        "res_data": f"{base_filename}_res_data.json",
    }

    return base_filename, base_conf
