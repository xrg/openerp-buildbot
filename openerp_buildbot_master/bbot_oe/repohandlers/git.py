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

    def _get_commit_files2(self, rev):
        """Get list of commit files and stats (part 1/2)

            This retrieves the status/name pairs of files actually modified.
            In a merge commit, it will *only* list conflict-modified files

        """
        args = ['log', rev, '--name-status', '--no-walk', r'--format=%n']
        d = utils.getProcessOutput(self.gitbin, args, path=self.workdir, env=dict(PATH=os.environ['PATH']), errortoo=False )
        def process(git_output):
            fileDic = {}
            for x in git_output.split('\n'):
                if not x:
                    continue
                status, fname = x.split('\t',1)
                fileDic[fname] = status
            return fileDic
        d.addCallback(process)
        return d

    def _get_commit_files3(self, rev):
        """Get list of commit files and diff stats

            The second part, list lines added/removed at files
        """
        # git show HEAD --no-walk --numstat --format='%n'
        args = ['log', rev, '--numstat', '--no-walk', r'--format=%n']
        d = utils.getProcessOutput(self.gitbin, args, path=self.workdir, env=dict(PATH=os.environ['PATH']), errortoo=False )
        def process(git_output):
            fileDic = {}
            for x in git_output.split('\n'):
                if not x:
                    continue
                add, rem, fname = x.split('\t',2)
                fileDic[fname] = (add, rem)
            return fileDic
        d.addCallback(process)
        return d

    @defer.deferredGenerator
    def _process_changes(self, unused_output):
        # get the change list
        revListArgs = ['log', '%s..%s/%s' % (self.localBranch, self.remoteName, self.branch), r'--format=%H']
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
                self._get_commit_files2(rev),
                self._get_commit_files3(rev),
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

            timestamp, name, files2, files3, comments = [ r[1] for r in results ]

            #process the files
            filesb = []
            for fname, stats in files3.items():
                if stats == ('-', '-'):
                    stats = (False, False)
                else:
                    stats = map(int, stats)

                if not fname in files2:
                    # it was cleanly merged
                    filesb.append(dict(filename=fname, ctype='f',
                            merge_add=stats[0], merge_rem=stats[1]))
                else:
                    status = files2[fname]
                    ctype = '?'
                    for letter in 'MDARC': #ordered by importance
                        if letter in status:
                            ctype = letter.lower()
                            break
                    filesb.append(dict(filename=fname, ctype=ctype,
                            lines_add=stats[0], lines_rem=stats[1]))

            props['filesb'] = filesb

            d = self.master.addChange(
                   author=name,
                   revision=rev,
                   files=[],
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
        # Early bail-out
        if p_interval <= 0:
            return

        kwargs = {'bare': True} # tmpconf['poller_kwargs'].copy()

        kwargs.update (repourl=fetch_url,
                pollInterval = p_interval,
                branch=pbr.get('branch_path', 'master'),
                branch_id=pbr['branch_id'],)

        if 'local_branch' in pbr:
            kwargs['localBranch'] = pbr['local_branch']

        if 'remote_name' in pbr:
            kwargs['remoteName'] = pbr['remote_name']

        if 'workdir' in pbr:
            kwargs['workdir'] = os.path.expanduser(pbr['workdir'])

        category = '' # TODO: revise
        if 'group' in pbr:
            category = pbr['group'].replace('/','_').replace('\\','_') # etc.
            kwargs['category'] = pbr['group']

        conf['change_source'].append(GitPoller_OE(**kwargs))


repo_types = { 'git': GitFactory }
