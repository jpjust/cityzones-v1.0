from flask import Blueprint, render_template
import os

bp = Blueprint('help', __name__, url_prefix='/help')

@bp.route('/', methods=['GET'])
def index():
  '''
  Help index page.
  '''
  return render_template('help/index.html', task_req_exp=os.getenv('TASK_REQ_EXP'), task_req_max=os.getenv('TASK_REQ_MAX'))
