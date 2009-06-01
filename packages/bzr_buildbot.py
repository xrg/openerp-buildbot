# -*- test-case-name: buildbot.test.test_bzrpoller -*-

from zope.interface import implements
from twisted.python import log
from twisted.application import service, internet

from buildbot import util, interfaces
from buildbot.changes.changes import Change

from bzrlib.branch import Branch

class BzrPoller(service.MultiService, util.ComparableMixin):
    """This source will poll a Bzr repository for changes and submit them to
    the change master."""
    implements(interfaces.IChangeSource)

    compare_attrs = ["location", "pollinterval"]
                     

    parent = None # filled in when we're added
    last_change = None
    loop = None
    working = False

    def __init__(self, location, pollinterval=10*60):
        """
        @type  location: string
        @param location: the URL of the branch that this poller should watch.
                         This is typically an http: or sftp: URL.

        @type  pollinterval: int
        @param pollinterval: interval in seconds between polls. The default
                             is 600 seconds (10 minutes). Smaller values
                             decrease the latency between the time a change
                             is recorded and the time the buildbot notices
                             it, but it also increases the system load.
        """
	print "in poller..........",location,pollinterval
        service.MultiService.__init__(self)

        self.location = location

        self.pollinterval = pollinterval
        self.overrun_counter = 0
        timer = internet.TimerService(pollinterval, self.poll)
        timer.setServiceParent(self)

    def describe(self):
	print "in describe....in poller-"
        return "BzrPoller watching %s" % self.location

    def poll(self):
	print "in poll....in poller----"
        log.msg("BzrPoller polling")
        # location="http://bazaar-vcs.org/bzr/bzr.dev"
        b = Branch.open_containing(self.url)[0]
        # this is subclass of bzrlib.branch.Branch
        current_revision = b.revno()
        # NOTE: b.revision_history() does network IO, and is blocking.
        revisions = b.revision_history()[last_revno:] # each is an id string
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

            # revision= ?
            # branch= ?
            c = Change(who=rev.committer,
                       files=files,
                       comments=rev.message,
                       when=rev.timestamp,
                       )
            changes.append(c)
        for c in changes:
            self.parent.addChange(c)
        log.msg("BzrPoller finished polling, %d changes found" % len(changes))
