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
import warnings

class OpenObjectChange(Change):
    def __init__(self, **kwargs):
        warnings.warn("You are using deprecated OpenObjectChange.", 
                DeprecationWarning, stacklevel=3)
        self.branch_id = kwargs.pop('branch_id')
        self.filesb = kwargs.pop('filesb',[])
        self.hash = kwargs.pop('hash', None)
        self.number = kwargs.pop('id', None)
        self.parent_id = kwargs.pop('parent_id', None)
        self.parent_revno = kwargs.pop('parent_revno', None)
        self.authors = kwargs.pop('authors', [])
        files = kwargs.pop('files', False)
        if not files:
            files = [ x['filename'] for x in self.filesb ]
        who = kwargs.pop('who', '')
        comments = kwargs.pop('comments', '')
        # self.all_modules = list(set([ x.split('/')[0] for x in files]))
        Change.__init__(self, who, files, comments, **kwargs)

    def asDict(self):
        res = Change.asDict(self)
        res['branch_id'] = self.branch_id
        if self.hash:
            res['hash'] = self.hash
        if self.filesb:
            res['filesb'] = self.filesb
        res['authors'] = self.authors
        if (not res.get('revlink',False)) and self.branch and self.revision:
            if self.branch.startswith('lp:'):
                res['revlink'] = "http://bazaar.launchpad.net/%s/revision/%s" % \
                                (self.branch[3:], self.revision)
        return res


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
