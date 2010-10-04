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
from openobject.buildstep import OpenObjectBzr, OpenObjectSVN, BzrMerge, BzrRevert, OpenERPTest, LintTest, BzrStatTest, BzrCommitStats, BzrTagFailure
from openobject.poller import BzrPoller
from openobject.status import web, mail, logs
import twisted.internet.task
import rpc
import os
import signal

from twisted.python import log, reflect
from twisted.python import components
from buildbot import util

logging.basicConfig(level=logging.DEBUG)

def str2bool(sstr):
    if sstr and sstr.lower() in ('true', 't', '1', 'on'):
        return True
    return False

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
        log.msg("Keeper config")
        self.bmconfig = bmconfig
        self.poll_interval = 560.0 #seconds
        self.in_reset = False
        self.bbot_tstamp = None
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
        self.loop = twisted.internet.task.LoopingCall(self.poll_config)
        
        self.loop.start(self.poll_interval)

    def poll_config(self):
        bbot_obj = rpc.RpcProxy('software_dev.buildbot')
        try:
            new_tstamp = bbot_obj.get_conf_timestamp([self.bbot_id,])
            # print "Got conf timestamp:", self.bbot_tstamp
        except Exception, e:
            print "Could not get timestamp: %s" % e
            return
        if new_tstamp != self.bbot_tstamp:
            try:
                print "Got new timestamp: %s, must reconfig" % new_tstamp
                
                # Zope makes it so difficult to locate the BuildMaster instance,
                # so...
                if self.bbot_tstamp is not None:
                    os.kill(os.getpid(), signal.SIGHUP)
                self.bbot_tstamp = new_tstamp
            except Exception:
                print "Could not reset"

    def reset(self):
        """ Reload the configuration
        """
        print "Keeper reset"
        if self.in_reset:
            return
        self.in_reset = True
        c = self.bmconfig
        c['slaves'] = []
        c['schedulers'] = []
        c['builders'] = []
        c['change_source']=[]
        
        c_mail = {}

        bbot_obj = rpc.RpcProxy('software_dev.buildbot')
        bbot_data = bbot_obj.read(self.bbot_id)
        if bbot_data['http_url']:
            c['buildbotURL'] = bbot_data['http_url']

        bbot_attr_obj = rpc.RpcProxy('software_dev.battr')
        bids = bbot_attr_obj.search([('bbot_id','=', self.bbot_id)])
        if bids:
            for attr in bbot_attr_obj.read(bids):
                if attr['name'].startswith('mail_'):
                    c_mail[attr['name']] = attr['value']
                else:
                    c[attr['name']] = attr['value']

        # Then, try to setup the slaves:
        bbot_slave_obj = rpc.RpcProxy('software_dev.bbslave')
        bsids = bbot_slave_obj.search([('bbot_id','=', self.bbot_id)])
        if bsids:
            for slav in bbot_slave_obj.read(bsids,['tech_code', 'password']):
                print "Adding slave: %s" % slav['tech_code']
                c['slaves'].append(BuildSlave(slav['tech_code'], slav['password'], max_builds=2))
        
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
                'BzrCommitStats': BzrCommitStats,
                'LintTest': LintTest,
                'BzrMerge': BzrMerge,
                'BzrTagFailure': BzrTagFailure,
                }

        for bld in builders:
            fact = factory.BuildFactory()
            props = bld.get('properties', {})
           
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
                'properties': props,
                'mergeRequests': False,
                'category': props.get('group', None),
            })

            cfilt = ChangeFilter_debug(branch=bld['branch_name'])
            # FIXME
            c['schedulers'].append(
                OpenObjectScheduler(name = "Scheduler for %s" %(bld['name']),
                                    builderNames = [bld['name'], ],
                                    change_filter=cfilt,
                                    treeStableTimer= bld.get('tstimer',None),
                                    properties={},
                                    keeper=self)
                                )

        if bbot_data['http_port']:
            print "We will have a http server at %s" % bbot_data['http_port']
            c['status'].append(web.OpenObjectWebStatus(http_port=bbot_data['http_port']))

        if c_mail.get('mail_smtp_host', False):
            mail_kwargs= {
                'projectURL': c['buildbotURL'],
                'extraRecipients'   : c_mail.get('mail_notify_cc', 'hmo@tinyerp.com').split(','),
                'html_body': str2bool(c_mail.get('mail_want_html','false')), # True value will send mail in HTML
                'smtpUser':  c_mail.get('mail_smtp_username',''),
                'smtpPassword':  c_mail.get('mail_smtp_passwd',''),
                'smtpPort': c_mail.get('mail_smtp_port', 2525),
                'subject': c_mail.get('mail_subject', '[%(projectName)s-buildbot] build of %(builder)s ended in %(result)s'),
                'fromaddr':  c_mail.get('mail_sender_email', '<noreply@openerp.com>'),
                'reply_to':  c_mail.get('mail_reply_to', 'support@tinyerp.com'),
                'relayhost': c_mail.get('mail_smtp_host'),
                'useTls':       str2bool(c_mail.get('mail_email_tls','t')),
                'mode':      c_mail.get('mail_notify_mode', 'failing'),
                                                # 'all':sends mail when step is either success/failure or had problem.
                                                # 'problem':sends mail when step had problem.
                                                # 'failing':sends mail when step fails.

                }
                
            c['status'].append(mail.OpenObjectMailNotifier( **mail_kwargs))

        # We should be ok by now..
        self.in_reset = False

    def __del__(self):
        log.msg("Here is where the keeper sleeps..")
        self.loop.stop()
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

if False:
    # TODO!!

    # locks.debuglog = log.msg
    db_lock = locks.MasterLock("database")
    cpu_lock = locks.SlaveLock("cpu")

#eof
