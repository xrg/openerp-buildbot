import time
import socket
import xmlrpclib

waittime = 10
wait_count = 0
wait_limit = 12

class buildbot_xmlrpc:
    def __init__(self, host='localhost', port='8069', dbname='buildbot'):
        self.host = host
        self.dbname = dbname
        self.port = port
    
    def execute(self, connector, method, *args):
        global wait_count
        res = False
        try:
            res = getattr(connector,method)(*args)
        except socket.error,e:
            if e.args[0] == 111:
                if wait_count > wait_limit:
                    print "Server is taking too long to start, it has exceeded the maximum limit of %d seconds."%(wait_limit)
                    clean()
                    sys.exit(1)
                print 'Please wait %d sec to start server....'%(waittime)
                wait_count += 1
                time.sleep(waittime)
                res = execute(connector, method, *args)
            else:
                raise e
        wait_count = 0
        return res

    def _login(self, login_id = 'admin', login_pwd='a'):
        conn = xmlrpclib.ServerProxy('http://'+self.host+':'+ self.port + '/xmlrpc/common')
        uid = self.execute(conn,'login', self.dbname, login_id, login_pwd)
        return uid
    
    def _search(self, uid=False, login_pwd='a', args=[]):
        con = xmlrpclib.ServerProxy('http://'+self.host+':'+self.port+'/xmlrpc/object')
        ids = self.execute(con,'execute', self.dbname, uid, login_pwd,'report.buildbot.data','search',[])		
        return ids
      
    def _read(self, uid=False, login_pwd='a', ids=[]):
        con = xmlrpclib.ServerProxy('http://'+self.host+':'+self.port+'/xmlrpc/object')
        result = self.execute(con,'execute', self.dbname, uid, login_pwd, 'report.buildbot.data','read',ids)
        print result
	

buildbot_xmlrpc = buildbot_xmlrpc() 
uid = buildbot_xmlrpc._login()
ids = buildbot_xmlrpc._search(uid=uid)
buildbot_xmlrpc._read(uid=uid, ids=ids)

