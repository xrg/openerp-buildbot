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

import buildbot.util
import buildbot.changes.base
import buildbot.changes.changes

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
    if blame_merge_author:
        # this is a pqm commit or something like it
        change['who'] = repository.get_revision(
            new_rev.parent_ids[-1]).get_apparent_author()
    else:
        change['who'] = new_rev.get_apparent_author()
    # maybe useful to know:
    # name, email = bzrtools.config.parse_username(change['who'])
    change['comments'] = new_rev.message
    change['revision'] = new_revno
    files = change['files'] = []
    changes = repository.revision_tree(new_revid).changes_from(
        repository.revision_tree(old_revid))
    for (collection, name) in ((changes.added, 'ADDED'),
                               (changes.removed, 'REMOVED'),
                               (changes.modified, 'MODIFIED')):
        for info in collection:
            path = info[0]
            kind = info[2]
            files.append(' '.join([path, kind, name]))
    for info in changes.renamed:
        oldpath, newpath, id, kind, text_modified, meta_modified = info
        elements = [oldpath, kind,'RENAMED', newpath]
        if text_modified or meta_modified:
            elements.append('MODIFIED')
        files.append(' '.join(elements))
    return change


class BzrPoller(buildbot.changes.base.ChangeSource,
                buildbot.util.ComparableMixin):

    compare_attrs = ['url']

    def __init__(self, url, poll_interval=10*60, blame_merge_author=False,
                    branch_name=None, category=None):
        # poll_interval is in seconds, so default poll_interval is 10
        # minutes.
        # bzr+ssh://bazaar.launchpad.net/~launchpad-pqm/launchpad/devel/
        # works, lp:~launchpad-pqm/launchpad/devel/ doesn't without help.
        if url.startswith('lp:'):
            url = 'bzr+ssh://bazaar.launchpad.net/' + url[3:]
        self.url = url
        self.poll_interval = poll_interval
        self.loop = twisted.internet.task.LoopingCall(self.poll)
        self.blame_merge_author = blame_merge_author
        self.branch_name = branch_name
        self.category = category

    def startService(self):
        twisted.python.log.msg("BzrPoller(%s) starting" % self.url)
        buildbot.changes.base.ChangeSource.startService(self)
        if self.branch_name is None:
            ourbranch = self.url
        else:
            ourbranch = self.branch_name
        for change in reversed(self.parent.changes):
            if change.branch == ourbranch:
                self.last_revision = change.revision
                break
        else:
            self.last_revision = None
        self.polling = False
        twisted.internet.reactor.callWhenRunning(
            self.loop.start, self.poll_interval)

    def stopService(self):
        twisted.python.log.msg("BzrPoller(%s) shutting down" % self.url)
        self.loop.stop()
        return buildbot.changes.base.ChangeSource.stopService(self)

    def describe(self):
        return "BzrPoller watching %s" % self.url

    @twisted.internet.defer.inlineCallbacks
    def poll(self):
        if self.polling: # this is called in a loop, and the loop might
            # conceivably overlap.
            return
        self.polling = True
        try:
            # On a big tree, even individual elements of the bzr commands
            # can take awhile. So we just push the bzr work off to a
            # thread.
            try:
                changes = yield twisted.internet.threads.deferToThread(
                    self.getRawChanges)
            except (SystemExit, KeyboardInterrupt):
                raise
            except:
                # we'll try again next poll.  Meanwhile, let's report.
                twisted.python.log.err()
            else:
                for change in changes:
                    yield self.addChange(
                        buildbot.changes.changes.Change(**change))
                    self.last_revision = change['revision']
        finally:
            self.polling = False

    def getRawChanges(self):
        branch = bzrlib.branch.Branch.open_containing(self.url)[0]
        if self.branch_name is FULL:
            branch_name = self.url
        elif self.branch_name is SHORT:
            branch_name = branch.nick
        else: # presumably a string or maybe None
            branch_name = self.branch_name
        changes = []
        change = generate_change(
            branch, blame_merge_author=self.blame_merge_author)
        if (self.last_revision is None or
            change['revision'] > self.last_revision):
            change['branch'] = branch_name
            change['category'] = self.category
            changes.append(change)
            if self.last_revision is not None:
                while self.last_revision + 1 < change['revision']:
                    change = generate_change(
                        branch, new_revno=change['revision']-1,
                        blame_merge_author=self.blame_merge_author)
                    change['branch'] = branch_name
                    changes.append(change)
        changes.reverse()
        return changes

    def addChange(self, change):
        d = twisted.internet.defer.Deferred()
        def _add_change():
            d.callback(
                self.parent.addChange(change))
        twisted.internet.reactor.callLater(0, _add_change)
        return d

#eof
