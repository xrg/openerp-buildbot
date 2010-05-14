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
        self.branch = Branch.open_containing(self.location)[0]
        # bzrlib.trace.enable_default_logging()
        timer = internet.TimerService(pollinterval, self.poll)
        timer.setServiceParent(self)

    def describe(self):
        return "BzrPoller watching %s" % self.location
        
    def poll(self):
        log.msg("BzrPoller polling")
        b = self.branch
        # this is subclass of bzrlib.branch.Branch
        current_revision = b.revno()
        if not self.last_revno:
            self.last_revno = current_revision - 1
        # NOTE: b.revision_history() does network IO, and is blocking.
        revisions = b.revision_history()[self.last_revno:] # each is an id string
        changes = []
        for r in revisions:
            rev = b.repository.get_revision(r)
            revision_id = rev.revision_id
            # bzrlib.revision.Revision
            who = rev.committer
            comments = rev.message
            when = rev.timestamp
            # rev.timezone, interesting. Not sure it's used.
            revision_delta = b.repository.get_revision_delta(r)            
            revision= b.revision_id_to_revno(r) #b.get_rev_id()
            branch= self.location #b.get_master_branch()
            c = OpenObjectChange(  
                                   who = rev.committer,
                                   revision_delta = revision_delta,
                                   revision_id = revision_id,
                                   comments = rev.message,
                                   when = rev.timestamp,
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

html_tmpl = """
<p>Changed by : <b>%(who)s</b><br />
Changed at : <b>%(at)s</b><br />
%(branch)s
%(revision_id)s
Revision No:%(revision)s
</p>

%(files_added)s
%(files_modified)s
%(files_renamed)s
%(files_removed)s


Comments : %(comments)s

<br />
"""
from twisted.web import html
class OpenObjectChange(Change):
    def __init__(self, who, revision_delta, revision_id, comments, files=[],  isdir=0, links=[],
                 revision=None, when=None, branch=None):
        self.files_added = [f[0] for f in revision_delta.added]
        self.files_modified = [f[0] for f in revision_delta.modified]
        self.files_renamed = [(f[0],f[1]) for f in revision_delta.renamed]
        self.files_removed = [f[0] for f in revision_delta.removed]
        self.ch = revision_delta
        self.revision_id = revision_id
        files =  self.files_added + self.files_modified + [f[1] for f in self.files_renamed] + self.files_removed
        Change.__init__(self, who=who, files=files, comments=comments, isdir=isdir, links=links,revision=revision, when=when, branch=branch)
        
    def asHTML(self):
        files_added = []
        files_modified = []
        files_renamed = []
        files_removed = [] 
        files_added_lbl = ''
        files_modified_lbl = ''
        files_renamed_lbl = ''
        files_removed_lbl = ''
        
        revision_id = ''
        if self.revision_id:
            revision_id = "Revision ID: <b>%s</b><br />\n" % self.revision_id
        
        revision = ''
        if self.revision:
            revision = self.revision            
        
            
        branch = ""
        branch_link = ''
        if self.branch:
            i = self.branch.index('launchpad')
            branch_link = 'https://bazaar.' + self.branch[i:] + '/revision/' + str(revision) + '#'
            branch = "Branch : <a href='%s'>%s</a><br />\n" % (self.branch,self.branch)
            
        if self.files_added:
            files_added_lbl = "Added files : \n"
            for file in self.files_added:
                file_link = branch_link + file
                files_added.append("<a href='%s'>%s</a>" % (file_link,file))
        if self.files_modified:
            files_modified_lbl = "Modified files : \n"
            for file in self.files_modified:
                file_link = branch_link + file
                files_modified.append("<a href='%s'>%s</a>" % (file_link, file))
        if self.files_renamed:
            files_renamed_lbl = "Renamed files : \n"
            for file in self.files_renamed:
                old_file_link = branch_link + file[0]
                file_link = branch_link + file[1]
                files_renamed.append("<a href='%s'>%s</a> => <a href='%s'>%s</a>" % (old_file_link, file[0], file_link,file[1]))
        if self.files_removed:
            files_removed_lbl = "Removed files : \n"
            for file in self.files_removed:
                file_link = branch_link + file
                files_removed.append("<a href='%s'>%s</a>" % (file_link,file))
        
        kwargs = { 'who'     : html.escape(self.who),
                   'at'      : self.getTime(),
                   'files_added'   : files_added_lbl + html.UL(files_added) + '\n',
                   'files_modified' : files_modified_lbl + html.UL(files_modified) + '\n',
                   'files_renamed' : files_renamed_lbl + html.UL(files_renamed) + '\n',
                   'files_removed' : files_removed_lbl + html.UL(files_removed) + '\n',
                   'revision': revision,
                   'revision_id': revision_id,
                   'branch'  : branch,
                   'comments': html.PRE(self.comments) }
        return html_tmpl % kwargs
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
