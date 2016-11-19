# -*- coding: utf-8 -*-

from flask import Flask, request, render_template, session, flash, redirect, \
    url_for, jsonify # For the web app functionality.
from celery import Celery # Tasks/job management.
from celery.task.control import inspect # Task Statuses.
import dlw_run # The carbon risk model.
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
def save_scenario(uuid, scenario_name, time_period_1, tree_analysis):
    '''
    Store the Celery task UUID along with the input parameter information.
    After the job completes, the UUID can be referred to to update or add output
    and results.
    '''
    con = sq3.connect('db.sqlite')
    cursor = con.cursor()
    sql = "insert into scenario (uuid, scenario_name, created_on, time_period_1, tree_analysis) values ('%s', '%s', CURRENT_TIMESTAMP, %d, %d)" % (uuid, scenario_name, time_period_1, tree_analysis)
    cursor.execute(sql)
    con.commit()
    con.close()

def update_scenario():
    '''
    This function is for updating the information related to a scenario's
    outcome after the Celery job has completed.
    '''    
    
def past_scenarios():
    '''
    Retrieves the summary information of previous run model simulations.
    '''
    # Connect to sqlite database
    con = sq3.connect('db.sqlite')
    sql = "SELECT scenario_id, uuid, created_on, scenario_name FROM scenario"
    cur = con.execute(sql)
    r = cur.fetchall()
    con.close()
    return r

def scenario_details():
    '''
    This function retrieves detailed information about a specific 
    scenario configuration and its outcome.
    '''    
    # Connect to sqlite database
    con = sq3.connect('db.sqlite')
    sql = "SELECT scenario_id, uuid, created_on, scenario_name FROM scenario"
    cur = con.execute(sql)
    r = cur.fetchone()
    con.close()
    return r

# =======================================
# CONTROLLER FUNCTIONS
# =======================================
@app.route('/', methods=['GET', 'POST'])
def index():
    scenarios = past_scenarios()
    return render_template('index.html', items=scenarios)    
    
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
    
@app.route('/scenario/add/', methods=['GET', 'POST'])
def create_scenario():    
    return render_template('create_scenario.html')
    
@app.route('/scenario/run/', methods=['POST'])
def run_scenario():
    print("Inside run_scenario()")
    model_name = request.form.get("model_name")
    tp1 = int(request.form.get("tp1"))
    tree_analysis = int(request.form.get("tree_analysis"))
    tree_final_states = int(request.form.get("tree_final_states"))
    damage_peak_temp = float(request.form.get("damage_peak_temp"))  
    damage_disaster_tail = float(request.form.get("damage_disaster_tail"))    
    
    #task = dlw_run.run_model.apply_async(tp1=tp1, tree_analysis=tree_analysis)
    task = dlw_run.run_model.apply_async(tp1=tp1, tree_analysis=tree_analysis, tree_final_states=tree_final_states, damage_peak_temp=damage_peak_temp, damage_disaster_tail=damage_disaster_tail)
    save_scenario(uuid=task.id, scenario_name=model_name, time_period_1=tp1, tree_analysis=tree_analysis)
    return jsonify({}), 202, {'Location': url_for('task_status',
                                                  task_id=task.id)}

@app.route('/scenario/status/<task_id>')
def task_status(task_id):
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
            'current': r.info.get('current', 0),
            'total': r.info.get('total', 1),
            'status': r.info.get('status', '')
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

@app.route('/scenario/active_jobs/')
def active_jobs():  
    i = inspect()
    return render_template('active_jobs.html', active_jobs= str(i.active()))
    
@app.route('/scenario/details/<string:task_id>', methods=['GET', 'POST'])
def scenario(task_id):
    # Connect to sqlite database
    con = sq3.connect('db.sqlite')
    sql = "SELECT scenario_id, uuid, created_on, scenario_name FROM scenario WHERE uuid = '%s'" % task_id # '466b53bc-d883-4ea7-9d5f-d7dce9183e62'"
    cur = con.execute(sql)
    r = cur.fetchone()
    con.close()
    # Assign result variables to dictionary:
    details = {}
    details['scenario_id'] = r[0]
    details['uuid'] = r[1]
    details['created_on'] = r[2]
    details['scenario_name'] = r[3]
    print("DEBUG: ", task_status(task_id))
    return render_template('scenario_details.html', details=details)
    
if __name__ == '__main__':
    app.run(debug=True)
