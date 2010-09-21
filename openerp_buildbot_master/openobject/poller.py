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
