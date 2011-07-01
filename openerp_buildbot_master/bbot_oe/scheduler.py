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

from buildbot.scheduler import AnyBranchScheduler,Scheduler
from sourcestamp import OpenObjectSourceStamp
# from buildbot import buildset
from datetime import datetime

raise ImportError("Don't use me!")

class OpenObjectScheduler(Scheduler):
    def __init__(self, name, **kwargs):
        self.unimportantChanges = []
        self.keeper = kwargs.pop('keeper', None)
        Scheduler.__init__(self, name=name, **kwargs)
        

class OpenObjectAnyBranchScheduler(AnyBranchScheduler):
    schedulerFactory = OpenObjectScheduler

    def __init__(self, name, branches, treeStableTimer, builderNames,
                 fileIsImportant=None, properties={}):
        AnyBranchScheduler.__init__(self, name=name, branches=branches, treeStableTimer=treeStableTimer, builderNames=builderNames,
                 fileIsImportant=fileIsImportant, properties=properties)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
