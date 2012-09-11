# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2011 P. Christeas <xrg@hellug.gr>
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

#.apidoc title: Master Poller service

""" Poller for master reconfiguration

    This *must be* included/instanciated in buildbot.tac
"""
from twisted.application import service
from buildbot.master import BuildMaster
from twisted.internet import defer, reactor
from twisted.python import log
from openerp_libclient import agent_commands, rpc
from twisted.internet.threads import blockingCallFromThread
from twisted.internet.task import LoopingCall

from functools import wraps

def call_with_master(func):
    """ Decorator to find and add 'master' argument to a function, consume deferreds
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        master = self.getMaster()
        if not master:
            self._waitAndRestart(None)
            raise agent_commands.CommandFailureException('Error!', 'Buildbot master is not active')
        
        if not self.running:
            raise agent_commands.CommandFailureException('Error!', 'Buildbot poller is not active')
        
        res = blockingCallFromThread(reactor, func, self, master, *args, **kwargs)
        return res
    return wrapper

class MasterPoller(service.MultiService):
    """ Poll the OpenERP database, reconfig and deliver async notifications
    """
    def __init__(self):
        service.MultiService.__init__(self)
        self.setName('master_poller')
        self._command_thread = None
        self._rpc_thread = None
        
    def startService(self):
        service.MultiService.startService(self)
        log.msg("Started MasterPoller")
        return reactor.callLater(7.0, self.restartPolling)
    
    def stopService(self):
        service.MultiService.stopService(self)
        if self._command_thread:
            self._command_thread.stop()
            self._command_thread = None
        if self._rpc_thread:
            self._rpc_thread.stop()
            self._rpc_thread = None

    def getMaster(self):
        """ Discover the BotMaster instance
        
            can fail, returning None
        """
        master = self.parent.getServiceNamed('buildmaster')
        assert isinstance(master, BuildMaster), master
        
        if not master.running:
            return None
        return master

    def restartPolling(self, result=None):
        if self._command_thread:
            self._command_thread.stop()
            self._command_thread = None
        if self._rpc_thread:
            self._rpc_thread.stop()
            self._rpc_thread = None
        if not self.running:
            return
        master = self.getMaster()
        if not master:
            return

        address = "software_dev.buildbot:%s" % master.properties['bbot_id']
        self._command_thread = agent_commands.CommandsThread(self, address,
                    agent_name=master.master_name, agent_incarnation=master.master_incarnation)

        self._command_thread.start()
        if rpc.default_session:
            self._rpc_thread = LoopingCall(rpc.default_session.loop_once)
            self._rpc_thread.start(rpc.default_session.conn_expire/2.0, now=False)
        log.msg('Restart MasterPoller command thread')
        return

    def _waitAndRestart(self, result, delay=10.0):
        return reactor.callLater(delay, self.restartPolling)

    @call_with_master
    def triggerMasterRequests(self, master):
        d = master.pollDatabaseBuildRequests()
        return d
    
    @call_with_master
    def triggerAllReconfig(self, master):
        d = master.loadTheConfigFile()
        return d

    @call_with_master
    def pollSources(self, master, sources):
        """ Poll selected repositories (by url)

            @param sources list of repo-urls to match existing changesources
        """
        assert isinstance(sources, list)
        try:
            deds = []
            for csource in master.change_svc:
                repourl = getattr(csource, 'repourl', None)
                if not repourl:
                    continue
                if not repourl in sources:
                    continue
                if not csource._loop:
                    continue
                cl = csource._loop
                if not (cl.running and cl.call):
                    csource.startService()

                d = defer.maybeDeferred(cl.f, *cl.a, **cl.kw)
                d.addCallback(lambda result: cl._reschedule())

            d = defer.gatherResults(deds)
            return d
        except Exception, e:
            log.err('Cannot trigger polls: %s' % e)

    @call_with_master
    def pollAllSources(self, master, res=None):
        try:
            # The twisted.internet.task.LoopingCall holds the function and args
            # of the poll. It is not thread safe, we need to prevent parallel
            # running of the calls.
            # Its 'call' attribute is filled while waiting, cleared while
            # running the function.

            # TODO: specify per change source, narrow down
            deds = []
            for csource in master.change_svc:
                if not csource._loop:
                    continue
                cl = csource._loop
                if not (cl.running and cl.call):
                    continue

                d = defer.maybeDeferred(cl.f, *cl.a, **cl.kw)
                d.addCallback(lambda result: cl._reschedule())

            d = defer.gatherResults(deds)
            return d
        except Exception, e:
            log.err('Cannot trigger polls: %s' % e)

    @call_with_master
    def rescan_commits(self, master, repourl, commits, branch_id, branch='other', standalone=True):
        """ Request a Poller to retrieve a set of arbitrary commits

            @param repourl the key to select the right poller
            @param commits a list of commit hashes
            @param branch_id the id of the branch to register found commits against
                Usually the "::rest" branch of that repository
            @param branch the branch name, as given to parent Change() class
            @param standalone do the hashes only, not their history
        """

        try:
            # The twisted.internet.task.LoopingCall holds the function and args
            # of the poll. It is not thread safe, we need to prevent parallel
            # running of the calls.
            # Its 'call' attribute is filled while waiting, cleared while
            # running the function.

            for csource in master.change_svc:
                if csource.repourl != repourl:
                    continue

                # assume the poller does have the function
                d = csource.rescan_commits(branch=branch,
                        commSpecs=[(c, {'branch_id': branch_id}) for c in commits],
                        standalone=standalone)
                return d # break the loop

            raise agent_commands.CommandFailureException('Warning!', \
                    'No changesource like "%s" available to rescan commits!' % repourl)
        except Exception, e:
            log.err('Cannot rescan commits: %s' % e)

    @call_with_master
    def ping(self, master, request=False, email=False):
        """ Respond with all possible ways, test async connectivity

            @param request Send a res.request
            @param email try to send an email TODO
        """

        log.msg(None, 'pong')

        if request:
            master.db.sendMessage('pong', 'Pong to poller request', priority=0)
        return 'pong'

#eof
