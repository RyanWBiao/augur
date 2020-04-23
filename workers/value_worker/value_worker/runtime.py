import json
import logging
import os
import subprocess
import sys

import click
import requests
from flask import Flask, Response, jsonify, request

from value_worker.worker import ValueWorker

from workers.standard_methods import read_config

def create_server(app, gw):
    """ Consists of AUGWOP endpoints for the broker to communicate to this worker
    Can post a new task to be added to the workers queue
    Can retrieve current status of the worker
    Can retrieve the workers config object
    """

    @app.route("/AUGWOP/task", methods=['POST', 'GET'])
    def augwop_task():
        """ AUGWOP endpoint that gets hit to add a task to the workers queue or is used to get the heartbeat/status of worker
        """
        # POST a task to be added to the queue
        if request.method == 'POST':
            logging.info("Sending to work on task: {}".format(str(request.json)))
            app.value_worker.task = request.json
            return Response(response=request.json,
                        status=200,
                        mimetype="application/json")
        if request.method == 'GET': #will retrieve the current tasks/status of the worker
            return jsonify({
                "status": "not implemented"
            })
        return Response(response=request.json,
                        status=200,
                        mimetype="application/json")

    @app.route("/AUGWOP/heartbeat", methods=['GET'])
    def heartbeat():
        if request.method == 'GET':
            return jsonify({
                "status": "alive"
            })

    @app.route("/AUGWOP/config")
    def augwop_config():
        """ Retrieve worker's config
        """
        return app.value_worker.config

@click.command()
@click.option('--augur-url', default='http://localhost:5000/', help='Augur URL')
@click.option('--host', default='localhost', help='Host')
@click.option('--port', default=51239, help='Port')
@click.option('--scc-bin', default=f'{os.environ["HOME"]}/go/bin/scc', help='scc binary')
def main(augur_url, host, port, scc_bin):
    """ Declares singular worker and creates the server and flask app that it will be running on
    """

    app = Flask(__name__)

    #load credentials
    broker_host = read_config("Server", "host", "AUGUR_HOST", "0.0.0.0")
    broker_port = read_config("Server", "port", "AUGUR_PORT", 5000)
    database_host = read_config('Database', 'host', 'AUGUR_DB_HOST', 'host')
    worker_info = read_config('Workers', 'value_worker', None, 
        {
            "port": 37300,
            "scc_bin": "/home/sean/go/bin/scc"
        })


    worker_port = worker_info['port'] if 'port' in worker_info else port

    while True:
        try:
            r = requests.get("http://{}:{}/AUGWOP/heartbeat".format(host, worker_port)).json()
            if 'status' in r:
                if r['status'] == 'alive':
                    worker_port += 1
        except:
            break

    logging.basicConfig(filename='worker_{}.log'.format(worker_port), filemode='w', level=logging.INFO)

    config = { 
            "id": "com.augurlabs.core.value_worker.{}".format(worker_port),
            "broker_port": broker_port,
            "broker_host": broker_host,
            "location": "http://{}:{}".format(read_config('Server', 'host', 'AUGUR_HOST', 'localhost'),worker_port),
            "host": database_host,
            "key": read_config("Database", "key", "AUGUR_GITHUB_API_KEY", "key"),
            "password": read_config('Database', 'password', 'AUGUR_DB_PASSWORD', 'password'),
            "port": read_config('Database', 'port', 'AUGUR_DB_PORT', 'port'),
            "user": read_config('Database', 'user', 'AUGUR_DB_USER', 'user'),
            "database": read_config('Database', 'name', 'AUGUR_DB_NAME', 'database'),
            "endpoint": "https://bestpractices.coreinfrastructure.org/projects.json",
            'scc_bin': worker_info['scc_bin'],
            'repo_directory': read_config('Workers', 'facade_worker', None, None)['repo_directory'],
        }

    # Create the worker that will be running on this server with specified config
    app.value_worker = ValueWorker(config)

    create_server(app, None)
    logging.info("Starting Flask App with pid: " + str(os.getpid()) + "...")


    app.run(debug=app.debug, host=host, port=worker_port)
    if app.value_worker._child is not None:
        app.value_worker._child.terminate()
    try:
        requests.post(f'http://{server["host"]}:{server["port"]}/api/unstable/workers/remove', json={"id": config['id']})
    except:
        pass

    logging.info("Killing Flask App: " + str(os.getpid()))
    os.kill(os.getpid(), 9)
