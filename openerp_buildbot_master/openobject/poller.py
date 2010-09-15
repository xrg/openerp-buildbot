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
import re

import bzr_poller

# -----------------
class OldBzrPoller(service.MultiService, util.ComparableMixin):
    """This source will poll a Bzr repository for changes and submit them to
    the change master."""
    implements(interfaces.IChangeSource)

    compare_attrs = ["location", "pollinterval"]


    parent = None # filled in when we're added
    last_change = None
    loop = None
    working = False

    def __init__(self, location, pollinterval=60*60, callback=False, openerp_properties = {}):
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
        self.openerp_properties = openerp_properties

    def describe(self):
        return "BzrPoller watching %s" % self.location

    def poll(self):
        try:
            self._poll()
        except Exception, e:
            log.err("Cannot poll: %s" % e)

    def _poll(self):
        log.msg("BzrPoller polling: %s"%(self.location))
        # this is subclass of bzrlib.branch.Branch
        current_revision = self.branch.revno()
        log.msg("Current revision: %s" % current_revision)
        if not self.last_revno:
            openerp_host = self.openerp_properties.get('openerp_host', 'localhost')
            openerp_port = self.openerp_properties.get('openerp_port',8069)
            openerp_dbname = self.openerp_properties.get('openerp_dbname','buildbot')
            openerp_userid = self.openerp_properties.get('openerp_userid','admin')
            openerp_userpwd = self.openerp_properties.get('openerp_userpwd','a')

            openerp = buildbot_xmlrpc(host = openerp_host, port = openerp_port, dbname = openerp_dbname)
            openerp_uid = openerp.execute('common','login',  openerp.dbname, openerp_userid, openerp_userpwd)

            args = [('url','ilike',self.location),('is_test_branch','=',False),('is_root_branch','=',False)]
            tested_branch_ids = openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.lp.branch','search', args)
            tested_branch_id = tested_branch_ids[0]

            tested_branch_data = openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.lp.branch','read',tested_branch_id,['latest_rev_no'])

            self.last_revno = int(tested_branch_data['latest_rev_no'])
        # NOTE: b.revision_history() does network IO, and is blocking.
        log.msg("Get revision history..")
        revisions = self.branch.revision_history()[self.last_revno:] # each is an id string
        log.msg("Finished revision history")
        changes = []
        for r in revisions:
            rev = self.branch.repository.get_revision(r)
            revision_id = rev.revision_id
            # bzrlib.revision.Revision
            who = rev.committer
            comments = rev.message
            when = rev.timestamp
            # rev.timezone, interesting. Not sure it's used.
            revision_delta = self.branch.repository.get_revision_delta(r)
            revision= self.branch.revision_id_to_revno(r) #b.get_rev_id()
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

# ------------------

html_tmpl = """
<p>Changed by : <b>%(who)s</b><br />
Changed at : <b>%(at)s</b><br />
%(branch)s
%(revision_id)s
Revision No: %(revision)s
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
    def __init__(self, **kwargs):
        self.branch_id = kwargs.pop('branch_id')
        self.filesb = kwargs.pop('filesb',[])
        self.hash = kwargs.pop('hash', None)
        self.number = kwargs.pop('id', None)
        self.authors = kwargs.pop('authors', [])
        files = kwargs.pop('files', False)
        if not files:
            files = [ x['filename'] for x in self.filesb ]
        who = kwargs.pop('who', '')
        comments = kwargs.pop('comments', '')
        # self.all_modules = list(set([ x.split('/')[0] for x in files]))
        Change.__init__(self, who, files, comments, **kwargs)

    def allModules(self, repo_expr):
        """ Return the list of all the modules that must have changed
        """
        rx = re.compile(repo_expr)
        ret = []
        for fi in self.filesb:
            m = rx.match(fi['filename'])
            if m:
                ret.append(m.group(1))
        return ret

    def asDict(self):
        res = Change.asDict(self)
        res['branch_id'] = self.branch_id
        if self.hash:
            res['hash'] = self.hash
        if self.filesb:
            res['filesb'] = self.filesb
        res['authors'] = self.authors
        return res

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
            # Decode source url to a web-vcs interface
            if self.branch.startswith('https://code.launchpad.net/'):
                branch_link = 'http://bazaar.launchpad.net/%s/revision/%s' % \
                    (self.branch[27:], str(revision))
            elif self.branch.startswith('lp:'):
                branch_link = 'http://bazaar.launchpad.net/%s/revision/%s' % \
                    (self.branch[3:], str(revision))
            # elif  some other repo...
            
            if branch_link:
                branch = "Branch : <a href='%s'>%s</a><br/>\n" % (branch_link, self.branch)
            else:
                branch = '<!-- no web for %s -->'  % self.branch

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
        
        
class BzrPoller(bzr_poller.BzrPoller):
    _change_class = OpenObjectChange
    
    def __init__(self, url, poll_interval=10*60, blame_merge_author=False,
                    branch_name=None, branch_id=None, category=None, keeper=None):
        bzr_poller.BzrPoller.__init__(self, url=url, poll_interval=poll_interval,
                    blame_merge_author=blame_merge_author,
                    branch_id=branch_id,
                    branch_name=branch_name, category=category)
        self.keeper = keeper


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
