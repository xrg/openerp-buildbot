#!/usr/bin/python
# -*- coding: utf-8 -*-
##############################################################################
#    
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.     
#
##############################################################################

import xmlrpclib
import ConfigParser
import optparse
import sys
import thread
import threading
import os
import time
import pickle
import base64
import socket
import subprocess
import select
import re

admin_passwd = 'admin'

def to_decode(s):
    try:
        return s.encode('utf-8')
    except UnicodeError:
        try:
            return s.encode('latin')
        except UnicodeError:
            try:
                return s.decode('ascii')
            except UnicodeError:
                return s
# --- cut here
import logging
import types

def xmlescape(sstr):
    return sstr.replace('<','&lt;').replace('>','&gt;').replace('&','&amp;')

class XMLStreamHandler(logging.FileHandler):
    """ An xml-like logging handler, writting stream into a file.
    
    Note that we don't use any xml dom class here, because we want
    our output to be immediately streamed into a file. Upon any 
    crash of the script, the partial xml will be useful.
    """
    def __init__(self, filename, encoding='UTF-8'):
        logging.FileHandler.__init__(self, filename, mode='w', 
                encoding=encoding, delay=False)
        # now, open the file and write xml prolog
        self.formatter = XMLFormatter()
        self.stream.write('<?xml version="1.0", encoding="%s" ?>\n<log>' % encoding)
        
    def close(self):
        # write xml epilogue
        self.stream.write('</log>\n')
        logging.FileHandler.close(self)

    # Note: we need not re-implement emit, because a special formatter
    # will be used

class XMLFormatter(logging.Formatter):
    """ A special formatter that will output all fields in an xml-like
    struct """
    
    def format(self, record):
        """ Put everything in xml format """
        
        s = '<rec name="%s" level="%s" time="%s" >' % \
            (record.name, record.levelno, record.created)

        if False and (record.filename or record.module or record.lineno):
            s += '<code filename="%s" module="%s" line="%s" />' % \
                    (record.filename, record.module, record.lineno)


        if record.exc_info and not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)

        if record.exc_text:
            s+= '<exception>%s</exception>' % xmlescape(record.exc_text)

        s+= xmlescape(record.getMessage())
        s+= '</rec>'

        return s.decode('utf-8')

# --- cut here

class server_thread(threading.Thread):
    
    def regparser(self, section, regex, funct):
        self.__parsers.setdefault(section, []).append( (regex, funct) )

    def setRunning(self, section, level, line):
        self.log.info("Server is ready!")
        self.is_ready = True
        
    def setListening(self, section, level, mobj):
        self.log.info("Server listens %s at %s:%s" % mobj.group(1, 2, 3))
        self._lports[mobj.group(1)] = mobj.group(3)

    def __init__(self, root_path, port, netport, addons_path, pyver=None, timed=False):
        threading.Thread.__init__(self)
        self.root_path = root_path
        self.port = port
        # self.addons_path = addons_path
        self.args = [ 'python%s' %(pyver or ''), '%sopenerp-server.py' % root_path,
                    '--httpd-port=%s' % port ,
                    '--netrpc-port=%s' % netport,
                    '--addons-path=%s' % addons_path ]
        if timed:
            self.args.insert(0, 'time')
        self.proc = None
        self.is_running = False
        self.is_ready = False
        self._lports = {}
        # self.is_terminating = False
        
        # Regular expressions:
        self.linere = re.compile(r'\[(.*)\] ([A-Z]+):([\w\.-]+):(.*)$')
        
        self.log = logging.getLogger('srv.thread')
        self.log_sout = logging.getLogger('server.stdout')
        self.log_serr = logging.getLogger('server.stderr')

        self.__parsers = {}
        self.regparser('web-services', 
                'the server is running, waiting for connections...', 
                self.setRunning)
        self.regparser('web-services',
                re.compile(r'starting (.+) service at ([0-9\.]+) port ([0-9]+)'),
                self.setListening)

    def stop(self):
        if (not self.is_running) and (not self.proc):
            time.sleep(2)

        if not self.proc :
            self.log.error("Program has not started")
        elif self.proc.returncode is not None:
            self.log.warning("Program is not running")
        else:
            self.log.info("Terminating..")
            self.proc.terminate()
            self.log.info('Terminated.')
            
            # TODO: kill if not terminate right.
        
    def run(self):
        try:
            self.log.info("will run: %s", ' '.join(self.args))
            self.proc = subprocess.Popen(self.args, shell=False, cwd=None, 
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.is_running = True
            self.log.info("server running at pid: %d", self.proc.pid)
            pob = select.poll()
            pob.register(self.proc.stdout)
            pob.register(self.proc.stderr)
            fdd = { self.proc.stdout.fileno(): self.proc.stdout ,
                    self.proc.stderr.fileno(): self.proc.stderr }
        
            while True:
                self.proc.poll()
                if self.proc.returncode is not None:
                    break
                # Now, see if we have output:
                p = pob.poll(10000)
                for fd, event in p:
                    if event == select.POLLIN:
                        r = fdd[fd].readline()
                        if r.endswith("\n"):
                            r = r[:-1]
                        if not r:
                            continue
                        m = self.linere.match(r)
                        if m:
                            for regex, funct in self.__parsers.get(m.group(3),[]):
                                if isinstance(regex, basestring):
                                    if regex == m.group(4):
                                        funct(m.group(3), m.group(2), m.group(4))
                                else:  # elif isinstance(regex, re.RegexObject):
                                    mm = regex.match(m.group(4))
                                    if mm:
                                        funct(m.group(3), m.group(3), mm)
                   
                        # now, print the line at stdout
                        if fdd[fd] is self.proc.stdout:
                            olog = self.log_sout
                        else:
                            olog = self.log_serr
                        olog.info(r)

            self.is_ready = False
            self.log.info("Finished server with: %d", self.proc.returncode)
        finally:
            self.is_running = False
        
    def start_full(self):
        """ start and wait until server is up, ready to serve
        """
        self.start()
        time.sleep(1)
        t = 0
        while not self.is_ready:
            if not self.is_running:
                raise Exception("Server cannot start")
            if t > 120:
                self.stop()
                raise Exception("Server took too long to start")
            time.sleep(1)
            t += 1
        if self._lports.get('HTTP') != str(self.port):
            self.log.warning("server does not listen HTTP at port %s" % self.port)
        return True

def execute(connector, method, *args):
    global server
    res = False
    if not server.is_ready:
        print "Server not ready, cannot execute %s" % method
        return False

    res = getattr(connector,method)(*args)
    return res

def login(uri, dbname, user, pwd):
    conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/common')
    uid = execute(conn,'login',dbname, user, pwd)
    return uid

def import_translate(uri, user, pwd, dbname, translate_in):
    uid = login(uri, dbname, user, pwd)
    if uid:
        conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/wizard')
        wiz_id = execute(conn,'create',dbname, uid, pwd, 'module.lang.import')
        for trans_in in translate_in:
            lang,ext = os.path.splitext(trans_in.split('/')[-1])
            state = 'init'
            datas = {'form':{}}
            while state!='end':
                res = execute(conn,'execute',dbname, uid, pwd, wiz_id, datas, state, {})
                if 'datas' in res:
                    datas['form'].update( res['datas'].get('form',{}) )
                if res['type']=='form':
                    for field in res['fields'].keys():
                        datas['form'][field] = res['fields'][field].get('value', False)
                    state = res['state'][-1][0]
                    trans_obj = open(trans_in)
                    datas['form'].update({
                        'name': lang,
                        'code': lang,
                        'data' : base64.encodestring(trans_obj.read())
                    })
                    trans_obj.close()
                elif res['type']=='action':
                    state = res['state']


def check_quality(uri, user, pwd, dbname, modules, quality_logs):
    uid = login(uri, dbname, user, pwd)
    quality_logs += 'quality-logs'
    if uid:
        conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/object')
        final = {}
        for module in modules:
            qualityresult = {}
            test_detail = {}
            quality_result = execute(conn,'execute', dbname, uid, pwd,'module.quality.check','check_quality',module)
            detail_html = ''
            html = '''<html><body><a name="TOP"></a>'''
            html +="<h1> Module: %s </h1>"%(quality_result['name'])
            html += "<h2> Final score: %s</h2>"%(quality_result['final_score'])
            html += "<div id='tabs'>"
            html += "<ul>"
            for x,y,detail in quality_result['check_detail_ids']:
                test = detail.get('name')
                msg = detail.get('message','')
                score = round(float(detail.get('score',0)),2)
                html += "<li><a href=\"#%s\">%s</a></li>"%(test.replace(' ','-'),test)
                detail_html +='''<div id=\"%s\"><h3>%s (Score : %s)</h3><font color=red><h5>%s</h5></font>%s</div>'''%(test.replace(' ', '-'), test, score, msg, detail.get('detail', ''))
                test_detail[test] = (score,msg,detail.get('detail',''))
            html += "</ul>"
            html += "%s"%(detail_html)
            html += "</div></body></html>"
            if not os.path.isdir(quality_logs):
                os.mkdir(quality_logs)
            fp = open('%s/%s.html'%(quality_logs,module),'wb')
            fp.write(to_decode(html))
            fp.close()
            #final[quality_result['name']] = (quality_result['final_score'],html,test_detail)

        #fp = open('quality_log.pck','wb')
        #pck_obj = pickle.dump(final,fp)
        #fp.close()
        #print "LOG PATH%s"%(os.path.realpath('quality_log.pck'))
        return True
    else:
        print 'Login Failed...'
        return False

def get_ostimes(uri, prev=None):
    try:
        conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/common')
        ost = execute(conn,'get_os_time', admin_passwd)
        if prev is not None:
            for i in range(0,5):
                ost[i] -= prev[i]
        return ost
    except Exception, e:
        print "exception:", e
        return ( 0.0, 0.0, 0.0, 0.0, 0.0 )


def wait(id,url=''):
    progress=0.0
    sock2 = xmlrpclib.ServerProxy(url+'/xmlrpc/db')
    while not progress==1.0:
        progress,users = execute(sock2,'get_progress',admin_passwd, id)
    return True


def create_db(uri, dbname, user='admin', pwd='admin', lang='en_US'):
    conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/db')
    obj_conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/object')
    wiz_conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/wizard')
    login_conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/common')
    db_list = execute(conn, 'list')
    if dbname in db_list:
        raise Exception("Database already exists, drop it first!")
    id = execute(conn,'create',admin_passwd, dbname, True, lang)
    wait(id,uri)
    install_module(uri, dbname, ['base_module_quality'],user=user,pwd=pwd)
    return True

def drop_db(uri, dbname):
    conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/db')
    db_list = execute(conn,'list')
    if dbname in db_list:
        execute(conn, 'drop', admin_passwd, dbname)
    return True

def make_links(uri, uid, dbname, source, destination, module, user, pwd):
    raise DeprecationWarning
    if module in ('base','quality_integration_server'):
        return True
    # FIXME: obsolete in 6.0! Better, use the multiple addons paths
    # feature and not affect our filesystem.
    if os.path.islink(destination + '/' + module):
        os.unlink(destination + '/' + module)                
    for path in source:
        if os.path.isdir(path + '/' + module):
            os.symlink(path + '/' + module, destination + '/' + module)
            obj_conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/object')
            execute(obj_conn, 'execute', dbname, uid, pwd, 'ir.module.module', 'update_list')
            module_ids = execute(obj_conn, 'execute', dbname, uid, pwd, 'ir.module.module', 'search', [('name','=',module)])
            if len(module_ids):
                data = execute(obj_conn, 'execute', dbname, uid, pwd, 'ir.module.module', 'read', module_ids[0],['name','dependencies_id'])
                dep_datas = execute(obj_conn, 'execute', dbname, uid, pwd, 'ir.module.module.dependency', 'read', data['dependencies_id'],['name'])
                for dep_data in dep_datas:
                    make_links(uri, uid, dbname, source, destination, dep_data['name'], user, pwd)
    return False

def install_module(uri, dbname, modules, user='admin', pwd='admin'):
    uid = login(uri, dbname, user, pwd)
    if not uid:
        raise Exception('cannot login')
    
    # what buttons to press at each state:
    form_presses = { 'init': 'start', 'next': 'start', 'start': 'end' }
    if True:
        obj_conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/object')
        wizard_conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/wizard')
        module_ids = execute(obj_conn, 'execute', dbname, uid, pwd, 'ir.module.module', 'search', [('name','in',modules)])
        if not module_ids:
	    raise Exception("Cannot find any modules to install!")
        execute(obj_conn, 'execute', dbname, uid, pwd, 'ir.module.module', 'button_install', module_ids)
        wiz_id = execute(wizard_conn, 'create', dbname, uid, pwd, 'module.upgrade.simple')
        state = 'init'
        datas = {}
        #while state!='menu':
        i = 0
        
        while state!='end':
            res = execute(wizard_conn, 'execute', dbname, uid, pwd, wiz_id, datas, state, {})
            i += 1
            if i > 100:
                raise RuntimeError("Too many wizard steps")
            
            next_state = 'end'
            if res['type'] == 'form':
                if state in form_presses:
                    next_state = form_presses[state]
                pos_states = [ x[0] for x in res['state'] ]
                if next_state in pos_states:
                    print "Pressing button for %s state" % next_state
                    state = next_state
                else:
                    print "State %s not found in %s, forcing end" % (next_state, pos_states)
                    state = 'end'
            else:
                print "State:", state, " Res:", res
        print "Wizard ended in %d steps" % i
    return True

def upgrade_module(uri, dbname, modules, user='admin', pwd='admin'):
    uid = login(uri, dbname, user, pwd)
    if uid:
        obj_conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/object')
        wizard_conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/wizard')
        module_ids = execute(obj_conn, 'execute', dbname, uid, pwd, 'ir.module.module', 'search', [('name','in',modules)])
        execute(obj_conn, 'execute', dbname, uid, pwd, 'ir.module.module', 'button_upgrade', module_ids)
        wiz_id = execute(wizard_conn, 'create', dbname, uid, pwd, 'module.upgrade.simple')
        state = 'init'
        datas = {}
        #while state!='menu':
        while state!='end':
            res = execute(wizard_conn, 'execute', dbname, uid, pwd, wiz_id, datas, state, {})
            if state == 'init':
                state = 'start'
            elif state == 'start':
                state = 'end'

    return True





usage = """%prog command [options]

Basic Commands:
    start-server         Start Server
    create-db            Create new database
    drop-db              Drop database
    install-module [<m> ...]   Install module
    upgrade-module [<m> ...]   Upgrade module
    install-translation        Install translation file
    check-quality  [<m ...]    Calculate quality and dump quality result into quality_log.pck using pickle
"""
parser = optparse.OptionParser(usage)
parser.add_option("--modules", dest="modules", action="append",
                     help="specify modules to install or check quality")
parser.add_option("--addons-path", dest="addons_path", help="specify the addons path")
parser.add_option("--quality-logs", dest="quality_logs", help="specify the path of quality logs files which has to stores")
parser.add_option("--root-path", dest="root_path", help="specify the root path")
parser.add_option("-p", "--port", dest="port", help="specify the TCP port", type="int")
parser.add_option("--net_port", dest="netport",help="specify the TCP port for netrpc")
parser.add_option("-d", "--database", dest="db_name", help="specify the database name")
parser.add_option("--login", dest="login", help="specify the User Login")
parser.add_option("--password", dest="pwd", help="specify the User Password")
parser.add_option("--translate-in", dest="translate_in",
                     help="specify .po files to import translation terms")
parser.add_option("--extra-addons", dest="extra_addons",
                     help="specify extra_addons and trunkCommunity modules path ")

(opt, args) = parser.parse_args()
if len(args) < 1:
    parser.error("incorrect number of arguments")
command = args[0]
if command not in ('start-server','create-db','drop-db','install-module','upgrade-module','check-quality','install-translation'):
    parser.error("incorrect command")

def die(cond, msg):
    if cond:
        print msg
        sys.exit(1)

lmodules = opt.modules or []
if command in ('install-module', 'upgrade-module', 'check-quality'):
    lmodules += args[1:]

die(lmodules and (not opt.db_name),
        "the modules option cannot be used without the database (-d) option")

die(opt.translate_in and (not opt.db_name),
        "the translate-in option cannot be used without the database (-d) option")

options = {
    'addons-path' : opt.addons_path or 'addons',
    'quality-logs' : opt.quality_logs or '',
    'root-path' : opt.root_path or '',
    'translate-in': [],
    'port' : opt.port or 8069,
    'netport':opt.netport or 8070,
    'database': opt.db_name or 'terp',
    'modules' : lmodules,
    'login' : opt.login or 'admin',
    'pwd' : opt.pwd or 'admin',
    'extra-addons':opt.extra_addons or []
}

import logging
def init_log():
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    hnd = XMLStreamHandler('test.log')
    log.addHandler(hnd)
    log.addHandler(logging.StreamHandler())
    
init_log()

logger = logging.getLogger('bqi')

# Hint:i18n-import=purchase:ar_AR.po+sale:fr_FR.po,nl_BE.po
if opt.translate_in:
    translate = opt.translate_in
    for module_name,po_files in map(lambda x:tuple(x.split(':')),translate.split('+')):
        for po_file in po_files.split(','):
            if module_name == 'base':
                po_link = '%saddons/%s/i18n/%s'%(options['root-path'],module_name,po_file)
            else:
                po_link = '%s/%s/i18n/%s'%(options['addons-path'], module_name, po_file)
            options['translate-in'].append(po_link)

uri = 'http://localhost:' + str(options['port'])

server = server_thread(root_path=options['root-path'], port=options['port'],
                        netport=options['netport'], addons_path=options['addons-path'])

logger.info('start of script')
try:
    server.start_full()
    ost =  get_ostimes(uri)
    logger.info("Server started at: User: %.3f, Sys: %.3f" % (ost[0], ost[1]))

    if command == 'create-db':
        create_db(uri, options['database'], options['login'], options['pwd'])
    if command == 'drop-db':
        drop_db(uri, options['database'])
    if command == 'install-module' or (command == 'create-db' and lmodules):
        install_module(uri, options['database'], options['modules'], options['login'], options['pwd'])
    if command == 'upgrade-module':
        upgrade_module(uri, options['database'], options['modules'], options['login'], options['pwd'])
    if command == 'check-quality':
        check_quality(uri, options['login'], options['pwd'], options['database'], options['modules'], options['quality-logs'])
    if command == 'install-translation':
        import_translate(uri, options['login'], options['pwd'], options['database'], options['translate-in'])

    ost =  get_ostimes(uri, ost)
    logger.info("Server ending at: User: %.3f, Sys: %.3f" % (ost[0], ost[1]))

    server.stop()
    server.join()
    sys.exit(0)

except xmlrpclib.Fault, e:
    logger.exception('xmlrpc')
    server.stop()
    server.join()
    sys.exit(1)
except Exception, e:
    logger.exception('')
    server.stop()
    server.join()
    sys.exit(1)

logger.info('end of script')
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
