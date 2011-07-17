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
from openerp_libclient import rpc, subscriptions


class MasterPoller(service.MultiService):
    """ Poll the OpenERP database, reconfig and deliver async notifications
    """
    def __init__(self):
        service.MultiService.__init__(self)
        self.setName('master_poller')
        self._tasks = []
        self._hazError = False
        
    def startService(self):
        service.MultiService.startService(self)
        log.msg("Started")
        return reactor.callLater(10.0, self.restartPolling)
    
    def stopService(self):
        service.MultiService.stopService(self)
        self._stopTasks()

    def _stopTasks(self):
        for t in self._tasks:
            try:
                t.stop()
            except Exception:
                pass
        
        self._tasks = []

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
        self._stopTasks()
        if not self.running:
            return
        if not self.getMaster():
            return
        
        t = subscriptions.SubscriptionThread('software_dev.buildrequest:notify')
        t.setCallback(self._triggerMasterRequests)
        self._tasks.append(t)
        t.start()
        
        t = subscriptions.SubscriptionThread('software_dev.buildbot:all-reconfig')
        t.setCallback(self._triggerAllReconfig)
        self._tasks.append(t)
        t.start()
        
        t = subscriptions.SubscriptionThread('software_dev.buildbot:trigger-all-poll')
        t.setCallback(self._pollAllSources)
        self._tasks.append(t)
        t.start()
        return

    def _waitAndRestart(self, result, delay=10.0):
        return reactor.callLater(delay, self.restartPolling)

    def _triggerMasterRequests(self):
        master = self.getMaster()
        if not master:
            self._waitAndRestart(None)
            return
        
        if not self.running:
                return defer.suceed(True)
        d = master.pollDatabaseBuildRequests()
        return d
    
    def _triggerAllReconfig(self):
        master = self.getMaster()
        if not master:
            self._waitAndRestart(None)
            return
        
        if not self.running:
                return defer.suceed(True)
        d = master.loadTheConfigFile()
        return d

    def _pollAllSources(self, res=None):
        master = self.getMaster()
        if not master:
            self._waitAndRestart(None)
            return
        if not self.running:
            return defer.suceed(True)

        try:
            # The twisted.internet.task.LoopingCall holds the function and args
            # of the poll. It is not thread safe, we need to prevent parallel
            # running of the calls.
            # Its 'call' attribute is filled while waiting, cleared while
            # running the function.

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

#eof
