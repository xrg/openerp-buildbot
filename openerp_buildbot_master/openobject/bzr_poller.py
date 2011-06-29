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
from buildbot.util import deferredLocked, epoch2datetime

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
from twisted.python.failure import Failure
import twisted.spread.pb
from twisted.internet import defer, utils


def generate_change(branch,
                    old_revno=None, old_revid=None,
                    new_revno=None, new_revid=None,
                    blame_merge_author=False,
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
    change = {} # files, who, comments, revision; NOT branch (= branch.nick)
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
    new_rev = repository.get_revision(new_revid)
    gaas = []
    if blame_merge_author:
        # this is a pqm commit or something like it
        gaas = repository.get_revision(
            new_rev.parent_ids[-1]).get_apparent_authors()
    else:
        gaas = new_rev.get_apparent_authors()
    
    props = {}
    change['who'] = gaas[0]
    props['authors'] = gaas[1:]
    # maybe useful to know:
    # name, email = bzrtools.config.parse_username(change['who'])
    change['when_timestamp'] = epoch2datetime(new_rev.timestamp)
    change['comments'] = new_rev.message
    change['revision'] = new_revno
    props['hash'] = new_revid
    files = change['files'] = []
    filesb = props['filesb'] = []
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

    compare_attrs = ['url']
    updateLock = defer.DeferredLock() # class-wide

    def __init__(self, url, poll_interval=10*60, blame_merge_author=False,
                    branch_name=None, branch_id=None, category=None,
                    proxy_location=None, slave_proxy_url=None):
        # poll_interval is in seconds, so default poll_interval is 10
        # minutes.
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
        self.last_revision = None
        self.local_run = False # would skip pulling from LP, for testing

    def _get_url(self):
        # bzr+ssh://bazaar.launchpad.net/~launchpad-pqm/launchpad/devel/
        # works, lp:~launchpad-pqm/launchpad/devel/ doesn't without help.
        if self.url.startswith('lp:'):
           #url = 'bzr+ssh://bazaar.launchpad.net/' + url[3:]
           return 'https://code.launchpad.net/' + self.url[3:]
        elif self.url.startswith('/'):
            return 'file://' + self.url

    def startService(self):
        twisted.python.log.msg("BzrPoller(%s) starting" % self.url)
        d = self.initRepository()
        buildbot.changes.base.PollingChangeSource.startService(self)

    @deferredLocked('initLock')
    def initRepository(self):
        
        def checkout_branch(_):
            """ Checkout the remote (LP) branch into the local proxy_location
            """
            d = utils.getProcessOutputAndValue('bzr',
                    ['branch', '-q', '--bind', '--no-tree',
                        self._get_url(), self.proxy_location])
            d.addCallback(self._convert_nonzero_to_failure)
            d.addErrback(self._stop_on_failure)
            self.lastPoll = time.time()
            return d

        def get_last_revision(_):
            self.last_revision = None
            last_cid = self.master.db.changes._getLatestChangeNumberNow(branch=self.branch_id) # TODO defer
            while last_cid:
                change = self.master.db.changes._get_change_num(last_cid)
                assert change['repository'] == str(self.branch_id), "%r != %r" % (change['repository'], self.branch_id)
                if not change['revision']:
                    # This must have been a failed merge "commit", go up
                    last_cid = change['properties'].get('parent_id', (False, False))[0]
                    continue
                self.last_revision = int(change['revision'])
                # We *assume* here that the last change registered with the
                # branch is a head earlier than our current revision.
                # But, it might happen that the repo is diverged and that change
                # is no longer in the history...
                break

        def _updateLock_release(x):
            self.updateLock.release()
            return x
        d = defer.succeed(None)
        if self.proxy_location:
            if not os.path.isdir(self.proxy_location):
                d = self.updateLock.acquire()
                d.addCallback(checkout_branch)
                d.addBoth(_updateLock_release)
        d.addCallback(get_last_revision)
        return d

    def describe(self):
        return "BzrPoller watching %s" % self.url

    @deferredLocked('initLock')
    def poll(self):
        d = defer.succeed(None)
        if self.proxy_location and not self.local_run:
            d.addCallback(self._update_branch)
        d.addCallback(self._get_changes)
        return d

    @deferredLocked('updateLock')
    def _update_branch(self, _):
        twisted.python.log.msg("Updating branch from %s to %s" % (self.url, self.proxy_location))
        d = utils.getProcessOutputAndValue('bzr', ['pull', '-q', ], path=self.proxy_location)
        d.addCallback(self._convert_nonzero_to_failure)
        self.lastPoll = time.time()
        return d

    @defer.deferredGenerator
    def _get_changes(self, _):
        branch = bzrlib.branch.Branch.open_containing(self.proxy_location or self._get_url())[0]
        branch_name = self.branch_name
        changes = []
        change = generate_change(branch,
                    blame_merge_author=self.blame_merge_author,
                    last_revision=self.last_revision)
        if change:
            change['branch'] = self.url
            change['repository'] = str(self.branch_id)
            change['category'] = self.category
            changes.append(change)
            if self.last_revision is not None:
                while self.last_revision + 1 < change['revision']:
                    change = generate_change(
                        branch, new_revno=change['revision']-1,
                        blame_merge_author=self.blame_merge_author)
                    change['branch'] = self.url
                    change['repository'] = str(self.branch_id)
                    change.setdefault('category', self.category)
                    changes.append(change)
        if changes:
            self.last_revision = changes[0]['revision']
            twisted.python.log.msg("We have %d changes" % len(changes))
            changes.reverse()
        
            for change in changes:
                wfd = defer.waitForDeferred(self.master.addChange(**change))
                yield wfd
                wfd.getResult()
 
    def _stop_on_failure(self, f):
        "utility method to stop the service when a failure occurs"
        d = defer.maybeDeferred(lambda : self.running and self.stopService())
        d.addErrback(twisted.python.log.err, 'while stopping broken BzrPoller service')
        if f and isinstance(f, Failure) and isinstance(f.value, EnvironmentError):
            twisted.python.log.err("Stopping BzrPoller: %s" % f.value.args[0])
            # don't return, we handled it already
            return None
        else:
            twisted.python.log.err("Stopping BzrPoller")
            return f

    def _convert_nonzero_to_failure(self, res):
        "utility method to handle the result of getProcessOutputAndValue"
        (stdout, stderr, code) = res
        if code != 0:
            raise EnvironmentError('command failed with exit code %d: %s' % (code, stderr))
        return (stdout, stderr, code)


#eof
