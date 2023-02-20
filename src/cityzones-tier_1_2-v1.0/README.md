# CityZones Application Server

CityZones Application Server is a web interface and back-end application for CityZones Maps-service: https://github.com/jpjust/cityzones-maps-service

The web interface works as a client for the user, so the user can configure an AoI to reqeuest a RiskZones classification. The Maps-service workers will periodically request a task from the CityZones Application Server to perform it locally and then send the results back. The web interface can then present the results to the user.

## How to deploy

First of all, clone this repository into your server folder. After cloning, `cd` into the cloned repository and follow these steps:

First, create a Python 3 virtual environment.

`python3 -m venv venv`

Then activate the virtual environment.

`. venv/bin/activate`

Install the dependencies.

`python3 -m pip install flask flask-sqlalchemy flask-mysqldb python-dotenv flask-alembic geojson`

Copy `.env.example` file and set the configuration for your server.

`cp .env.example .env`

To run CityZones Web you will need Passenger WSGI enabled in your server. Follow your HTTP daemon instructions to setup Passenger and finish the deployment.
