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
import binascii



def create_test_log(source, properties):
    openerp_host = properties.get('openerp_host', 'localhost')
    openerp_port = properties.get('openerp_port',8069)
    openerp_dbname = properties.get('openerp_dbname','buildbot')
    openerp_userid = properties.get('openerp_userid','admin')
    openerp_userpwd = properties.get('openerp_userpwd','a')
    change = source.changes and source.changes[0] or False
    if not change:
        return False
    openerp = buildbot_xmlrpc(host = openerp_host, port = openerp_port, dbname = openerp_dbname)
    openerp_uid = openerp.execute('common','login',  openerp.dbname, openerp_userid, openerp_userpwd)
    args = [('url','ilike',change.branch),('is_test_branch','=',False),('is_root_branch','=',False)]
    tested_branch_ids = openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.lp.branch','search',args)
    tested_branch_id = tested_branch_ids[0]

    res = {}
    res['tested_branch'] = tested_branch_id or False
    res['test_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    res['commit_date'] = datetime.fromtimestamp(change.when).strftime('%Y-%m-%d %H:%M:%S')
    lp_user_id = openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.lp.user','search', [('name','ilike',change.who)])
    if lp_user_id:
        lp_user_id = lp_user_id[0]
    else:
         lp_email = str(change.revision_id).split('-')[0]
         res_lp_user = {'name':change.who,'lp_email':lp_email}
         lp_user_id = openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.lp.user', 'create', res_lp_user)
    res['commiter_id'] =  lp_user_id
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
    ## Add patch as attachment
    if source.patch:
     for patch in source.patch or []:
        data_attach = {
            'name': str(change.revision_id)+'.patch',
            'datas':binascii.b2a_base64(str(source.patch.get(patch))),
            'datas_fname': patch,
            'description': 'Patch attachment',
            'res_model': 'buildbot.test',
            'res_id': result_id,
        }
        openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'ir.attachment', 'create', data_attach)
    return result_id

class OpenObjectBuildset(buildset.BuildSet):
    def __init__(self, builderNames, source, reason=None, bsid=None,
                 properties=None, openerp_properties={}):
        buildset.BuildSet.__init__(self, builderNames=builderNames, source=source, reason=reason, bsid=bsid, properties=properties)
        self.openerp_properties = openerp_properties
    def start(self, builders):
        res = buildset.BuildSet.start(self, builders)
        for builder in builders:
             if not hasattr(builder, 'test_ids'):
                 builder.test_ids = {}
             builder.openerp_properties = self.openerp_properties

             openerp_test_id = create_test_log(self.source, self.openerp_properties)

             if self.source.revision not in builder.test_ids:
                 builder.test_ids[self.source.revision] = openerp_test_id
        return res

class OpenObjectScheduler(Scheduler):
    def __init__(self, name, branch, treeStableTimer, builderNames,
                 fileIsImportant=None, properties={}, openerp_properties={}):
        Scheduler.__init__(self, name=name, branch=branch, treeStableTimer=treeStableTimer, builderNames=builderNames,
                 fileIsImportant=fileIsImportant, properties=properties)
        self.openerp_properties = openerp_properties
    def fireTimer(self):
        # clear out our state
        self.timer = None
        self.nextBuildTime = None
        changes = self.importantChanges + self.unimportantChanges
        self.importantChanges = []
        self.unimportantChanges = []
        # create a BuildSet, submit it to the BuildMaster
        for change in changes:
            bs = OpenObjectBuildset(self.builderNames,
                                   OpenObjectSourceStamp(changes=[change]),
                                   properties=self.properties,
                                   openerp_properties=self.openerp_properties)
            self.submitBuildSet(bs)


class OpenObjectAnyBranchScheduler(AnyBranchScheduler):
    schedulerFactory = OpenObjectScheduler

    def __init__(self, name, branches, treeStableTimer, builderNames,
                 fileIsImportant=None, properties={}):
        AnyBranchScheduler.__init__(self, name=name, branches=branches, treeStableTimer=treeStableTimer, builderNames=builderNames,
                 fileIsImportant=fileIsImportant, properties=properties)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
