#!/usr/bin/python
# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2011 OpenERP SA (www.openerp.com)
#    Copyright (C) 2011, written by P. Christeas <xrg@hellug.gr>
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
from time import sleep
import logging
import optparse

from openerp_libclient import rpc
from openerp_libclient.extra import options
from openerp_libclient.extra.loopthread import LoopThread

from launchpadlib.launchpad import Launchpad
from launchpadlib.credentials import Credentials, UnencryptedFileCredentialStore, RequestTokenAuthorizationEngine
from lazr.restfulclient.errors import HTTPError


class MS_Service(object):
    """Provide others with authenticated Launchpad connections
    
        Will take care of authentication tokens, etc.
    """
    auth_poll_interval = 60 # seconds
    _credentials = None

    _cachedir = os.path.expanduser("~/.launchpadlib/cache/")
    _creds_file = os.path.expanduser("~/.launchpadlib/buildbot-creds")
    _try_auth_loop = None
    _lp_server = 'production'
    _app_name = 'test.openerp.hellug.gr'
    _afac = None

    def __init__(self):
        self._logger = logging.getLogger('lp-service')
        self.user_id = None

    def _open_auth(self):
        """ Load existing credentials or request new ones
        """
        self._cstore = UnencryptedFileCredentialStore(self._creds_file)
        
        assert not self._credentials
        self._credentials = self._cstore.load(self._afac.unique_consumer_id)
        if self._credentials:
            return

        self._credentials = Credentials(self._app_name)
        try:
            request_token_info = self._credentials.get_request_token(web_root=self._lp_server)
        except Exception, e:
            self._logger.error("Cannot get authentication token, will not connect to LP at all: %s", e)
            return

        self._try_auth_loop = LoopThread(self.auth_poll_interval, target=self._poll_request_auth)
        
        # Send a request to the user!
        self._logger.info("LP: Please go to %s and authorize me!", request_token_info)
        self.sendMessage("Authorization required for LP",
                "LP: Please go to %s and authorize me!",
                args=(request_token_info,))
        self._try_auth_loop.start()

    def _poll_request_auth(self):
        self._logger.info("LP: Still waiting auth for: %s", self._credentials._request_token)
    
        try:
            self._credentials.exchange_request_token_for_access_token( web_root=self._lp_server)
            self._logger.info("LP: I have authentication!")
            
            self._cstore.save(self._credentials, self._afac.unique_consumer_id)

            self._try_auth_loop.stop()
            self._try_auth_loop = None
        except HTTPError:
            # The user hasn't authorized the token yet.
            return

    def startService(self):

        if os.path.isdir(self._cachedir) and not os.path.exists(os.path.join(self._cachedir, 'CACHEDIR.TAG')):
            fd = open(os.path.join(self._cachedir, 'CACHEDIR.TAG'), 'wb')
            fd.write('Signature: 8a477f597d28d172789f06886806bc55\n# Cache of LauncpadLib')
            fd.close()

        self._afac = RequestTokenAuthorizationEngine(self._lp_server, self._app_name)
        self._open_auth()
        if self._try_auth_loop:
            self._try_auth_loop.join()

    def stopService(self):
        if self._try_auth_loop:
            self._try_auth_loop.stop()
            self._try_auth_loop.join()

    def get_Launchpad(self):
        if not self._credentials.access_token:
            self._logger.error('Launchpad authentication is not ready yet!')
            raise RuntimeError("Please authenticate first! See logs for token.")
        return Launchpad(credentials=self._credentials, credential_store=self._cstore,
                authorization_engine=self._afac, service_root=self._lp_server,
                cache=self._cachedir)

    def sendMessage(self, title, message, args=None, priority=1):
        """ Send a notification to the administrator

            This may use the db to send a special request, so that the
            admin doesn't have to read the logs

            @param title The message title
            @param message the message body (text)
            @param args may replace delimiters (%s) in message
            @param priority 0=Low, 1=Normal, 2=High, just like res.request

        """
        final_message = message
        if args and '%' in message:
            final_message = message % args

        if self.user_id:
            try:
                request_obj = rpc.RpcProxy('res.request')
                
                req_id = request_obj.create({'act_to': self.user_id,
                        'name': title, 'body': final_message, 'priority': str(priority)})
                assert req_id
                request_obj.request_send([req_id])
            except Exception, e:
                self._logger.exception('Cannot send request')

class MS_BranchScanner(LoopThread):
    """
    Class that scans MS site for changes in our branches.
    """

    _loop = None
    _lp = None
    pass_count = 0

    def __init__(self, service, period=1800):
        assert isinstance(service, MS_Service)
        LoopThread.__init__(self, period=1800)
        self._logger = logging.getLogger('lp-scanner')
        self.service = service
        self.days_recent = 30
        self.days_old = 90
    
    def loop_once(self):
        global cachedir
        if self._lp is None:
            self._lp = self.service.get_Launchpad()
        
        branch_obj = rpc.RpcProxy('software_dev.branch')
        btmpl_obj = rpc.RpcProxy('software_dev.branch.template')
        repo_obj = rpc.RpcProxy('software_dev.repo')
        
        templates = btmpl_obj.search_read([('repo_id.host_id.host_family','=', 'lp')])
        if not templates:
            self._logger.warning('No template branches found to scan with')
            return

        proj_id_map = {}
        
        projects = set()
        
        for tmpl in templates:
            if tmpl['repo_id'][0] not in proj_id_map:
                res = repo_obj.read(tmpl['repo_id'][0], ['base_url'])
                if not res:
                    raise RuntimeError("Cannot find base_url of repo #%d" % tmpl['repo_id'][0])
                proj_id_map[tmpl['repo_id'][0]] = res['base_url']
            
            tmpl['project'] = str(proj_id_map[tmpl['repo_id'][0]])
            
            if tmpl['sub_url'].startswith('~'):
                tmpl['pattern'] = 'lp:' + tmpl['sub_url']
            elif '@' in tmpl['sub_url']:
                luser, lurl = tmpl['sub_url'].split('@', 1)
                tmpl['pattern'] = 'lp:~%s/%s/%s'% (luser, tmpl['project'], lurl)
            else:
                tmpl['pattern'] = 'lp:' + tmpl['project'] + '/'+ tmpl['sub_url']
            
            tmpl['pattern'] = str(tmpl['pattern'])
            projects.add(tmpl['project'])

        min_tstamp = datetime.datetime.now() - datetime.timedelta(days=self.days_recent)
        # old_tstamp = datetime.datetime.now() - datetime.timedelta(days=self.days_old)
        
        get_kwargs = {}
        if (self.pass_count % 20) == 0:
            old_mode = True
            get_kwargs['status'] = ['Experimental', 'Development', 'Mature', 'Merged', 'Abandoned']
        else:
            old_mode = False
            get_kwargs['modified_since'] = min_tstamp
        self.pass_count += 1

        for projname in projects:
            project = self._lp.projects[projname]
            assert project, projname
            self._logger.info('Scanning branches in %s', project.name)
            for br in project.getBranches(**get_kwargs):
                if br.private:
                    continue
                self._logger.debug('Processing branch: %s = %s', br.name, br.bzr_identity)
                for tmpl in templates:
                    if fnmatch.fnmatch(br.bzr_identity, tmpl['pattern']):
                        self._logger.debug('Matched branch %s against template #%d',
                                    br.bzr_identity, tmpl['id'])
                        old_branches = branch_obj.search_read( [ \
                                            ('repo_id', '=', tmpl['repo_id'][0]),
                                            ('fetch_url','=', 'lp:' + br.bzr_identity)],
                                            fields=['fetch_url', 'poll_interval', 'branch_collection_id'])
        
                        self._logger.debug("old branches: %r", [b['id'] for b in old_branches])
                        # TODO remove in f3: (with fn field search)
                        old_branches = filter(lambda b: \
                                b['fetch_url'] == br.bzr_identity, \
                                old_branches)
                        
                        assert len(old_branches) <= 1
                        if br.lifecycle_status not in ('Experimental', 'Development', 'Mature'):
                            self._logger.debug("Branch %s is %s, found it in %r",
                                        br.bzr_identity, br.lifecycle_status,
                                        old_branches)
                            if not old_branches:
                                break
                            # full_off = (br.date_last_modified.date() <= old_tstamp.date())

                            old_ids = [ b['id'] for b in old_branches \
                                    if b['poll_interval'] >= 0 or b['branch_collection_id'] ]
                            
                            if not old_ids:
                                # list may (probably) be empty by now
                                break

                            self._logger.info('Deactivating branches %s', old_ids)
                            branch_obj.write(old_ids, {'poll_interval': -1, 'branch_collection_id': False })
                            break

                        if old_branches:
                            self._logger.debug('Branch already there with id %d, continuing', 
                                    old_branches[0]['id'])
                            break # we shall not match against rest of templates

                        if old_mode and br.date_last_modified.date() < min_tstamp.date():
                            self._logger.debug("No need to register old %s branch %s", 
                                    br.lifecycle_status, br.bzr_identity)
                            break

                        namedict = dict(name=br.name, lp=br.bzr_identity, \
                                unique_name=br.unique_name, user='')

                        # Break down the identity to elements:
                        if br.bzr_identity.startswith('lp:~'):
                            nusr, nproj, nname = br.bzr_identity[4:].split('/',2)
                            assert nproj == tmpl['project']
                            namedict.update(dict(user=nusr, branch_name=nname))
                            sub_url = '%s@%s' % (nusr, nname)
                        elif br.bzr_identity.startswith('lp:' + tmpl['project']+ '/'):
                            namedict['branch_name'] = br.bzr_identity[len(tmpl['project'])+4:]
                            sub_url = namedict['branch_name']
                        else:
                            self._logger.error("Cannot decode bzr identity: %s", br.bzr_identity)
                            break
                        
                        self._logger.debug("Namedict for %s: %r", br.name, namedict)
                        vals = { 'name': tmpl['name'] % namedict,
                                 'description': tmpl['description'],
                                 'poll_interval': tmpl['poll_interval'],
                                 'sub_url': sub_url,
                                 'repo_id': tmpl['repo_id'][0],
                                 'branch_collection_id': tmpl['branch_collection_id'] \
                                                    and tmpl['branch_collection_id'][0],
                                 }
                        
                        if tmpl['tech_code']:
                            vals['tech_code'] = tmpl['tech_code'] % namedict
                        
                        if br.description:
                            vals['description'] = br.description,
                        nbranch = branch_obj.create(vals)
                        self._logger.info('Registered new branch %s at #%d' % (vals['name'], nbranch))
                        break

def custom_options(parser):
    assert isinstance(parser, optparse.OptionParser)

    pgroup = optparse.OptionGroup(parser, "LP poller options")
    pgroup.add_option('-t', '--poll-interval', type=int,
                    help="Polling Interval")
    parser.add_option_group(pgroup)

if __name__ == "__main__":
    options.init(config=os.path.expanduser('~/.openerp/lp_poller.conf'), have_args=False)

    log = logging.getLogger('main')
    log.info("Init. Connecting...")

    rpc.openSession(**options.connect_dsn)

    if not rpc.login():
        raise Exception("Could not login!")
    log.info("Connected.")
    
    mssvc = MS_Service()
    mssvc.startService()
    log.info('Connected to LP')
    scanner = MS_BranchScanner(service=mssvc) # TODO interval
    
    scanner.start()

    try:
        while True:
            sleep(120)
    except KeyboardInterrupt:
        pass
    scanner.stop()
    mssvc.stopService()

    log.info('Exiting')
#eof
