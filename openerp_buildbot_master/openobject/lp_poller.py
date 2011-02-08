#!/usr/bin/python
# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2011 OpenERP SA (www.openerp.com)
#    Parts of this file are taken from the buildbot project, GPL2,
#    to which this code links anyway.
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

import os
import fnmatch
import datetime

from twisted.application import service
from twisted.internet import defer, task, reactor
from twisted.python import log

from buildbot import util

import rpc

from launchpadlib.launchpad import Launchpad

cachedir = os.path.expanduser("~/.launchpadlib/cache/")

if os.path.isdir(cachedir) and not os.path.exists(os.path.join(cachedir, 'CACHEDIR.TAG')):
    fd = open(os.path.join(cachedir, 'CACHEDIR.TAG'), 'wb')
    fd.write('Signature: 8a477f597d28d172789f06886806bc55\n# Cache of LauncpadLib')
    fd.close()

class MS_Scanner(service.Service, util.ComparableMixin):
    """
    Class that scans MS site for changes in our branches.
    """

    pollInterval = 2520
    "time (in seconds) between calls to C{poll}"

    _loop = None
    _lp = None

    def describe(self):
        pass

    def scan(self):
        global cachedir
        if not self._lp:
            self._lp = Launchpad.login_anonymously('buildbot spider', 'production', cachedir)
        
        bseries_obj = rpc.RpcProxy('software_dev.buildseries')
        tmpl_ids = bseries_obj.search([('is_template','=', True)])
        if not tmpl_ids:
            log.msg('No template branches found to scan with')
            return
        
        templates = bseries_obj.read(tmpl_ids, ['name', 'target_path', 'branch_url', 'builder_id'])
        
        projects = set()
        # here start the assumptions:
        for t in templates:
            if t['target_path'] == 'server':
                projects.add('openobject-server')
            elif t['target_path'] in ('addons', 'extra_addons'):
                projects.add('openobject-addons')
            # and nothing else
        min_tstamp = datetime.datetime.now() - datetime.timedelta(days=30)
        
        for projname in projects:
            project = self._lp.projects[projname]
            assert project, projname
            log.msg('Scanning branches in %s' % project.name)
            for br in project.getBranches(modified_since=min_tstamp, \
                    status=('Experimental', 'Development', 'Mature')):
                if br.private:
                    continue
                for tmpl in templates:
                    if fnmatch.fnmatch(br.bzr_identity, tmpl['branch_url']):
                        log.msg('Matched branch %s against template #%d' % (br.bzr_identity, tmpl['id']))
                        old_ids = bseries_obj.search([('branch_url','=', br.bzr_identity), 
                                            ('builder_id', '=', tmpl['builder_id'][0])])
                        if old_ids:
                            log.msg('Branch already there with id %r, continuing' % old_ids)
                            break # we shall not match against rest of templates
                        
                        namedict = {'name': br.name, 'lp': br.bzr_identity, 'unique_name': br.unique_name }
                        defaults = { 'is_template': False, 'branch_url': br.bzr_identity,
                                    'name': tmpl['name'] % namedict 
                                   }
                        nbranch = bseries_obj.copy(tmpl['id'], defaults)
                        log.msg('Registered new branch %s at #%d' % (defaults['name'], nbranch))
                        break

    def startService(self):
        service.Service.startService(self)
        def do_poll():
            d = defer.maybeDeferred(self.scan)
            d.addErrback(log.err, 'while scanning Launchpad')
            return d

        # delay starting the loop until the reactor is running
        def start_loop():
            self._loop = task.LoopingCall(do_poll)
            self._loop.start(self.pollInterval)
        reactor.callWhenRunning(start_loop)

    def stopService(self):
        if self._loop:
            self._loop.stop()
        return service.Service.stopService(self)

#eof
