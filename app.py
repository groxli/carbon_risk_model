# -*- coding: utf-8 -*-

from flask import Flask, request, Response, render_template, session, flash, redirect, \
    url_for, jsonify # For the web app functionality.
from functools import wraps    
from celery import Celery # Tasks/job management.
from celery.task.control import inspect # Task Statuses.
import dlw_run # The carbon risk simulator.
import sqlite3 as sq3 # Store and retrieve data parameters and results.

# To start the web app, execute the steps in the following order from the
# project's root directory:
#
#   1) rabbitmq-server
#   2) celery -A dlw_run worker --loglevel=info
#   3) python app.py
#
# If you would like to watch the RabbitMQ logs, the following type of command
# should work depending on where your environment is configured to output
# the log file:
#    tail -f /usr/local/var/log/rabbitmq/rabbit@localhost.log    
#
# Note: if you need to shutdown the RabbitMQ server, use this command:
#   sudo rabbitmqctl stop
#
# Note: if you need to keep the Flask process from halting on terminal
# sign-off, try the following:
#   nohup python  /to/path/app.py &

# =======================================
# APP INITIALIZATION
# =======================================
app = Flask(__name__)
# TODO: NJ: Figure out how to best generate and manage SECRET_KEY for our needs.
app.config['SECRET_KEY'] = 'eU=yv$d$t=#*H-UkRraWf#fR8$GeYc5E'

# Celery configuration
# TODO: NJ: Make configuration-driven.
app.config['CELERY_BROKER_URL'] = 'amqp://'
app.config['CELERY_RESULT_BACKEND'] = 'amqp://'

# Initialize Celery
# TODO: NJ: Add try, except and finally handlers.
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'], backend=app.config['CELERY_RESULT_BACKEND'])

# =======================================
# DATA MODEL FUNCTIONS
# =======================================
def save_package(uuid, package_name, time_period_1, tree_analysis):
    '''
    Store the Celery task UUID along with the input parameter information.
    After the job completes, the UUID can be referred to to update or add output
    and results.
    '''
    con = sq3.connect('db.sqlite')
    cursor = con.cursor()
    sql = "insert into package (uuid, package_name, created_on, time_period_1, tree_analysis, status) values ('%s', '%s', CURRENT_TIMESTAMP, %d, %d, 'PENDING')" % (uuid, package_name, time_period_1, tree_analysis)
    cursor.execute(sql)
    con.commit()
    con.close()
    
def update_package():
    '''
    This function is for updating the information related to a package's
    outcome after the Celery job has completed.
    '''    
    
def past_packages():
    '''
    Retrieves the summary information of previous run package simulations.
    '''
    # Connect to sqlite database
    con = sq3.connect('db.sqlite')
    sql = "SELECT package_id, uuid, created_on, package_name, status FROM package"
    cur = con.execute(sql)
    r = cur.fetchall()
    con.close()
    return r

def package_details():
    '''
    This function retrieves detailed information about a specific 
    package configuration and its outcome.
    '''    
    # Connect to sqlite database
    con = sq3.connect('db.sqlite')
    sql = "SELECT package_id, uuid, created_on, package_name FROM package"
    cur = con.execute(sql)
    r = cur.fetchone()
    con.close()
    return r

# =======================================
# CONTROLLER FUNCTIONS
# =======================================
def check_auth(username, password):
    """
    This function is called to check if a username and
    password combination is valid.
    """
    return username == 'guest' and password == 'tree32'
    
def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'Could not verify your access level for this URL.\n'
    'Login credentials required.', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated
    
@app.route('/', methods=['GET', 'POST'])
@requires_auth
def index():
    packages = past_packages()
    return render_template('index.html', items=packages)    
    
@app.route('/login/', methods=['GET', 'POST'])
def login():
    session['username'] = None
    return render_template('login.html')

@app.route('/login_check/', methods=['POST'])
def login_check():
    print(request.form['username'], request.form['password'])
    if (request.form['username'] == 'dev') and (request.form['password'] == 'tokyo7'):
        print("LOGIN OK")
        session['username'] = request.form['username']
        return redirect(url_for('index'))
    else:
        print("LOGON FAILED")
        return redirect(url_for('login'))
    
@app.route('/logout/', methods=['GET', 'POST'])
def logout():
    session['username'] = None
    return redirect(url_for('login'))  
    
@app.route('/package/add/', methods=['GET', 'POST'])
@requires_auth
def create_package():    
    return render_template('create_package.html')
    
@app.route('/package/run/', methods=['POST'])
@requires_auth
def run_package():
    print("Inside run_package()")
    package_name = request.form.get("package_name")
    tp1 = int(request.form.get("tp1"))
    tree_analysis = int(request.form.get("tree_analysis"))
    tree_final_states = int(request.form.get("tree_final_states"))
    damage_peak_temp = float(request.form.get("damage_peak_temp"))  
    damage_disaster_tail = float(request.form.get("damage_disaster_tail"))    
    
    #task = dlw_run.run_model.apply_async(tp1=tp1, tree_analysis=tree_analysis)
    task = dlw_run.run_model.apply_async(tp1=tp1, tree_analysis=tree_analysis, tree_final_states=tree_final_states, damage_peak_temp=damage_peak_temp, damage_disaster_tail=damage_disaster_tail)
    save_package(uuid=task.id, package_name=package_name, time_period_1=tp1, tree_analysis=tree_analysis)
    return jsonify({}), 202, {'Location': url_for('task_status',
                                                  task_id=task.id)}
                   
@app.route('/package/status/<task_id>')
@requires_auth
def task_status(task_id):
    #r = long_task.AsyncResult(task_id) #DEBUG
    r = celery.AsyncResult(task_id)

    if r.state == 'PENDING':
        response = {
            'state': r.state,
            'current': 0,
            'total': 1,
            'status': 'Pending...'
        }
    elif r.state == 'RUNNING':
        response = {
            'state': r.state,
            'current': 0,
            'total': 1,
            'status': 'Running...'
        }        
    elif r.state != 'FAILURE':
        response = {
            'state': r.state,
            'current': 0,
            'total': 1,
            'status': ''
        }
        if 'result' in r.info:
            response['result'] = r.info['result']
    else:
        # something went wrong in the background job
        response = {
            'state': r.state,
            'current': 1,
            'total': 1,
            'status': str(r.info),  # this is the exception raised
        }
    return jsonify(response)

@app.route('/package/active_jobs/')
@requires_auth
def active_jobs():  
    i = inspect()
    return render_template('active_jobs.html', active_jobs= str(i.active()))
    
@app.route('/package/details/<string:task_id>', methods=['GET', 'POST'])
@requires_auth
def package(task_id):
    # Connect to sqlite database
    con = sq3.connect('db.sqlite')
    sql = "SELECT package_id, uuid, created_on, package_name, cost_per_ton FROM package WHERE uuid = '%s'" % task_id # '466b53bc-d883-4ea7-9d5f-d7dce9183e62'"
    cur = con.execute(sql)
    r = cur.fetchone()
    con.close()
    # Assign result variables to dictionary:
    details = {}
    details['package_id'] = r[0]
    details['uuid'] = r[1]
    details['created_on'] = r[2]
    details['package_name'] = r[3]
    details['cost_per_ton'] = r[4]
    print("DEBUG: ", task_status(task_id))
    return render_template('package_details.html', details=details)
    
if __name__ == '__main__':
    app.run(debug=True)

