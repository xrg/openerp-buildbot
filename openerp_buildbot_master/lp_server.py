#!/usr/bin/python
# -*- encoding: utf-8 -*-
from launchpadlib.launchpad import Launchpad, EDGE_SERVICE_ROOT
from launchpadlib.credentials import Credentials
from SimpleXMLRPCServer import SimpleXMLRPCServer
from SimpleXMLRPCServer import SimpleXMLRPCRequestHandler
import os
import threading
import pickle
import time

class lpServer(threading.Thread):
    host = 'localhost'
    port = 8200
    cachedir = ".launchpad/cache/"
    lp_credential_file = ".launchpad/lp_credential2.txt"
    bugs_pck = 'bugs.pck'
    launchpad = False  
    projects = ['openobject']  

    def __init__(self):
        super(lpServer, self).__init__()
        self.launchpad = self.get_lp()

    def get_lp(self):
        launchpad = False
        if not os.path.isdir(self.cachedir):
            try:
                os.makedirs(self.cachedir)
            except:
                raise 
        if not os.path.isfile(self.lp_credential_file): 
            try:       
                launchpad = Launchpad.get_token_and_login('openerp', EDGE_SERVICE_ROOT, self.cachedir)        
                launchpad.credentials.save(file(self.lp_credential_file, "w"))
            except:
                print 'Service Unavailable !'
        else:        
            credentials = Credentials()
            credentials.load(open(self.lp_credential_file))
            launchpad = Launchpad(credentials, EDGE_SERVICE_ROOT, self.cachedir)
        return launchpad
    
    def get_lp_bugs(self, projects):
        launchpad = self.launchpad
        res = {}
        if not launchpad:
            return res
        if not isinstance(projects,list):
            projects = [projects]
        
        def store_bugs(label='',r={},date=''):
            if label not in r:
                r[label] = {}
                r[label][str(date.year)] = {}
                r[label][str(date.year)][date.month] = 1
            else:
                if str(date.year) not in r[label]:
                    r[label][str(date.year)] = {}
                    r[label][str(date.year)][date.month] = 1
                else:
                    if date.month not in r[label][str(date.year)]:
                        r[label][str(date.year)][date.month] = 1
                    else:
                        r[label][str(date.year)][date.month] += 1
            return r

        bug_status = ['New','Confirmed','In Progress']

        for project in projects:
            result = {}            
            r = {}
            lp_project = launchpad.projects[project]
            result['non-series'] = lp_project.searchTasks(status=bug_status)              
            if 'series' in lp_project.lp_collections:
                for series in lp_project.series:
                    result[series.name] = series.searchTasks()  
            label = ''
            for name, bugs in result.items():                
               for bug in bugs:
                    if bug.importance == 'Wishlist':
                        label = 'wishlist'
                    elif bug.status == 'New':
                        label = 'new'
                    elif bug.status in ('Confirmed','In Progress'):
                        label = 'confirmed'
                    if label:
                        date = bug.date_created
                        r = store_bugs(label,r,date) 
            res[project] = r
        new = []
        confirmed = []
        wishlist = []
        for project,types in res.items():
            for type,years in types.items():  
                for year, months in years.items():
                    for month,val in months.items():
                        if type == 'new':
                            new.append([year,month,val]) 
                        elif type == 'confirmed':
                            confirmed.append([year,month,val])
                        elif type == 'wishlist':
                            wishlist.append([year,month,val])
        datasets = [new,confirmed,wishlist]
        return datasets

    def save_dataset(self):        
        datasets = ''
        while not datasets:
            datasets = self.get_lp_bugs(self.projects)
        last_update = time.strftime('%B %d %I:%M:%S %Y %Z', time.localtime(time.time()))
        datasets = [last_update, datasets]
        fp = open('bugs.pck','wb')
        pickle.dump(datasets,fp)
        fp.close()
        

    def run(self): 
        while True:                  
            self.save_dataset()
            time.sleep(3000)
        return True

if __name__ == '__main__':    
    lp_server = lpServer()
    lp_server.start()
    print 'LP Server is started ....'
    
