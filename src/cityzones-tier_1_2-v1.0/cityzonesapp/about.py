from flask import Blueprint, render_template

bp = Blueprint('about', __name__, url_prefix='/about')

@bp.route('/', methods=['GET'])
def index():
  '''
  Index about page.
  '''
  return render_template('about/index.html')
