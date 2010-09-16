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

import logging
from buildbot.buildslave import BuildSlave
from buildbot.process import factory
from buildbot.schedulers.filter import ChangeFilter
from openobject.scheduler import OpenObjectScheduler, OpenObjectAnyBranchScheduler
from openobject.buildstep import OpenObjectBzr, OpenObjectSVN, BzrMerge, BzrRevert, OpenERPTest, LintTest, BzrStatTest
from openobject.poller import BzrPoller
from openobject.status import web, mail, logs
import rpc

from twisted.python import log, reflect
from buildbot import util

logging.basicConfig(level=logging.DEBUG)

class ChangeFilter_debug(ChangeFilter):
    def filter_change(self, change):
        print "Trying to filter %r with %r" % (change, self)
        return ChangeFilter.filter_change(self, change)

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
        c['db_url'] = 'openerp://' # it prevents the db_schema from going SQL
        c['slavePortnum'] = 'tcp:8999:interface=127.0.0.1'

        c['slaves'] = []

        c['schedulers'] = []
        c['builders'] = []
        c['change_source']=[]
        c['status'] = []
        
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
        c['slaves'] = []
        c['schedulers'] = []
        c['builders'] = []
        c['change_source']=[]

        bbot_obj = rpc.RpcProxy('software_dev.buildbot')
        bbot_data = bbot_obj.read(self.bbot_id)
        if bbot_data['http_url']:
            c['buildbotURL'] = bbot_data['http_url']

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
        polled_brs = bbot_obj.get_polled_branches([self.bbot_id])
        print "got polled brs:", polled_brs
        
        for pbr in polled_brs:
            pmode = pbr.get('mode','branch')
            if pmode == 'branch':
                # Maintain a branch 
                if pbr['rtype'] == 'bzr':
                    fetch_url = pbr['fetch_url']
                    
                    c['change_source'].append(BzrPoller(fetch_url,
                            branch_name=pbr.get('branch_name', None),
                            branch_id=pbr['branch_id'], keeper=self))
                else:
                    raise NotImplementedError("No support for %s repos yet" % pbr['rtype'])

        # Get the tests that have to be performed:
        builders = bbot_obj.get_builders([self.bbot_id])
        
        dic_steps = { 'OpenERP-Test': OpenERPTest,
                'OpenObjectBzr': OpenObjectBzr,
                'BzrRevert': BzrRevert,
                'BzrStatTest': BzrStatTest,
                'LintTest': LintTest,
                'BzrMerge': BzrMerge,
                }

        for bld in builders:
            fact = factory.BuildFactory()
           
            for bstep in bld['steps']:
                assert bstep[0] in dic_steps, "Unknown step %s" % bstep[0]
                kwargs = bstep[1].copy()
                # TODO manipulate some of them
                if 'locks' in kwargs:
                   pass # TODO
                if 'keeper' in kwargs:
                    kwargs['keeper'] = self

                print "Adding step %s(%r)" % (bstep[0], kwargs)
                klass = dic_steps[bstep[0]]
                fact.addStep(klass(**kwargs))
               
            c['builders'].append({
                'name' : bld['name'],
                'slavename' : bld['slavename'],
                'builddir': bld['builddir'],
                'factory': fact,
                'properties': bld.get('properties', {}),
            })

            cfilt = ChangeFilter_debug(branch=bld['branch_name'])
            # FIXME
            c['schedulers'].append(
                OpenObjectScheduler(name = "Scheduler for %s" %(bld['name']),
                                    builderNames = [bld['name'], ],
                                    change_filter=cfilt,
                                    treeStableTimer = bld['tstimer'],
                                    properties={},
                                    keeper=self)
                                )

        if bbot_data['http_port']:
            print "We will have a http server at %s" % bbot_data['http_port']
            c['status'].append(web.OpenObjectWebStatus(http_port=bbot_data['http_port']))

        # We should be ok by now..

    def __del__(self):
        print "Here is where the keeper sleeps.."
        try:
            rpc.session.logout()
        except Exception: pass


class DBSpec_OpenERP(object):
    """
    A specification for the database type and other connection parameters.
    """

    # List of connkw arguments that are applicable to the connection pool only
    pool_args = ["max_idle"]
    def __init__(self, dbapiName, *connargs, **connkw):
        # special-case 'sqlite3', replacing it with the available implementation
        self.dbapiName = dbapiName
        self.connargs = connargs
        self.connkw = connkw

    @classmethod
    def from_url(cls, url, basedir=None):
        return cls('OpenERP')

    def get_dbapi(self):
        """
        Get the dbapi module used for this connection (for things like
        exceptions and module-global attributes
        """
        return None  #reflect.namedModule(self.dbapiName)

    def get_sync_connection(self):
        """
        Get a synchronous connection to the specified database.  This returns
        a simple DBAPI connection object.
        """
        
        conn = False
        return conn

    def get_async_connection_pool(self):
        """
        Get an asynchronous (adbapi) connection pool for the specified
        database.
        """
        return False

    def get_maxidle(self):
        default = None
        return self.connkw.get("max_idle", default)
        
    def get_connector(self):
        import connector
        return connector.OERPConnector(self)
        
    def get_schemaManager(self, basedir):
        return False

from buildbot.db import dbspec

dbspec.cur_dbspec = DBSpec_OpenERP
print "Replaced dbspec!\n"


if False:
    # TODO!!

    # locks.debuglog = log.msg
    db_lock = locks.MasterLock("database")
    cpu_lock = locks.SlaveLock("cpu")

#eof
