# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution    
#    Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>). All Rights Reserved
#    $Id$
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import xmlrpclib
import optparse
import sys
import threading
import os
import time
import socket

admin_passwd = 'admin'
waittime = 10
wait_count = 0
wait_limit = 12

def start_server(root_path, port):
    if root_path:
        root_path += '/'
    os.system('python2.5 '+root_path+'/bin/tinyerp-server.py --pidfile=tinyerp.pid --port=%s --no-netrpc' %(str(port)))
def clean():
    if os.path.isfile('tinyerp.pid'):
        ps = open('tinyerp.pid') 
        if ps:
            pid = int(ps.read())
            ps.close()  
            if pid:    
                os.kill(pid,9)

def execute(connector, method, *args):
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

def login(uri, dbname, user, pwd):
    conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/common')
    uid = execute(conn,'login',dbname, user, pwd) 
    return uid

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
    if dbname not in db_list:
        id = execute(conn,'create',admin_passwd, dbname, True, lang)
        wait(id,uri)
    uid = login_conn.login(dbname, user, pwd) 
    db_list = execute(conn, 'list') 
    wiz_id = execute(wiz_conn,'create', dbname, uid, user, 'base_setup.base_setup')
    state = 'init'
    datas = {'form':{}}

    while state!='menu':   
        res = execute(wiz_conn, 'execute', dbname, uid, pwd, wiz_id, datas, state, {})
        if state=='init':
            datas['form'].update( res['datas'] )
        if res['type']=='form':
            for field in res['fields'].keys():               
                #datas['form'][field] = datas['form'].get(field,False)
                datas['form'][field] = res['fields'][field].get('value', False)
            state = res['state'][-1][0]
            datas['form'].update({
                'profile': -1                
            })
        elif res['type']=='state':
            state = res['state']
    res = execute(wiz_conn, 'execute', dbname, uid, pwd, wiz_id, datas, state, {})
    return True

def install_module(uri, dbname, modules, user='admin', pwd='admin'):
    uid = login(uri, dbname, user, pwd)
    if uid: 
        obj_conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/object')
        wizard_conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/wizard')
        module_ids = execute(obj_conn, 'execute', dbname, uid, pwd, 'ir.module.module', 'search', [('name','in',modules)])  
        execute(obj_conn, 'execute', dbname, uid, pwd, 'ir.module.module', 'button_install', module_ids)           
        wiz_id = execute(wizard_conn, 'create', dbname, uid, pwd, 'base_setup.base_setup')
        state = 'init'
        datas = {}
        #while state!='menu':
        while state!='finish':                
            res = execute(wizard_conn, 'execute', dbname, uid, pwd, wiz_id, datas, state, {})                
            if state == 'init':
                state = 'update'
            elif state == 'update':
                state = 'finish'                                  
    return True

usage = """%prog command [options]

Basic Commands:
    create-db            Create new database
    install-module       Install module 
"""
parser = optparse.OptionParser(usage)            
parser.add_option("--modules", dest="modules",
                     help="specify modules to install or check quality")
parser.add_option("--root-path", dest="root_path", help="specify the root path")
parser.add_option("-p", "--port", dest="port", help="specify the TCP port", type="int")
parser.add_option("-d", "--database", dest="db_name", help="specify the database name")  
parser.add_option("--login", dest="login", help="specify the User Login") 
parser.add_option("--password", dest="pwd", help="specify the User Password")  

(opt, args) = parser.parse_args()
if len(args) != 1:
    parser.error("incorrect number of arguments")
command = args[0]
if command not in ('create-db','install-module'):
    parser.error("incorrect command")    

def die(cond, msg):
    if cond:
        print msg
        sys.exit(1)

die(opt.modules and (not opt.db_name),
        "the modules option cannot be used without the database (-d) option")

options = {    
    'root-path' : opt.root_path or 'bin/',
    'port' : opt.port or 8359, 
    'database': opt.db_name or 'terp',
    'modules' : opt.modules or [],
    'login' : opt.login or 'admin',
    'pwd' : opt.pwd or 'admin',
}

options['modules'] = opt.modules and map(lambda m: m.strip(), opt.modules.split(',')) or []
uri = 'http://localhost:' + str(options['port'])

server_thread = threading.Thread(target=start_server,
                args=(options['root-path'], options['port']))
try:    
    server_thread.start() 
    if command == 'create-db':
        create_db(uri, options['database'], options['login'], options['pwd'])
    if command == 'install-module': 
        install_module(uri, options['database'], options['modules'], options['login'], options['pwd'])
    clean()
    sys.exit(0)
    
except xmlrpclib.Fault, e:
    print e.faultString
    clean()
    sys.exit(1)
except Exception, e:
    print e
    clean()
    sys.exit(1)
