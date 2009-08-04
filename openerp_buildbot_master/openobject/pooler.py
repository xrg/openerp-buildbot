# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>). All Rights Reserved
#    $Id$
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
from zope.interface import implements
from twisted.python import log
from twisted.application import service, internet

from buildbot import util, interfaces
from buildbot.changes.changes import Change

from bzrlib.branch import Branch
import bzrlib

class BzrPoller(service.MultiService, util.ComparableMixin):
    """This source will poll a Bzr repository for changes and submit them to
    the change master."""
    implements(interfaces.IChangeSource)

    compare_attrs = ["location", "pollinterval"]


    parent = None # filled in when we're added
    last_change = None
    loop = None
    working = False

    def __init__(self, location, pollinterval=60*60, callback=False):
        """
        @type  location: string
        @param location: the URL of the branch that this poller should watch.
                         This is typically an http: or sftp: URL.

        @type  pollinterval: int
        @param pollinterval: interval in seconds between polls. The default
                             is 3600 seconds (1 hour). Smaller values
                             decrease the latency between the time a change
                             is recorded and the time the buildbot notices
                             it, but it also increases the system load.
        """
        service.MultiService.__init__(self)

        self.location = location
        self.last_revno = 0
        self.pollinterval = pollinterval
        self.overrun_counter = 0
        self.callback = callback
        timer = internet.TimerService(pollinterval, self.poll)
        timer.setServiceParent(self)

    def describe(self):
        return "BzrPoller watching %s" % self.location

    def poll(self):
        log.msg("BzrPoller polling")
        b = Branch.open_containing(self.location)[0]
        bzrlib.trace.enable_default_logging()
        # this is subclass of bzrlib.branch.Branch
        current_revision = b.revno()
        if not self.last_revno:
            self.last_revno = current_revision #- 1
        # NOTE: b.revision_history() does network IO, and is blocking.
        revisions = b.revision_history()[self.last_revno:] # each is an id string
        changes = []
        for r in revisions:
            rev = b.repository.get_revision(r)
            # bzrlib.revision.Revision
            who = rev.committer
            comments = rev.message
            when = rev.timestamp
            # rev.timezone, interesting. Not sure it's used.

            d = b.repository.get_revision_delta(r)
            # this is a delta.TreeDelta
            files = ([f[0] for f in d.added] +
                     [f[0] for f in d.removed] +
                     [f[1] for f in d.renamed] +
                     [f[0] for f in d.modified]
                     )
            revision= r #b.revision_id_to_revno(r) #b.get_rev_id()
            branch= self.location #b.get_master_branch()
            c = Change(who=rev.committer,
                       files=files,
                       comments=rev.message,
                       when=rev.timestamp,
                       revision = revision,
                       branch = branch
                       )
            changes.append(c)
        self.last_revno = current_revision
        if self.callback:
            self.callback(self.location,changes)
        for c in changes:
            self.parent.addChange(c)
        log.msg("BzrPoller finished polling, %d changes found" % len(changes))

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
