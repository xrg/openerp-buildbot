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
from scheduler import ChangeFilter_OE
from buildbot.schedulers import basic, timed, dependent
from buildbot import manhole
from .status import web, mail, logs
import twisted.internet.task
from openerp_libclient import rpc
import os
import signal

from twisted.python import log

logging.basicConfig(level=logging.DEBUG)

from . import buildsteps
from . import repohandlers

def str2bool(sstr):
    if sstr and sstr.lower() in ('true', 't', '1', 'on'):
        return True
    return False

class Keeper(object):
    """ Keeper is the connector that gets/updates buildbot configuration from openerp
    """
    logger = logging.getLogger('master_keeper')

    def __init__(self, db_props, bmconfig):
        """
            @param db_props a dict with info how to connect to db
            @param c the BuildmasterConfig dict
        """
        self.logger.info("Initialize")
        self.bmconfig = bmconfig
        self.poll_interval = 560.0 #seconds
        self.in_reset = False
        self.bbot_tstamp = None
        self.loop = None # define early, so that del() always sees it
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
        
        rpc.openSession(**db_props)
        r = rpc.login()
        if not r:
            self.logger.error("Cannot login to OpenERP")
            raise Exception("Could not login!")
        
        bbot_obj = rpc.RpcProxy('software_dev.buildbot')
        bbot_id = bbot_obj.search([('tech_code','=',db_props.get('code','buildbot'))])
        assert bbot_id, "No buildbot for %r exists!" % db_props.get('code','buildbot')
        self.bbot_id = bbot_id[0]
        self.loop = twisted.internet.task.LoopingCall(self.poll_config)
        from twisted.internet import reactor
        reactor.suggestThreadPoolSize(30)

        self.loop.start(self.poll_interval)
        os.umask(int('0027',8)) # re-enable group read bit

    def poll_config(self):
        bbot_obj = rpc.RpcProxy('software_dev.buildbot')
        try:
            new_tstamp = bbot_obj.get_conf_timestamp([self.bbot_id,])
            # print "Got conf timestamp:", self.bbot_tstamp
        except Exception, e:
            self.logger.exception("Could not get timestamp: %s", e)
            return
        if new_tstamp != self.bbot_tstamp:
            try:
                self.logger.info("Got new timestamp: %s, must reconfig", new_tstamp)
                
                # Zope makes it so difficult to locate the BuildMaster instance,
                # so...
                if self.bbot_tstamp is not None:
                    # Since this will spawn a new Keeper object, we have to stop the
                    # previous one:
                    self.loop.stop()
                    self.loop = None
                    os.kill(os.getpid(), signal.SIGHUP)
                self.bbot_tstamp = new_tstamp
            except Exception:
                self.logger.exception("Could not reset")

    def reset(self):
        """ Reload the configuration
        """
        self.logger.info("Keeper reset")
        if self.in_reset:
            return
        self.in_reset = True
        c = self.bmconfig
        c['slaves'] = []
        c['schedulers'] = []
        c['builders'] = []
        c['change_source']=[]
        
        c_mail = {}
        slave_proxy_url = None
        bzr_local_run = None
        tmpconf = { 'proxied_bzrs': {}, # map the remote branches to local ones.
            'poller_kwargs': {},
            }

        bbot_obj = rpc.RpcProxy('software_dev.buildbot')
        bbot_data = bbot_obj.read(self.bbot_id)
        if bbot_data['http_url']:
            c['buildbotURL'] = bbot_data['http_url']

        bbot_attr_obj = rpc.RpcProxy('software_dev.battr')
        if True:
            for attr in bbot_attr_obj.search_read([('bbot_id','=', self.bbot_id)]):
                if attr['name'].startswith('mail_'):
                    c_mail[attr['name']] = attr['value']
                elif attr['name'] == 'proxy_location':
                    tmpconf['poller_kwargs'][attr['name']] = attr['value']
                elif attr['name'] == 'slave_proxy_url':
                    slave_proxy_url = attr['value']
                elif attr['name'] == 'bzr_local_run':
                    bzr_local_run = True
                elif attr['name'] == 'manhole':
                    try:
                        mtype, margs = attr['value'].split('|', 1)
                        margs = margs.split('|')
                        klass = getattr(manhole, mtype + 'Manhole')
                        c['manhole'] = klass(*margs)
                    except Exception:
                        self.logger.exception("Cannot configure manhole:")
                else:
                    c[attr['name']] = attr['value']

        # Then, try to setup the slaves:
        bbot_slave_obj = rpc.RpcProxy('software_dev.bbslave')
        # TODO: max_builds
        for slav in bbot_slave_obj.search_read([('bbot_id','=', self.bbot_id)], fields=['tech_code', 'password']):
            self.logger.info("Adding slave: %s", slav['tech_code'])
            c['slaves'].append(BuildSlave(slav['tech_code'], slav['password'], max_builds=slav.get('max_builds',2)))
        
        # Get the repositories we have to poll and maintain
        polled_brs = bbot_obj.get_polled_branches([self.bbot_id])
        self.logger.info("Got %d polled branches", len(polled_brs))
        
        for pbr in polled_brs:
            if pbr['rtype'] in repohandlers.repo_types:
                repohandlers.repo_types[pbr['rtype']].createPoller(pbr, c, tmpconf)
            else:
                raise NotImplementedError("No support for %s repos yet" % pbr['rtype'])

        dic_steps = {}
        
        for bs in buildsteps.exported_buildsteps:
            if getattr(bs, 'step_name', None):
                dic_steps[bs.step_name] = bs
            else:
                # by default, the class name
                dic_steps[bs.__name__] = bs
        
        self.logger.debug("Available steps: %r", dic_steps.keys())

        # Get the tests that have to be performed:
        builders = bbot_obj.get_builders([self.bbot_id])
        
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

                
                klass = dic_steps[bstep[0]]
                if bstep[0] in ('OpenObjectBzr') and kwargs['repourl'] in tmpconf['proxied_bzrs']:
                    kwargs['proxy_url'] = tmpconf['proxied_bzrs'][kwargs['repourl']]
                self.logger.debug("Adding step %s(%r)", bstep[0], kwargs)
                if bstep[0] in ('BzrPerformMerge', 'BzrSyncUp'):
                    # Pass all of them to buildstep, so that it can resolve
                    # all the changes it will be receiving.
                    kwargs['proxied_bzrs'] = tmpconf['proxied_bzrs']
                    # FIXME: remove this
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

            cfilt = ChangeFilter_OE(branch_id=bld['branch_id'])
            # FIXME
            
            sched = None
            sched_kwargs = dict(name = "Scheduler %s" % bld['name'],
                    builderNames = [bld['name'],],
                    properties=bld.get('sched_props',{}))
        
            if bld['scheduler'] == 'periodic':
                sched = timed.Periodic( periodicBuildTimer = bld.get('tstimer',None),
                                    **sched_kwargs)
            elif bld['scheduler'] == 'nightly':
                sched = timed.Nightly(branch=bld['branch_name'], change_filter=cfilt,
                                    minute=bld.get('sched_minute',0), hour=bld.get('sched_hour','*'),
                                    dayOfMonth=bld.get('sched_dayOfMonth', '*'),
                                    dayOfWeek=bld.get('sched_dayOfWeek','*'),
                                    onlyIfChanged=bld.get('sched_ifchanged',False),
                                    **sched_kwargs)

            elif bld['scheduler'] == 'dependent':
                sched = None
                for sch in c['schedulers']:
                    if sch.name == 'Scheduler %s' % bld.get('sched_upstream', ':('):
                        sched = dependent.Dependent(upstream=sch, **sched_kwargs)
                        break
            else:
                sched = basic.SingleBranchScheduler(change_filter=cfilt,
                                    treeStableTimer= bld.get('tstimer',None),
                                    **sched_kwargs)

            c['schedulers'].append(sched)

        if bbot_data['http_port']:
            self.logger.info("We will have a http server at %s", bbot_data['http_port'])
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
        # we do reset some "heavy" members, to ensure dereferencing
        # objects that might hold circular references to us
        if self.loop:
            self.loop.stop()
            self.loop = None
        try:
            import lp_poller
            lp_poller.MS_Service.stopInstance()
        except Exception: pass
        
        try:
            rpc.session.logout()
        except Exception: pass
        self.bmconfig = None
        

from buildbot.db import connector as bbot_connector
import connector

bbot_connector.db_connector = connector.OERPConnector

#eof
