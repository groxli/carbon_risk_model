# -*- coding: utf-8 -*-

# filename: performance_tests.py
# last_updated: 2016/12/14
# updated_by: Nate Jensen <nate@groxli.com>
# description: This python code is a performance test wrapper around the 
#           dlw_run.py carbon risk code. This file reads in an Excel file
#           containing different test scenarios and then times the
#           run time and stores the results into an output Excel file.

import dlw_run # The code to be tested.
import time # For measuring the run time.
import pandas as pd # For loading the scenario configs and outputting the results.
import psutil # For getting system info.
import sys # For key system info.

df_s = pd.read_excel("performance_scenarios_short.xlsx")
output_filename = "outputs/performance_results_%s.xlsx" % time.strftime("%Y-%m-%d-%H%M%S")

if __name__ == '__main__':
    r = [] # Array for storing the run time results.
    for index, row in df_s.iterrows():
        print("Running performance scenario:", index)
        ts = time.time() # Scenario start time.
        dlw_run.run_model(tp1=row.tp1, tree_analysis=row.tree_analysis)
        te = time.time() - ts # Scenario end time.
        d = {} # Temporary dictionary for storing the run time results.
        d['tp1'] = row.tp1
        d['tree_analysis'] = row.tree_analysis
        d['os'] = sys.platform
        d['python_version'] = sys.version
        d['run_time'] = te
        d['cpu_count'] = psutil.cpu_count()
        d['total_mem'] = psutil.virtual_memory().total / 1024 / 1024
        d['mem_used'] = psutil.virtual_memory().used / 1024 / 1024
        d['mem_free'] = psutil.virtual_memory().free / 1024 / 1024
        d['mem_inactive'] = psutil.virtual_memory().inactive / 1024 / 1024
        r.append(d)
    df_r = pd.DataFrame(r) # Create a results Data Frame.
    df_r.to_excel(output_filename)