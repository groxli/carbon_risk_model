# -*- coding: utf-8 -*-

# filename: dlw_log.py
# last_updated: 2017/01/02
# updated_by: Nate Jensen <nate@groxli.com>
# description: This is a utility file that writes the progres of a job/run
#       to a generic outputs/log.txt file so that it is easier for the engineer
#       to monitor and track the progress of larger job statuses without
#       needing to be concerned there is a rogue process that will not return
#       because of a parameter that was set far beyond the 
#       computational power of a given environment.
#
# IMPORTANT: This file is currently intended for debugging--not production.
#           We need to add Logging configuration capabilities for 
#           production deployment.

import logging

class LogUtil(object):
    def __init__(self):
        self.name = 'My Logger'
        self.logger = logging.getLogger('Carbon Risk')
        hdlr = logging.FileHandler('./outputs/dlw.log')
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        hdlr.setFormatter(formatter)
        self.logger.addHandler(hdlr)
        self.logger.setLevel(logging.DEBUG)        
        
    def log_it(self, m):
        self.logger.debug(m)

def main():
    print("Logging utility...")
    
if __name__ == "__main__":
    main()