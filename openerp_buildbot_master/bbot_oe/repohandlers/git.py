# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP Buildbot
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

from bbot_oe.repo_iface import RepoFactory
from buildbot.changes.gitpoller import GitPoller
from twisted.internet import defer, utils
from twisted.python import log
import os
from buildbot.util import epoch2datetime

class GitPoller_OE(GitPoller):
    """ Enhanced subclass to fit OpenERP backend, record more data
    
    """
    
    def __init__(self, **kwargs):
        branch_id = kwargs.pop('branch_id') # mandatory
        GitPoller.__init__(self, **kwargs)
        self.branch_id = branch_id

    @defer.deferredGenerator
    def _process_changes(self, unused_output):
        # get the change list
        revListArgs = ['log', '%s..%s/%s' % (self.branch, self.remoteName, self.branch), r'--format=%H']
        self.changeCount = 0
        d = utils.getProcessOutput(self.gitbin, revListArgs, path=self.workdir,
                                   env=dict(PATH=os.environ['PATH']), errortoo=False )
        wfd = defer.waitForDeferred(d)
        yield wfd
        results = wfd.getResult()

        # process oldest change first
        revList = results.split()
        if not revList:
            return

        revList.reverse()
        self.changeCount = len(revList)
            
        log.msg('gitpoller: processing %d changes: %s in "%s"'
                % (self.changeCount, revList, self.workdir) )

        for rev in revList:
            dl = defer.DeferredList([
                self._get_commit_timestamp(rev),
                self._get_commit_name(rev),
                self._get_commit_files(rev),
                #self._get_commit_files2(rev),
                self._get_commit_comments(rev),
            ], consumeErrors=True)

            wfd = defer.waitForDeferred(dl)
            yield wfd
            results = wfd.getResult()

            # check for failures
            failures = [ r[1] for r in results if not r[0] ]
            if failures:
                # just fail on the first error; they're probably all related!
                raise failures[0]

            props = dict(branch_id=self.branch_id, hash=rev, ) # TODO
            
            timestamp, name, files, comments = [ r[1] for r in results ]
            d = self.master.addChange(
                   author=name,
                   revision=rev,
                   files=files,
                   comments=comments,
                   when_timestamp=epoch2datetime(timestamp),
                   branch=self.branch,
                   category=self.category,
                   project=self.project,
                   repository=self.repourl,
                   properties=props)
            wfd = defer.waitForDeferred(d)
            yield wfd
            results = wfd.getResult()
    
class GitFactory(RepoFactory):
    @classmethod
    def createPoller(cls, poller_dict, conf, tmpconf):
        pbr = poller_dict
        if pbr.get('mode', 'branch') != 'branch':
            raise ValueError("Cannot handle %s mode yet" % pbr['mode'])
        fetch_url = pbr['fetch_url']
        p_interval = int(pbr.get('poll_interval', 600))
        kwargs = {} # tmpconf['poller_kwargs'].copy()
        category = ''
        if 'group' in pbr:
            category = pbr['group'].replace('/','_').replace('\\','_') # etc.
            kwargs['category'] = pbr['group']

        if p_interval > 0:
            conf['change_source'].append(GitPoller_OE(repourl=fetch_url,
                pollInterval = p_interval,
                branch=pbr.get('branch_path', 'master'),
                branch_id=pbr['branch_id'],
                **kwargs))


repo_types = { 'git': GitFactory }
