# Copyright (C) 2008-2009 Canonical
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

Maintainer/author: gary.poster@canonical.com
"""

#import urllib
#import urlparse
#import StringIO
import os
import time

import buildbot.util
import buildbot.changes.base
import buildbot.changes.changes
from buildbot.util import deferredLocked

import bzrlib.branch
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
import twisted.spread.pb
from twisted.internet import defer, utils


def generate_change(branch,
                    old_revno=None, old_revid=None,
                    new_revno=None, new_revid=None,
                    blame_merge_author=False):
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
    change = {} # files, who, comments, revision; NOT branch (= branch.nick)
    if new_revno is None:
        new_revno = branch.revno()
    if new_revid is None:
        new_revid = branch.get_rev_id(new_revno)
    # TODO: This falls over if this is the very first revision
    if old_revno is None:
        old_revno = new_revno -1
    if old_revid is None:
        old_revid = branch.get_rev_id(old_revno)
    repository = branch.repository
    new_rev = repository.get_revision(new_revid)
    gaas = []
    if blame_merge_author:
        # this is a pqm commit or something like it
        gaas = repository.get_revision(
            new_rev.parent_ids[-1]).get_apparent_authors()
    else:
        gaas = new_rev.get_apparent_authors()
    
    change['who'] = gaas[0]
    change['authors'] = gaas[1:]
    # maybe useful to know:
    # name, email = bzrtools.config.parse_username(change['who'])
    change['comments'] = new_rev.message
    change['revision'] = new_revno
    change['hash'] = new_revid
    files = change['files'] = []
    filesb = change['filesb'] = []
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
    return change


class BzrPoller(buildbot.changes.base.PollingChangeSource,
                buildbot.util.ComparableMixin):

    compare_attrs = ['url']

    def __init__(self, url, poll_interval=10*60, blame_merge_author=False,
                    branch_name=None, branch_id=None, category=None,
                    proxy_location=None, slave_proxy_url=None):
        # poll_interval is in seconds, so default poll_interval is 10
        # minutes.
        # bzr+ssh://bazaar.launchpad.net/~launchpad-pqm/launchpad/devel/
        # works, lp:~launchpad-pqm/launchpad/devel/ doesn't without help.
        if url.startswith('lp:'):
            #url = 'bzr+ssh://bazaar.launchpad.net/' + url[3:]
            url = 'https://code.launchpad.net/' + url[3:]
        elif url.startswith('/'):
           url = 'file://' + url
        self.url = url
        self.poll_interval = poll_interval
        self.blame_merge_author = blame_merge_author
        self.branch_name = branch_name
        self.branch_id = branch_id
        self.category = category
        self.proxy_location = os.path.expanduser(proxy_location)
        self.slave_proxy_url = slave_proxy_url
        self.initLock = defer.DeferredLock()
        self.lastPoll = time.time()

    def startService(self):
        twisted.python.log.msg("BzrPoller(%s) starting" % self.url)
        d = self.initRepository()
        buildbot.changes.base.PollingChangeSource.startService(self)

    @deferredLocked('initLock')
    def initRepository(self):
        d = defer.succeed(None)
        def checkout_branch(_):
            """ Checkout the remote (LP) branch into the local proxy_location
            """
            d = utils.getProcessOutputAndValue('bzr',
                    ['branch', '-q', '--bind', '--no-tree',
                        self.url, self.proxy_location])
            d.addCallback(self._convert_nonzero_to_failure)
            d.addErrback(self._stop_on_failure)
            self.lastPoll = time.time()
            return d

        def get_last_revision(_):
            last_cid = self.master.db.getLatestChangeNumberNow(branch=self.branch_id) # TODO defer
            if last_cid:
                change = self.master.db.getChangeNumberedNow(last_cid)
                assert change.branch_id == self.branch_id, "%r != %r" % (change.branch_id, self.branch_id)
                self.last_revision = int(change.revision)
                # We *assume* here that the last change registered with the
                # branch is a head earlier than our current revision.
                # But, it might happen that the repo is diverged and that change
                # is no longer in the history...
            else:
                self.last_revision = None

        def try_open_url(_):
            try:
                # Just try to open the branch. There is sth wrong in bzrlib
                # wrt. the import order, so try to consume the exception here.
                branch = bzrlib.branch.Branch.open_containing(self.proxy_location or self.url)[0]
            except Exception, e:
                twisted.python.log.err("Cannot open the branch: %s" % e)

        d.addCallback(try_open_url)
        if self.proxy_location:
            if not os.path.isdir(self.proxy_location):
                d.addCallback(checkout_branch)
        d.addCallback(get_last_revision)
        return d

    def describe(self):
        return "BzrPoller watching %s" % self.url

    @deferredLocked('initLock')
    def poll(self):
        d = defer.succeed(None)
        if self.proxy_location:
            d.addCallback(self._update_branch)
        d.addCallback(self._get_changes)
        return d

    def _update_branch(self, _):
        twisted.python.log.msg("Updating branch from %s" % self.url)
        branch = bzrlib.branch.Branch.open_containing(self.proxy_location)[0]
        d = twisted.internet.threads.deferToThread(branch.update)
        self.lastPoll = time.time()
        return d

    @defer.deferredGenerator
    def _get_changes(self, _):
        branch = bzrlib.branch.Branch.open_containing(self.url)[0]
        branch_name = self.branch_name
        changes = []
        change = generate_change(
            branch, blame_merge_author=self.blame_merge_author)
        if (self.last_revision is None or
            change['revision'] != self.last_revision):
            change['branch'] = branch_name
            change['branch_id'] = self.branch_id
            change['category'] = self.category
            changes.append(change)
            if self.last_revision is not None:
                while self.last_revision + 1 < change['revision']:
                    change = generate_change(
                        branch, new_revno=change['revision']-1,
                        blame_merge_author=self.blame_merge_author)
                    change['branch'] = branch_name
                    change['branch_id'] = self.branch_id
                    change.setdefault('category', self.category)
                    changes.append(change)
        changes.reverse()
        for change in changes:
            d = self.master.addChange(**change)
            wfd = defer.waitForDeferred(d)
            yield wfd
            self.last_revision = change['revision']
        twisted.python.log.msg("We have %d changes" % len(changes))

    def _stop_on_failure(self, f):
        "utility method to stop the service when a failure occurs"
        if self.running:
            d = defer.maybeDeferred(lambda : self.stopService())
            d.addErrback(twisted.python.log.err, 'while stopping broken BzrPoller service')
        return f

    def _convert_nonzero_to_failure(self, res):
        "utility method to handle the result of getProcessOutputAndValue"
        (stdout, stderr, code) = res
        if code != 0:
            raise EnvironmentError('command failed with exit code %d: %s' % (code, stderr))
        return (stdout, stderr, code)


#eof
