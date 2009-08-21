from bzrlib.branch import Branch
from datetime import datetime
import threading
import os
import time

class logServer(threading.Thread):
    def __init__(self):
        self.logdir = 'public_html/Changelog'
        self.logfile = 'log.txt'
        self.locations = {
            '5.0/server':'https://launchpad.net/~openerp/openobject-server/5.0/',
            '5.0/addons':'https://launchpad.net/~openerp/openobject-addons/5.0/',
            'trunk/server':'https://launchpad.net/~openerp/openobject-server/trunk/',
            'trunk/addons':'https://launchpad.net/~openerp/openobject-addons/trunk/',
            'trunk/extra-addons':'https://launchpad.net/~openerp-commiter/openobject-addons/trunk-extra-addons/',
            'trunk/addons-community':'https://launchpad.net/~openerp-community/openobject-addons/trunk-addons-community/'
                        }
        self.last_revno = {}
        super(logServer, self).__init__()

    def get_revisions(self):
        res = {}
        curr_date = datetime.now()         
        for branch, location in self.locations.items():            
            b = Branch.open_containing(location)[0]
            current_revision = b.revno()
            if branch not in self.last_revno:
                self.last_revno[branch] = 0
            if not self.last_revno[branch]:
                revisions = b.revision_history()[(current_revision-100):]
            else:
                revisions = b.revision_history()[self.last_revno[branch]:]
            self.last_revno[branch] = current_revision
            summaries = {}
            
            for r in revisions:
                rev = b.repository.get_revision(r)
                timestamp = datetime.fromtimestamp(rev.timestamp)
                log_month = str(timestamp.month)
                log_year  = str(timestamp.year) 
                if log_year == str(curr_date.year) and log_month == str(curr_date.month - 1):
                    if log_year not in summaries:
                        summaries[log_year] = {}
                        summaries[log_year][log_month] = []
                    else: 
                        if log_month not in summaries[log_year]:
                            summaries[log_year][log_month] = []
                    msg = rev.get_summary().encode('utf-8')
                    app_authors = [rev.get_apparent_author().encode('utf-8')] #rev.get_apparent_authors()
                    ass_bugs = [] #[bug[0] for bug in rev.iter_bugs()]
                    summaries[log_year][log_month].append((msg,ass_bugs,app_authors))
                else:
                    continue
            res[branch] = summaries
        for branch,val in res.items():
            for year,logs in val.items():
                for month,values in logs.items():
                    path = branch.split('/')
                    file_path = os.path.join(os.path.realpath(self.logdir),path[0],path[1]) 
                    try:
                        if not os.path.isdir(file_path):
                            os.makedirs(file_path)
                    except:
                        raise   
                    fp = open(os.path.join(file_path,year+month+self.logfile),'w')
                    fp.write('Change Log of %s for the month of %s\n'%(branch, datetime(int(year),int(month),1).strftime('%B/%Y')))
                    fp.write('======================================\n')
                    for value in values:
                        ass_bugs = ''
                        app_authors = ''
                        if value[1]:
                            ass_bugs = value[1]
                        if value[2]:
                            app_authors = value[2]
                        fp.write("%s  %s by  %s\r"%(value[0].encode('utf-8'),','.join(ass_bugs),','.join(app_authors)))
                    fp.close()
        return True
    
    def run(self): 
        while True:                  
            self.get_revisions()
            time.sleep(3)
        return True
if __name__ == '__main__':    
    log_server = logServer()
    print "--log server started--"
    log_server.start()

