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
from buildbot import buildset
from xmlrpc import buildbot_xmlrpc
from datetime import datetime

openerp_host = 'localhost'
openerp_port = 8069
openerp_dbname = 'buildbot'

def create_test_log(change):
    openerp = buildbot_xmlrpc(host = openerp_host, port = openerp_port, dbname = openerp_dbname)
    openerp_uid = openerp.execute('common','login',  openerp.dbname, openerp_userid, openerp_userpwd)
    tested_branch_id = openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.lp.branch','search',[('name','ilike',change.branch)])
    res = {}
    res['name'] = "Tested for branch: %s"%change.branch
    res['tested_branch'] = tested_branch_id or False
    res['test_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    res['commit_date'] = datetime.fromtimestamp(change.when).strftime('%Y-%m-%d %H:%M:%S')
    res['commit_comment'] = str(change.comments)
    res['commit_rev_id'] = str(change.revision_id)
    res['commit_rev_no'] = int(change.revision)
    res['new_files'] = '\n'.join(change.files_added)
    res['update_files'] = '\n'.join(change.files_modified)
    renamed_files = ['%s --> %s'%(f[0], f[1]) for f in change.files_renamed]
    res['rename_files'] = '\n'.join(renamed_files)
    res['remove_files'] = '\n'.join(change.files_removed)

    result_id = openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.test', 'create', res)
    openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.lp.branch', 'write',
                    [tested_branch_id],{'lastest_rev_no':change.revision,
                                        'lastest_rev_id':change.revision_id})
    return result_id

class OpenObjectScheduler(Scheduler):
    def __init__(self, name, branch, treeStableTimer, builderNames,
                 fileIsImportant=None, properties={}):
        Scheduler.__init__(self, name=name, branch=branch, treeStableTimer=treeStableTimer, builderNames=builderNames,
                 fileIsImportant=fileIsImportant, properties=properties)
    def fireTimer(self):
        # clear out our state
        self.timer = None
        self.nextBuildTime = None
        changes = self.importantChanges + self.unimportantChanges
        self.importantChanges = []
        self.unimportantChanges = []
        # create a BuildSet, submit it to the BuildMaster
        for change in changes:
            bs = buildset.BuildSet(self.builderNames,
                                   OpenObjectSourceStamp(changes=[change]),
                                   properties=self.properties)
            bs.test_id = create_test_log(change)
            self.submitBuildSet(bs)


class OpenObjectAnyBranchScheduler(AnyBranchScheduler):
    schedulerFactory = OpenObjectScheduler

    def __init__(self, name, branches, treeStableTimer, builderNames,
                 fileIsImportant=None, properties={}):
        AnyBranchScheduler.__init__(self, name=name, branches=branches, treeStableTimer=treeStableTimer, builderNames=builderNames,
                 fileIsImportant=fileIsImportant, properties=properties)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: