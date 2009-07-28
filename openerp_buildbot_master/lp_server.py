from launchpadlib.launchpad import Launchpad, STAGING_SERVICE_ROOT
from launchpadlib.credentials import Credentials
from SimpleXMLRPCServer import SimpleXMLRPCServer
from SimpleXMLRPCServer import SimpleXMLRPCRequestHandler
import os
import threading
class lpServer(threading.Thread):
    host = 'localhost'
    port = 8200
    cachedir = "/home/tiny/.launchpad/cache/"
    lp_credential_file = "/home/tiny/.launchpad/lp_credential2.txt"
    launchpad = False    

    def __init__(self):
        super(lpServer, self).__init__()
        self.launchpad = self.get_lp()

    def get_lp(self):
        if not os.path.isdir(self.cachedir):
            try:
                os.makedirs(self.cachedir)
            except:
                raise 
        if not os.path.isfile(self.lp_credential_file):        
            launchpad = Launchpad.get_token_and_login('openerp', STAGING_SERVICE_ROOT, self.cachedir)        
            launchpad.credentials.save(file(self.lp_credential_file, "w"))
        else:        
            credentials = Credentials()
            credentials.load(open(self.lp_credential_file))
            launchpad = Launchpad(credentials, STAGING_SERVICE_ROOT, self.cachedir)
        return launchpad

    def get_lp_bugs(self, projects):  
        import time      
        launchpad = self.launchpad
        res = {}
        if not launchpad:
            return res
        if not isinstance(projects,list):
            projects = [projects]
        for project in projects:
            result = {}            
            r = {}
            lp_project = launchpad.projects[project]
            result['non-series'] = lp_project.searchTasks()            
            if 'series' in lp_project.lp_collections:
                for series in lp_project.series:
                    result[series.name] = series.searchTasks()                       
            for name, bugs in result.items():                                  
               for bug in bugs:
                    if bug.status == 'New':
                        label = 'new'
                        date = bug.date_created
                    elif bug.status == 'Confirmed':
                        label = 'confirmed'
                        date = bug.date_confirmed
                    elif bug.status == 'In Progress':
                        label = 'inprogress'
                        date = bug.date_in_progress
                    #elif bug.status == 'Fix Committed':
                     #   date = bug.date_fix_committed
                    #elif bug.status == 'Incomplete':
                     #   date = bug.date_left_new
                    else:
                        continue
                    month = date.month
                    if label not in r:
                        r[label] = {}
                        r[label][str(date.year)] = {}
                        r[label][str(date.year)][month] = 1
                        #r[label]['Total'] += 1
                    else:
                        if str(date.year) not in r[label]:
                            r[label][str(date.year)] = {}
                            r[label][str(date.year)][month] = 1
                         #   r[label]['Total'] += 1
                        else:
                            if month not in r[label][str(date.year)]:
                                r[label][str(date.year)][month] = 1
                          #      r[label]['Total'] += 1
                            else:
                                r[label][str(date.year)][month] += 1
                           #     r[label]['Total'] += 1
        
            res[project] = r    
        datasets={}
        for project,types in res.items():
            datasets[project] = {}
            print project,types
            for type,years in types.items():  
                print type,years
                datasets[project][type] = []
                for year, months in years.items():
                    for month,val in months.items():
                        datasets[project][type].append([year,month,val]) 
        return datasets

    def run(self):        
        server = SimpleXMLRPCServer((self.host, self.port))
        server.register_introspection_functions()        
        server.register_function(self.get_lp_bugs)
        server.serve_forever()
        return server

if __name__ == '__main__':
    lp_server = lpServer()
    lp_server.start()
    print 'LP Server is started on %s:%s...' %(lp_server.host, lp_server.port)
    
