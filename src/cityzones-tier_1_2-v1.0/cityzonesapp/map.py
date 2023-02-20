from flask import Blueprint, Response, current_app, render_template, request, send_file
from . import meta, models
import os
import io
import csv
import json
import geojson
from zipfile import ZipFile, ZIP_DEFLATED

bp = Blueprint('map', __name__, url_prefix='/map')
db = models.db

DEFAULT_MAP_LON = -8.595449606742658
DEFAULT_MAP_LAT = 41.1783048033954

@bp.route('/show', methods=['GET'])
def show():
    '''
    Map index page.

    Shows the map centered on FEUP.
    '''
    return render_template('map/index.html', lon=DEFAULT_MAP_LON, lat=DEFAULT_MAP_LAT, polygon=[])

@bp.route('/show/<polygon>', methods=['GET'])
def show_polygon(polygon: str):
    '''
    Map index page.

    Shows the map with some AoI defined.
    '''
    polygon = eval(polygon.replace('%20', ''))
    if polygon[-1][0] == polygon[0][0] and polygon[-1][1] == polygon[0][1]:
        polygon.pop()
    
    return render_template('map/index.html', lon=DEFAULT_MAP_LON, lat=DEFAULT_MAP_LAT, polygon=polygon)

@bp.route('/geojson', methods=['POST'])
def geojson_map():
    '''
    Map index page.

    Shows the map with an AoI defined by a GeoJSON file.
    '''
    geojson_file = request.files['geojson']
    geojson_data = geojson.loads(geojson_file.read().decode())
    polygon = meta.get_polygon(geojson_data)

    if polygon == None:
        return render_template('map/index.html', lon=DEFAULT_MAP_LON, lat=DEFAULT_MAP_LAT, polygon=[], error_msg='Invalid GeoJSON file. It must be a FeatureCollection with a Polygon or MultiPolygon feature.')
    else:
        if polygon[-1][0] == polygon[0][0] and polygon[-1][1] == polygon[0][1]:
            polygon.pop()
        
        return render_template('map/index.html', lon=DEFAULT_MAP_LON, lat=DEFAULT_MAP_LAT, polygon=polygon)

@bp.route('/run', methods=['POST'])
def run():
    '''
    Map request method.

    This method will create the task files and write them to the queue folder.
    A background app will be responsible to check new tasks and execute them.
    '''
    try:
        # Form data
        zl           = int(request.form['zl'])
        edus         = int(request.form['edus'])
        edu_alg      = request.form['edu_alg']
        description  = request.form['description']

        poi_hospital = ('poi_hospital' in request.form.keys())
        poi_firedept = ('poi_firedept' in request.form.keys())
        poi_police   = ('poi_police'   in request.form.keys())
        poi_metro    = ('poi_metro'    in request.form.keys())

        w_hospital   = float(request.form['w_hospital']) if poi_hospital else 0
        w_firedept   = float(request.form['w_firedept']) if poi_firedept else 0
        w_police     = float(request.form['w_police'])   if poi_police   else 0
        w_metro      = float(request.form['w_metro'])    if poi_metro    else 0

        polygon      = eval(request.form['polygon'])

        if len(polygon) < 3:
            return render_template('map/index.html', error_msg='At least 3 points are required for an AoI polygon.', lon=DEFAULT_MAP_LON, lat=DEFAULT_MAP_LAT)
        
        for coord in polygon:
            lon = coord[0]
            lat = coord[1]
            if not (-90 < lat < 90) or not (-180 < lon < 180):
                return render_template('map/index.html', error_msg='The selected AoI is invalid.', lon=DEFAULT_MAP_LON, lat=DEFAULT_MAP_LAT)

        # Generate configuration files
        geojson_data = meta.make_polygon(polygon)
        base_filename, conf = meta.make_config_file(polygon, zl, edus, edu_alg)
        center_lon = (conf['left'] + conf['right']) /2
        center_lat = (conf['bottom'] + conf['top']) /2

        if poi_hospital: conf['pois_types']['amenity']['hospital'] = {'w': w_hospital}
        if poi_firedept: conf['pois_types']['amenity']['fire_station'] = {'w': w_firedept}
        if poi_police:   conf['pois_types']['amenity']['police'] = {'w': w_police}
        if poi_metro:    conf['pois_types']['railway']['station'] = {'w': w_metro}

        # Store in database        
        with current_app.app_context():
            task = models.Task(base_filename, conf, geojson_data, center_lat, center_lon)
            task.description = description
            models.db.session.add(task)
            models.db.session.commit()

            return render_template('map/index.html', info_msg=f'Your request was successfully queued. Request number: {task.id}.', lat=center_lat, lon=center_lon)

    except KeyError:
        return render_template('map/index.html', error_msg='Error: all fields are mandatory.', lon=DEFAULT_MAP_LON, lat=DEFAULT_MAP_LAT)
    except IndexError:
        return render_template('map/index.html', error_msg='There was an error trying to parse the AoI polygon. Check if you created a valid AoI before submitting a map request.', lon=DEFAULT_MAP_LON, lat=DEFAULT_MAP_LAT)
    except ValueError:
        return render_template('map/index.html', error_msg='There was an error trying to parse some parameters. Check if you entered proper values.', lon=DEFAULT_MAP_LON, lat=DEFAULT_MAP_LAT)

@bp.route('/results', methods=['GET'])
def results():
    '''
    Results index page.

    Shows the results of previous requests to display on map.
    '''
    with current_app.app_context():
        tasks = db.paginate(db.select(models.Task).order_by(models.Task.created_at.desc()), max_per_page=10)
        return render_template('map/results.html', tasks=tasks, meta=meta)

@bp.route('/result/<int:id>', methods=['GET'])
def get_result(id):
    '''
    Get a result by its ID and respond with its map data.
    '''
    with current_app.app_context():
        result = db.session.query(models.Result).where(models.Result.task_id == id).first()

        if result == None:
            return Response(json.dumps({'msg': 'There is no result for this task yet.'}), headers={'Content-type': 'application/json'}, status=404)

        map_file = f'{os.getenv("RESULTS_DIR")}/{result.task.base_filename}_map.csv'
        edus_file = f'{os.getenv("RESULTS_DIR")}/{result.task.base_filename}_edus.csv'
        classification = {
            'polygon': [],
            'center_lat': 0,
            'center_lon': 0,
            'zl': result.task.config['zone_size'],
            '1': [],
            '2': [],
            '3': [],
            'edus': []
        }

        left = 180
        right = -180
        bottom = 90
        top = -90

        try:
            # Classification data
            geojson_collection = geojson.loads(str(result.task.geojson).replace("'", '"'))
            geojson_geometry = geojson_collection.features[0].geometry
            if geojson_geometry.type == 'Polygon':
                classification['polygon'] = geojson_geometry.coordinates[0]
            elif geojson_geometry.type == 'MultiPolygon':
                classification['polygon'] = geojson_geometry.coordinates[0][0]

            fp = open(map_file, 'r')
            reader = csv.reader(fp)
            fp.readline()  # Skip header line

            for row in reader:
                M = row[1]
                geodata = json.loads(row[2])
                coord = geodata['coordinates']
                classification[M].append(coord)
                if coord[0] < left:   left   = coord[0]
                if coord[0] > right:  right  = coord[0]
                if coord[1] < bottom: bottom = coord[1]
                if coord[1] > top:    top    = coord[1]

            fp.close()

            classification['center_lat'] = (bottom + top) / 2
            classification['center_lon'] = (left + right) / 2

            # EDUs data
            fp = open(edus_file, 'r')
            reader = csv.reader(fp)
            fp.readline()  # Skip header line

            for row in reader:
                geodata = json.loads(row[1])
                coord = geodata['coordinates']
                classification['edus'].append(coord)

            fp.close()

            return classification
        except FileNotFoundError:
            return Response(json.dumps({'msg': 'Results file not found for this task.'}), headers={'Content-type': 'application/json'}, status=500)

@bp.route('/result/download/<int:id>', methods=['GET'])
def download_result(id):
    '''
    Get a result by its ID and respond with its CSV files in ZIP format.
    '''
    with current_app.app_context():
        result = db.session.query(models.Result).where(models.Result.task_id == id).first()

        if result == None:
            return Response(json.dumps({'msg': 'There is no result for this task yet.'}), headers={'Content-type': 'application/json'}, status=404)

        map_file = f'{os.getenv("RESULTS_DIR")}/{result.task.base_filename}_map.csv'
        edus_file = f'{os.getenv("RESULTS_DIR")}/{result.task.base_filename}_edus.csv'
        roads_file = f'{os.getenv("RESULTS_DIR")}/{result.task.base_filename}_roads.csv'
        zip_data = io.BytesIO()

        try:
            with ZipFile(zip_data, 'w', compression=ZIP_DEFLATED, compresslevel=9) as myzip:
                myzip.write(map_file, arcname=f'{result.task.base_filename}_map.csv')
                if os.path.isfile(edus_file):
                    myzip.write(edus_file, arcname=f'{result.task.base_filename}_edus.csv')
                if os.path.isfile(roads_file):
                    myzip.write(roads_file, arcname=f'{result.task.base_filename}_roads.csv')
        except FileNotFoundError:
            return Response(json.dumps({'msg': 'The map file for this task is missing!'}), headers={'Content-type': 'application/json'}, status=404)
        
        zip_data.seek(0)
        return send_file(
            zip_data,
            as_attachment=True,
            download_name=f'{result.task.base_filename}_results.zip',
            mimetype='application/zip'
        )

@bp.route('/download/<int:id>', methods=['GET'])
def download_task(id):
    '''
    Get a task by its ID and respond with its JSON and GeoJSON files in ZIP format.
    '''
    with current_app.app_context():
        task = db.get_or_404(models.Task, id)

        zip_data = io.BytesIO()

        with ZipFile(zip_data, 'w', compression=ZIP_DEFLATED, compresslevel=9) as myzip:
            myzip.writestr(f'{task.base_filename}.json', json.dumps(task.config))
            myzip.writestr(f'{task.base_filename}.geojson', json.dumps(task.geojson))
        
        zip_data.seek(0)
        return send_file(
            zip_data,
            as_attachment=True,
            download_name=f'{task.base_filename}.zip',
            mimetype='application/zip'
        )

@bp.route('/countries', methods=['GET'])
def countries():
    '''
    Get the countries list and its coordinates for the list on map page.
    '''
    try:
        fp = open('public/countries.csv', 'r')
        reader = csv.reader(fp)
        data = {'countries': []}

        for row in reader:
            data['countries'].append({
                'name': row[3],
                'lat': row[1],
                'lon': row[2]
            })

        fp.close()

        return Response(json.dumps(data), headers={'Content-type': 'application/json'}, status=200)
    except FileNotFoundError:
        return Response(json.dumps({'msg': 'The countries file is missing!'}), headers={'Content-type': 'application/json'}, status=404)
