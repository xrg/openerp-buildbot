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
from launchpadlib.credentials import Credentials, UnencryptedFileCredentialStore, RequestTokenAuthorizationEngine
from lazr.restfulclient.errors import HTTPError

class MS_Service(service.Service, util.ComparableMixin):
    """Provide others with authenticated Launchpad connections
    
        Will take care of authentication tokens, etc.
    """
    auth_poll_interval = 60 # seconds
    _credentials = None

    _cachedir = os.path.expanduser("~/.launchpadlib/cache/")
    _creds_file = os.path.expanduser("~/.launchpadlib/buildbot-creds")
    _try_auth_loop = None
    _lp_server = 'staging'
    _app_name = 'test.openobject.com'
    _afac = None
    __instance = None

    def describe(self):
        pass

    def _open_auth(self):
        """ Load existing credentials or request new ones
        """
        self._cstore = UnencryptedFileCredentialStore(self._creds_file)
        
        assert not self._credentials
        self._credentials = self._cstore.load(self._afac.unique_consumer_id)
        if self._credentials:
            return

        def _poll_req_auth_2():
            d = defer.maybeDeferred(self._poll_request_auth)
            d.addErrback(log.err, 'while waiting Launchpad Authorization')
            return d

        self._credentials = Credentials(self._app_name)
        request_token_info = self._credentials.get_request_token(web_root=self._lp_server)

        self._try_auth_loop = task.LoopingCall(_poll_req_auth_2)
        log.msg("LP: Please go to %s and authorize me!" % request_token_info)
        self._try_auth_loop.start(self.auth_poll_interval)

    def _poll_request_auth(self):
        log.msg("LP: Still waiting auth for: %s" % self._credentials._request_token)
    
        try:
            self._credentials.exchange_request_token_for_access_token( web_root=self._lp_server)
            log.msg("LP: I have authentication!")
            
            self._cstore.save(self._credentials, self._afac.unique_consumer_id)

            self._try_auth_loop.stop()
            self._try_auth_loop = None
        except HTTPError:
            # The user hasn't authorized the token yet.
            return

    def startService(self):
        service.Service.startService(self)

        if os.path.isdir(self._cachedir) and not os.path.exists(os.path.join(self._cachedir, 'CACHEDIR.TAG')):
            fd = open(os.path.join(self._cachedir, 'CACHEDIR.TAG'), 'wb')
            fd.write('Signature: 8a477f597d28d172789f06886806bc55\n# Cache of LauncpadLib')
            fd.close()

        self._afac = RequestTokenAuthorizationEngine(self._lp_server, self._app_name)
        reactor.callWhenRunning(self._open_auth)

    def stopService(self):
        if self._try_auth_loop:
            self._try_auth_loop.stop()
        return service.Service.stopService(self)

    def get_Launchpad(self):
        if not self._credentials.access_token:
            log.err('Launchpad authentication is not ready yet!')
            raise RuntimeError("Please authenticate first! See logs for token.")
        return Launchpad(credentials=self._credentials, credential_store=self._cstore,
                authorization_engine=self._afac, service_root=self._lp_server,
                cache=self._cachedir)
    
    @classmethod
    def startInstance(cls):
        cls.__instance = cls()
        cls.__instance.startService()

    @classmethod
    def stopInstance(cls):
        if cls.__instance:
            cls.__instance.stopService()
            cls.__instance = None

    @classmethod
    def get_LP(cls):
        return cls.__instance.get_Launchpad()

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
        if self._lp is None:
            self._lp = MS_Service.get_LP()
        
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
                                    'name': tmpl['name'] % namedict,
                                   }
                        if br.description:
                            defaults['description'] = br.description,
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
        del self._lp
        return service.Service.stopService(self)

#eof
