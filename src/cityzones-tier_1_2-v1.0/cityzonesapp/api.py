from flask import Blueprint, Response, current_app, g, request
from sqlalchemy import and_, or_
from datetime import datetime, timedelta
from . import models
import os
import io
import json

bp = Blueprint('api', __name__, url_prefix='/api')
db = models.db

def get_file_data(stream, fp, eof: str):
    # Scan until the beginning of data
    while True:
        if stream.readline() == b'\r\n':
            break

    while True:
        line = stream.readline()

        # Check if the contents of the file has ended
        if len(line) == 0 or line.startswith(eof):
            fp.seek(-1, io.SEEK_CUR)
            fp.truncate()
            return
        else:
            fp.write(line.strip())
            fp.write(b'\n')

@bp.before_request
def authorize():
    g.worker = db.session.query(models.Worker).where(models.Worker.token == str(request.headers.get('X-API-Key'))).first()
    if g.worker == None:
        return Response(json.dumps({'msg': 'Unauthorized.'}), headers={'Content-type': 'application/json'}, status=401)

@bp.route('/task', methods=['GET'])
def get_task():
    '''
    Return a task to the worker (client).
    '''
    with current_app.app_context():
        request_exp = datetime.now() - timedelta(minutes=int(os.getenv('TASK_REQ_EXP')))
        max_requests = int(os.getenv('TASK_REQ_MAX'))
        tasks = db.session.query(models.Task).where(and_(models.Task.requests < max_requests, or_(models.Task.requested_at < request_exp, models.Task.requested_at == None))).all()

        for task in tasks:
            if len(task.result) == 0:
                task.requested_at = datetime.now()
                task.requests += 1
                db.session.commit()

                data = {
                    'id': task.id,
                    'config': task.config,
                    'geojson': task.geojson
                }
                return data

    return Response(json.dumps({'msg': 'No tasks to perform.'}), headers={'Content-type': 'application/json'}, status=204)

@bp.route('/result/<int:id>', methods=['POST'])
def post_result(id):
    '''
    Receive a result from the worker and save its data.
    '''
    try:
        task = models.db.session.query(models.Task).where(models.Task.id == id).first()
        if task == None:
            return Response(json.dumps({'msg': 'Task not found.'}), headers={'Content-type': 'application/json'}, status=404)

        # Check if there is a result for this task
        if len(task.result) > 0:
            return Response(json.dumps({'msg': 'There is a result for this task already.'}), headers={'Content-type': 'application/json'}, status=409)
        
        # Read stream
        fp = None
        res_data = {}
        boundary = request.stream.readline().strip()

        while True:
            line = request.stream.readline()

            # If there is no data, stream is over
            if len(line) == 0:
                result = models.Result(task.id)
                result.res_data = res_data
                g.worker.tasks += 1
                g.worker.last_task_at = datetime.now()
                g.worker.total_time += res_data['time_classification'] + res_data['time_positioning']
                models.db.session.add(result)
                models.db.session.add(g.worker)
                models.db.session.commit()
                return Response(json.dumps({'msg': 'Data received succesfully.'}), headers={'Content-type': 'application/json'}, status=201)

            # Other case is a line of headers
            else:
                if line.startswith(b'Content-Disposition: form-data'):
                    # Get current data name
                    dataname = ''
                    header = line.split(b'; ')
                    for item in header:
                        item = item.strip()
                        field = item.split(b'=')
                        if field[0] == b'name':
                            dataname = field[1].decode().replace('"', '').replace("'", "")
                            break

                    if fp != None:
                        fp.close()

                    if dataname in ['map', 'edus', 'roads']:
                        fp = open(f'{os.getenv("RESULTS_DIR")}/{task.base_filename}_{dataname}.csv', 'wb')
                        get_file_data(request.stream, fp, boundary)
                        fp.close()
                    
                    elif dataname == 'res_data':
                        fp = io.BytesIO()
                        get_file_data(request.stream, fp, boundary)
                        res_data = json.loads(fp.getvalue())
                        fp.close()

    except KeyError:
        return Response(json.dumps({'msg': 'Received data is incomplete.'}), headers={'Content-type': 'application/json'}, status=400)
    except ValueError:
        return Response(json.dumps({'msg': 'Received header is incomplete.'}), headers={'Content-type': 'application/json'}, status=400)
