from bzrlib.branch import Branch
from datetime import datetime
import threading
import os
import time

nt_revs = []
nt_str = []
class logServer(threading.Thread):
    def __init__(self):
        self.logdir = 'public_html/Changelog'        
        self.logfile = 'changelog.txt'
        self.open_file = {}
        self.locations = {
            '5.0/server':'https://launchpad.net/~openerp/openobject-server/5.0/',
            '5.0/addons':'https://launchpad.net/~openerp/openobject-addons/5.0/',
            '5.0/extra-addons':'https://launchpad.net/~openerp-commiter/openobject-addons/5.0-extra-addons/',
            'trunk/server':'https://launchpad.net/~openerp/openobject-server/trunk/',
            'trunk/addons':'https://launchpad.net/~openerp/openobject-addons/trunk/',
            'trunk/extra-addons':'https://launchpad.net/~openerp-commiter/openobject-addons/trunk-extra-addons/',
            'trunk/addons-community':'https://launchpad.net/~openerp-community/openobject-addons/trunk-addons-community/'
                        }
        self.last_revno = {}
        self.latest_tag_file = {}
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
                self.get_tags(branch,location)
                self.last_revno[branch] = current_revision
                continue
            else:
                revisions = b.revision_history()[self.last_revno[branch]:]
                self.last_revno[branch] = current_revision
                if self.open_file[branch]:
                    fp = open(self.open_file[branch],'ab+')
                else:
                    self.get_tags(branch,location)
                bugs=[]
                for r in revisions:
                    rev = b.repository.get_revision(r)
                    rev_no = b.revision_id_to_revno(r)
                    msg = rev.get_summary().encode('utf-8')
                    app_authors = [rev.get_apparent_author().encode('utf-8')] #rev.get_apparent_authors()
                    ass_bugs =[[rev_no,bug] for bug in rev.iter_bugs()]
                    bugs.append(ass_bugs)
                    try:
                        fp.write("%s %s  %s by  %s\r"%(str(rev_no),msg,','.join(ass_bugs),','.join(app_authors)))
                    except:
                        nt_str.append(msg)
                for item in bugs:
                    for bug in item:
                        rev_no=bug[0]
                        bug=bug[1]
                        fp.write("%s\t%s\n"%(rev_no,'\t'.join(bug)))
                fp.close()
        return True
    
    def run(self): 
        while True:                  
            self.get_revisions()
            print "\n\nFollowing revisions not found in mapper :\n%s"%(','.join(nt_revs))
            print "\n\nFollowing msgs could not be written to log files :\n%s"%(','.join(nt_str))
            time.sleep(3)
        return True

    def get_tags(self,branch,location):
            b = Branch.open_containing(location)[0]
            tags = b.tags.get_tag_dict()
            mappings = b.get_revision_id_to_revno_map()
            n = {}
            t = []
            for k in tags:
                try:
                    n[k] = mappings[tags[k]]
                except:
                    continue
            for k in tags:
                try:
                    t.append(mappings[tags[k]],k)
                except:
                    continue
            ls = [[[v],k] for k,v in n.iteritems()]
            ls.sort()
            #ls=ls[0:2]
            f=ls
            for i in range(0,len(ls)):
                    f[i]=ls[i]
                    temp = [mappings[l] for l in mappings if str(mappings[l]).startswith( '('+str(ls[i][0][0][0])+',')]
                    temp.sort()    
                    index = temp.index(ls[i][0][0])
                    rev_list = temp[1:index]
                    f[i][0].extend(rev_list)
                    f[i][0].sort()
                    if i+1 < len(ls):
                        ls[i+1][0].extend(temp[index:])

            jp = f
            for i in range(0,len(jp)):
                jp[i][0].sort()
                fi = jp[i][0][0][0] + 1
                l = jp[i][0][-1][0]
                for j in range(fi,l):
                        temp1 = [mappings[l] for l in mappings if str(mappings[l]).startswith( '('+str(j)+',')]
                        temp1.sort()
                        jp[i][0].extend(temp1)
                        jp[i][0].sort()
            mapp={}
            for k,v in mappings.iteritems():
                mapp[v] = k
            path = branch.split('/')
            file_path = os.path.join(os.path.realpath(self.logdir),path[0],path[1])             
            try:
                if not os.path.isdir(file_path):
                    os.makedirs(file_path)
            except:
                raise
            file_path = os.path.join(file_path,self.logfile)
            self.open_file[branch] = file_path
            fp = open(file_path,'w')    
            for i in range(0,len(jp)):
                tag_data = jp[i]
                tag = tag_data[1]
                data = tag_data[0]                
                
                fp.write('\n\n%s\n======================================\n'%(tag))
                bugs=[]       
                print 'len of data', len(data)
                for rev_no in data:                    
                    try:
                        r = mapp[rev_no]
                        rev = b.repository.get_revision(r)
                        msg = rev.get_summary().encode('utf-8')
                        app_authors = [rev.get_apparent_author().encode('utf-8')] #rev.get_apparent_authors()                                            
                        try:
                            fp.write("%s (by %s)\r\n"%(msg, ','.join(app_authors)))
                        except Exception, e:
                            print e
                            nt_str.append(msg)
                        #for bug in rev.iter_bugs():
                        #    bugs.append([rev_no,bug])
                    except:
                        nt_revs.append(rev_no)
                        continue
                if bugs:
                    fp.write("\n\n\n")
                    fp.write('Fix bugs : %s\n======================================\n'%(tag))
                    for bug in bugs:
                        rev_no=bug[0]
                        bug=bug[1]
                        fp.write("%s\n"%('\t'.join(bug)))
            fp.close()



if __name__ == '__main__':    
    log_server = logServer()
    print "--log server started--"
    log_server.start()

