# -*- encoding: utf-8 -*-

""" This is where all the configuration of the buildbot takes place

    The master keeper is one object, that is attached to the buildbot
    configuration and also connected to the database. Upon start, it
    reads the db for the configuration, and sets the buildbot 
    accordingly.
    But, eventually, the master keeper should also poll the OpenERP
    db for changes (eg. new branches etc.) and reconfigure the bbot
    on the fly, without any reload or so.
"""

import rpc
import logging
from buildbot.buildslave import BuildSlave

logging.basicConfig(level=logging.DEBUG)

class Keeper(object):
    
    def __init__(self, db_props, bmconfig):
        """
            @param db_props a dict with info how to connect to db
            @param c the BuildmasterConfig dict
        """
        print "Keeper config"
        self.bmconfig = bmconfig
        c = bmconfig
        # some necessary definitions in the dict:
        c['projectName'] = "OpenERP-Test"
        c['buildbotURL'] = "http://test.openobject.com/"

        c['slaves'] = []
        c['slavePortnum'] = 'tcp:8999:interface=127.0.0.1'

        c['schedulers'] = []
        c['builders'] = []
        c['change_source']=[]
        
        r = rpc.session.login(db_props)
        if r != 0:
            raise Exception("Could not login!")
        
        bbot_obj = rpc.RpcProxy('software_dev.buildbot')
        bbot_id = bbot_obj.search([('tech_code','=',db_props.get('code','buildbot'))])
        assert bbot_id, "No buildbot for %r exists!" % db_props.get('code','buildbot')
        self.bbot_id = bbot_id[0]
        
    def reset(self):
        """ Reload the configuration
        """
        print "Keeper reset"
        c = self.bmconfig
        bbot_attr_obj = rpc.RpcProxy('software_dev.battr')
        bids = bbot_attr_obj.search([('bbot_id','=', self.bbot_id)])
        if bids:
            for attr in bbot_attr_obj.read(bids):
                c[attr['name']] = attr['value']
        # Then, try to setup the slaves:
        bbot_slave_obj = rpc.RpcProxy('software_dev.bbslave')
        bsids = bbot_slave_obj.search([('bbot_id','=', self.bbot_id)])
        if bsids:
            for slav in bbot_slave_obj.read(bsids,['tech_code', 'password']):
                print "Adding slave: %s" % slav['tech_code']
                c['slaves'].append(BuildSlave(slav['tech_code'], slav['password']))
        
        # Get the repositories we have to poll and maintain
        bbot_obj = rpc.RpcProxy('software_dev.buildbot')
        polled_brs = bbot_obj.get_polled_branches([self.bbot_id])
        print "got polled brs:", polled_brs
        
        # We should be ok by now..

    def __del__(self):
        print "Here is where the keeper sleeps.."
        try:
            rpc.session.logout()
        except Exception: pass


if False:
    # --- Do not edit past this
    openerp = buildbot_xmlrpc(host=properties['openerp_host'], port=properties['openerp_port'], dbname=properties['openerp_dbname'])
    openerp_uid = openerp.execute('common','login',  openerp.dbname, properties['openerp_userid'], properties['openerp_userpwd'])
    if not openerp_uid:
        raise RuntimeError("Cannot login to db, check %s@%s credentials!" % \
                (properties['openerp_userid'], properties['openerp_dbname']))
    testing_branches_ids = openerp.execute('object', 'execute', openerp.dbname, openerp_uid, properties['openerp_userpwd'], 'buildbot.lp.branch','search',[('is_test_branch','=',False), ('is_root_branch','=',False)])
    if not testing_branches_ids:
        log.msg("No branches were detected at the db!")
    testing_branches = openerp.execute('object', 'execute', openerp.dbname, openerp_uid, properties['openerp_userpwd'], 'buildbot.lp.branch','read',testing_branches_ids)

    # TODO!!

    # locks.debuglog = log.msg
    db_lock = locks.MasterLock("database")
    cpu_lock = locks.SlaveLock("cpu")

#eof
