# Copyright (C) 2008-2009 Canonical
# Copyright (C) 2010-2011 OpenERP SA
# Copyright (C) 2011 P. Christeas
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""\
bzr buildbot integration
========================

This file contains both bzr commit/change hooks and a bzr poller.

------------
Requirements
------------

This has been tested with buildbot 0.7.9, bzr 1.10, and Twisted 8.1.0.  It
should work in subsequent releases.

For the hook to work, Twisted must be installed in the same Python that bzr
uses.

------
Poller
------

Put this file somewhere that your buildbot configuration can import it.  Even
in the same directory as the master.cfg should work.  Install the poller in
the buildbot configuration as with any other change source.  Minimally,
provide a URL that you want to poll (bzr://, bzr+ssh://, or lp:), though make
sure the buildbot user has necessary privileges.  You may also want to specify
these optional values.

poll_interval: the number of seconds to wait between polls.  Defaults to 10
               minutes.

branch_name: any value to be used as the branch name.  Defaults to None, or
             specify a string, or specify the constants from this file SHORT
             or FULL to get the short branch name or full branch address.

blame_merge_author: normally, the user that commits the revision is the user
                    that is responsible for the change. When run in a pqm
                    (Patch Queue Manager, see https://launchpad.net/pqm)
                    environment, the user that commits is the Patch Queue
                    Manager, and the user that committed the merged, *parent*
                    revision is responsible for the change. set this value to
                    True if this is pointed against a PQM-managed branch.

-------------------
Contact Information
-------------------

Original author: gary.poster@canonical.com
Hacker: xrg@hellug.gr
"""

import os
import time
import re

import buildbot.util
import buildbot.changes.base
import buildbot.changes.changes
from buildbot.util import deferredLocked, epoch2datetime

import bzrlib.branch
import bzrlib.repository
import bzrlib.errors
import bzrlib.trace
import twisted.cred.credentials
import twisted.internet.base
import twisted.internet.defer
import twisted.internet.reactor
import twisted.internet.selectreactor
import twisted.internet.task
import twisted.internet.threads
import twisted.python.log
from twisted.python.failure import Failure
import twisted.spread.pb
from twisted.internet import defer, utils

from bbot_oe.repo_iface import RepoFactory

mege = re.compile(r'([^\(]+) *(\(.*\))? *(\< ?(.*?) ?\>)$')

# maybe useful to know:
# name, email = bzrtools.config.parse_username(change['who'])

def split_email(an):
    """ Split an email expression to name, mail
    """
    ma = mege.match(an.strip())
    
    if ma:
        an = ma.group(1).strip()
        if ma.group(2):
            an += ' ' + ma.group(2)
        aemail = ma.group(4)
        return (an, aemail)
    else:
        return ('', an)

def generate_change(branch, branch_id,
                    old_revno=None, old_revid=None,
                    new_revno=None, new_revid=None,
                    blame_merge_author=False,
                    branch_nick=None,
                    last_revision=None):
    """Return a dict of information about a change to the branch.

    Dict has keys of "files", "who", "comments", and "revision", as used by
    the buildbot Change (and the PBChangeSource).

    If only the branch is given, the most recent change is returned.

    If only the new_revno is given, the comparison is expected to be between
    it and the previous revno (new_revno -1) in the branch.

    Passing old_revid and new_revid is only an optimization, included because
    bzr hooks usually provide this information.

    blame_merge_author means that the author of the merged branch is
    identified as the "who", not the person who committed the branch itself.
    This is typically used for PQM.
    """

    if new_revno is None:
        new_revno = branch.revno()
    if last_revision and (new_revno == last_revision):
        # early exit when branch is up to date
        return None
    if new_revid is None:
        new_revid = branch.get_rev_id(new_revno)
    # TODO: This falls over if this is the very first revision
    if old_revno is None:
        old_revno = new_revno -1
    if old_revid is None:
        old_revid = branch.get_rev_id(old_revno)
    repository = branch.repository

    return _generate_change2(repository=repository, new_revid=new_revid,
            old_revid=old_revid, branch_id=branch_id, new_revno=new_revno,
            blame_merge_author=blame_merge_author, branch_nick=branch_nick)

def generate_change_revid(repository, new_revid, branch_id, new_revno=None):
    try:
        return _generate_change2(repository, new_revid=new_revid, old_revid=None,
                    branch_id=branch_id, new_revno=new_revno)
    except bzrlib.errors.NoSuchRevision, e:
        twisted.python.log.err('Unknown bzr revision: %s' % e)
        return None

def _generate_change2(repository, new_revid, old_revid,
                    branch_id, new_revno=False,
                    blame_merge_author=False,
                    branch_nick=None ):
    """ Inner workings of generate_change(), relative to repository
    """
    change = {} # files, who, comments, revision; NOT branch (= branch.nick)

    new_rev = repository.get_revision(new_revid)
    gaas = []
    if branch_nick is not None:
        # stop at branch boundaries, don't let the history explode back
        if new_rev.properties.get('branch-nick') != branch_nick:
            twisted.python.log.msg('Stopping at cross-branch border: "%s"->"%s"' % \
                (branch_nick, new_rev.properties.get('branch_nick')))
            return None
    if blame_merge_author:
        # this is a pqm commit or something like it
        gaas = repository.get_revision(
            new_rev.parent_ids[-1]).get_apparent_authors()
    else:
        gaas = new_rev.get_apparent_authors()

    props = {'branch_id': branch_id}
    props['author_name'], change['author'] = split_email(gaas[0])
    if new_rev.committer and new_rev.committer != gaas[0]:
        props['committer_name'], props['committer_email'] = split_email(new_rev.committer)
    props['authors'] = gaas[1:]
    change['when_timestamp'] = epoch2datetime(new_rev.timestamp)
    change['comments'] = new_rev.message
    change['revision'] = new_revno
    props['hash'] = new_revid
    props['parent_hashes'] = new_rev.parent_ids[:]
    files = change['files'] = []
    filesb = props['filesb'] = []
    if (not old_revid) and (new_rev.parent_ids):
        old_revid = new_rev.parent_ids[0]
    changes = repository.revision_tree(new_revid).changes_from(
        repository.revision_tree(old_revid))
    tmp_kfiles = set()
    for (collection, name, ctype) in ((changes.added, 'ADDED', 'a'),
                               (changes.removed, 'REMOVED', 'd'),
                               (changes.modified, 'MODIFIED', 'm')):
        for info in collection:
            path = info[0]
            kind = info[2]
            if path in tmp_kfiles:
                continue
            tmp_kfiles.add(path)
            files.append(path)
            filesb.append({'filename': path, 'ctype': ctype,
                        'lines_add':0, 'lines_rem':0 })
    for info in changes.renamed:
        oldpath, newpath, id, kind, text_modified, meta_modified = info
        if oldpath in tmp_kfiles:
            continue
        tmp_kfiles.add(oldpath)
        files.append(oldpath)
        filesb.append({'filename': oldpath, 'ctype': 'r',
                        'newpath': newpath,
                        'lines_add':0, 'lines_rem':0 })
    change['properties'] = props
    return change

class BzrPoller(buildbot.changes.base.PollingChangeSource,
                buildbot.util.ComparableMixin):

    compare_attrs = ['fetch_url', 'pollInterval', 'branch_id', 'workdir', 'local_branch']
    updateLock = defer.DeferredLock() # class-wide

    def __init__(self, fetch_url, poll_interval=10*60, blame_merge_author=False,
                    branch_path=None, branch_id=None, category=None,
                    workdir=None, local_branch=None, last_revision=None,
                    allHistory=False, repourl=None):
        """
            @param fetch_url the remote url to fetch the branch from
            @param branch_path the remote name of the branch
            @param workdir if specified, the local proxy of the branch to poll
            @param local_branch the name of the branch within workdir
            @param poll_interval is in seconds, so default poll_interval is 10
                minutes.
            @param last_revision the last known revision from previous
                incarnations of the poller, so that this time it only scans
                from there onwards
            @param repourl the URL to access the repository, if one
        """
        # buildbot.changes.base.PollingChangeSource.__init__(self)
        self.fetch_url = fetch_url
        self.pollInterval = poll_interval
        self.blame_merge_author = blame_merge_author
        self.branch_path = branch_path
        self.branch_id = branch_id
        self.category = category
        if workdir:
            self.repo_dir = os.path.expanduser(workdir)
        else:
            self.repo_dir = None
        self.initLock = defer.DeferredLock()
        self.lastPoll = time.time()
        self.local_branch = local_branch
        self.repourl = repourl
        if (not last_revision) and allHistory:
            twisted.python.log.msg("Historic mode for branch: %s" % fetch_url)
            self.last_revision = 0
            self.historic_mode = True
        else:
            self.historic_mode = False
            self.last_revision = last_revision

        self.branch_dir = None # to be filled after init
        self.error_count = 0

    def _get_url(self):
        # bzr+ssh://bazaar.launchpad.net/~launchpad-pqm/launchpad/devel/
        # works, lp:~launchpad-pqm/launchpad/devel/ doesn't without help.
        if self.fetch_url.startswith('lp:'):
           return 'https://code.launchpad.net/' + self.fetch_url[3:]
        elif self.fetch_url.startswith('/'):
            return 'file://' + self.fetch_url

    def startService(self):
        twisted.python.log.msg("BzrPoller(%s) starting" % self.fetch_url)
        self.error_count = 0
        d = self.initRepository()
        buildbot.changes.base.PollingChangeSource.startService(self)
        return d

    @deferredLocked('initLock')
    def initRepository(self):

        def _init_repo(_):
            """ Initializes the local proxy repository
            """
            os.mkdir(self.repo_dir)
            d = utils.getProcessOutputAndValue('bzr',
                    ['init-repo', '--no-trees', '.'], path=self.repo_dir)
            d.addCallback(self._convert_nonzero_to_failure)
            d.addErrback(self._stop_on_failure)
            return d

        def checkout_branch(_):
            """ Checkout the remote (LP) branch into the local proxy_location
            """
            d = utils.getProcessOutputAndValue('bzr',
                    ['branch', '-q', '--bind', '--no-tree',
                        self._get_url(), self.branch_dir])
            d.addCallback(self._convert_nonzero_to_failure)
            d.addErrback(self._stop_on_failure)
            self.lastPoll = time.time()
            return d

        def _updateLock_release(x):
            self.updateLock.release()
            return x

        d = defer.succeed(None)

        if self.repo_dir:
            self.branch_dir = self.repo_dir
            if not self.branch_dir.endswith('/'):
                self.branch_dir += '/'
            self.branch_dir += self.local_branch or self.branch_path

            if not os.path.isdir(self.branch_dir):
                d = self.updateLock.acquire()
                if not os.path.isdir(self.repo_dir):
                    d.addCallback(_init_repo)
                d.addCallback(checkout_branch)
                d.addBoth(_updateLock_release)
        return d

    def describe(self):
        status = ""
        if not self.master:
            status = ' [STOPPED by master]'
        elif (not getattr(self, '_loop')) or not self._loop.running:
            status = ' [STOPPED] '
        return "BzrPoller watching %s%s" % (self.fetch_url, status)

    @deferredLocked('initLock')
    def poll(self):
        d = defer.succeed(None)
        if self.branch_dir:
            d.addCallback(self._update_branch)
        d.addCallback(self._get_changes)
        d.addErrback(self._poll_failure)
        return d

    @deferredLocked('updateLock')
    def _update_branch(self, _):
        twisted.python.log.msg("Updating branch from %s to %s" % \
                                (self.fetch_url, self.branch_dir))
        d = utils.getProcessOutputAndValue('bzr', ['pull', '-q', ], path=self.branch_dir)
        d.addCallback(self._convert_nonzero_to_failure)
        self.lastPoll = time.time()
        return d

    @defer.deferredGenerator
    def _get_changes(self, _):
        branch = bzrlib.branch.Branch.open_containing(self.branch_dir or self._get_url())[0]
        changes = []
        change = generate_change(branch, self.branch_id,
                    blame_merge_author=self.blame_merge_author,
                    last_revision=self.last_revision)
        if change:
            change['branch'] = self.fetch_url
            change['category'] = self.category
            changes.append(change)
            if self.last_revision is not None:
                if self.historic_mode:
                    branch_nick = branch.repository.get_revision(branch.last_revision()).\
                                properties.get('branch-nick',None)
                else:
                    branch_nick = None
                while self.last_revision + 1 < change['revision']:
                    change = generate_change( branch, self.branch_id,
                        new_revno=change['revision']-1,
                        blame_merge_author=self.blame_merge_author,
                        branch_nick=branch_nick)
                    if not change:
                        break
                    change['branch'] = self.fetch_url
                    change.setdefault('category', self.category)
                    changes.append(change)
        if changes:
            self.last_revision = changes[0]['revision']
            twisted.python.log.msg("We have %d changes" % len(changes))
            changes.reverse()

            for change in changes:
                if self.historic_mode:
                    change['skip_build'] = True
                wfd = defer.waitForDeferred(self.master.addChange(**change))
                yield wfd
                wfd.getResult()
        self.historic_mode = False

    def _stop_on_failure(self, f, message=None):
        "utility method to stop the service when a failure occurs"
        d = defer.maybeDeferred(lambda : self.running and self.stopService())
        d.addErrback(twisted.python.log.err, 'while stopping broken BzrPoller service')
        
        self.master.db.sendMessage('Stopping bzr poller:',
                        '%s, bzr poller for %s had to stop. ',
                        (message or 'Error', self.fetch_url),
                        instance=f)

        return None

    def _poll_failure(self, f):
        twisted.python.log.err(f, 'bzr poller: please resolve issues in local repo: %s' % self.workdir)
        # this used to stop the service, but this is (a) unfriendly to tests and (b)
        # likely to leave the error message lost in a sea of other log messages
        self.master.db.sendMessage('Bzr poll:',
                        'Bzr poller for %s at %s cannot poll branch.',
                        (self.fetch_url, self.workdir),
                        instance=f)
        if self.error_count >= 5:
            self.error_count = 0
            d = defer.maybeDeferred(lambda : self.running and self.stopService())
            d.addErrback(twisted.python.log.err, 'while stopping broken BzrPoller service')
        else:
            self.error_count += 1


    def _convert_nonzero_to_failure(self, res):
        "utility method to handle the result of getProcessOutputAndValue"
        (stdout, stderr, code) = res
        if code != 0:
            raise EnvironmentError('command failed with exit code %d: %s' % (code, stderr))
        return (stdout, stderr, code)

    @defer.inlineCallbacks
    def rescan_commits(self, branch, commSpecs, standalone=True):
        """ Rescan and register arbitrary commits from commSpecs

            @param branch the branch name, to satisfy buildbot's Change()
            @param commSpecs a list of 2-item tuples:
                (commit, props)
            @param standalone causes the algorithm to only list the
                specific commits. Otherwise, lists the full history of
                each commit since the known branches

            see also same function in gitpoller
        """
        twisted.python.log.msg("Rescanning %d commits" % len(commSpecs))
        assert standalone, "Not prepared to do history traversal yet"


        repourl = self.repo_dir or self.repourl

        if not repourl:
            raise ValueError("rescan_commits() must not be called w/o repourl")

        if repourl.startswith('lp:'):
           repourl = 'https://launchpad.net/' + repourl[3:]
        elif repourl.startswith('/'):
            repourl = 'file://' + repourl

        repository = bzrlib.repository.Repository.open(repourl)
        changes = []

        for commit, props in commSpecs:
            change = generate_change_revid(repository, commit, branch_id=props['branch_id'])
            if not change:
                continue

            change['branch'] = branch
            change['category'] = self.category
            changes.append(change)

        twisted.python.log.msg("We have %d changes" % len(changes))

        for change in changes:
            change['skip_build'] = True
            yield self.master.addChange(**change)

class BzrFactory(RepoFactory):
    @classmethod
    def createPoller(cls, poller_dict, conf, tmpconf):
        pbr = poller_dict # a shorthand
        if pbr.get('mode','branch') != 'branch':
            raise ValueError("Cannot handle %r mode" % pbr.get('mode'))

        kwargs = {}
        # category = ''
        if 'group' in pbr:
            # category = pbr['group'].replace('/','_').replace('\\','_') # etc.
            kwargs['category'] = pbr['group']

        for kk in ('branch_id', 'branch_path', 'workdir', 'local_branch',
                'fetch_url', 'poll_interval', 'last_revision', 'allHistory',
                'repourl'):
            if kk in pbr:
                kwargs[kk] = pbr[kk]

        if pbr.get('poll_interval', -1) > 0:
            conf['change_source'].append(BzrPoller( **kwargs))

repo_types = { 'bzr': BzrFactory }

#eof
