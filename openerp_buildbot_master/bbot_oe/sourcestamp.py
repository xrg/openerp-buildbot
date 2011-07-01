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

from buildbot.sourcestamp import SourceStamp

class OpenObjectSourceStamp(SourceStamp):
    changes = False
    def __init__(self, branch=None, revision=None, patch=None,
                 changes=None):
        SourceStamp.__init__(self, branch=branch, revision=revision, patch=patch,
                 changes=changes)

        if self.changes:
            self.revision = self.changes[0].revision
    def canBeMergedWith(self, other):
        if self.revision != other.revision:
            return False
        return SourceStamp.canBeMergedWith(self, other)


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: