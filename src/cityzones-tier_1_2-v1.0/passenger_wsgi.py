import sys, os

# Get venv python3 path
cwd = os.getcwd()
INTERP = os.path.expanduser("%s/venv/bin/python3" % cwd)

# Replace python3 process
if sys.executable != INTERP:
  os.execl(INTERP, INTERP, *sys.argv)

# Include venv bin into PATH
sys.path.insert(0, "%s/venv/bin" % cwd)

# Import the application
import cityzonesapp
application = cityzonesapp.create_app()
