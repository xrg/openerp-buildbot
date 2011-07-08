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

from twisted.python import log
from buildbot.schedulers.filter import ChangeFilter

class ChangeFilter_OE(ChangeFilter):
    def __init__(self, branch_id, **kwargs):
        self.branch_id = branch_id
        ChangeFilter.__init__(self, **kwargs)

    def filter_change(self, change):
        #print "Trying to filter %r with %r" % (change, self)

        if 'branch_id' in change.properties:
            if change.properties['branch_id'] != self.branch_id:
                #print "Branches don't match:", change.properties['branch_id'], self.branch_id
                return False
        else:
            log.msg("strange, change doesn't have 'branch_id' property!")

        return ChangeFilter.filter_change(self, change)

# eof
