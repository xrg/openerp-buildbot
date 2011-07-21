# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Software Development Solution
#    Copyright (C) 2011 P. Christeas <xrg@hellug.gr>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from tools.translate import _
from osv import fields, osv
from datetime import datetime

class softdev_branch_collection(osv.osv):
    _name = 'software_dev.mirrors.branch_collection'
    
    _columns = {
        'name': fields.char('Name', size=128, required=True, select=True),
        'branch_ids': fields.one2many('software_dev.branch', 'branch_collection_id',
                string='Branches',
                help="All branches that participate in the sync. Their mapping "
                    "will also be based on each branch'es tech_code."),
        }

    # TODO: load marks for branch

softdev_branch_collection()

class software_dev_branch(osv.osv):
    _inherit = "software_dev.branch"
    
    _columns = {
        'branch_collection_id': fields.many2one('software_dev.mirrors.branch_collection',
                string="Branch collection",
                help="If set, this branch will be mirrored to other repos through that collection. "
                    "Only one collection is allowed."),
        'is_imported': fields.boolean('Imported', required=True,
                help="If set, this branch will not be polled, but instead import commits "
                    "from the other branches of the collection"),
        }

    _defaults = {
        'is_imported': False,
    }

    def _fmt_branch(self, branch_bro, fixed_commit=False):
        res = super(software_dev_branch, self)._fmt_branch(branch_bro, fixed_commit=fixed_commit)
        print "res:", res
        return res

software_dev_branch()

class softdev_commit_mapping(osv.osv):
    _name = "software_dev.mirrors.commitmap"
    _description = "Commit Map"
    _rec_name = 'mark'
    
    _columns = {
        'mark': fields.char('Mark', size=64, required=True,
                help="Fastexport mark, uniquely identifiesc commit in a branch collection"),
        'collection_id': fields.many2one('software_dev.mirrors.branch_collection',
                string="Branch Collection", required=True ),
        'commit_ids': fields.one2many('software_dev.commit', 'commitmap_id',
                string="Commits"),
        }
    
    _sql_constraints = [ ('unique_mark', 'UNIQUE(mark, collection_id)', "Marks must be unique per collection")]

softdev_commit_mapping()

class software_dev_commit(osv.osv):
    _inherit = "software_dev.commit"
    
    _columns = {
        'commitmap_id': fields.many2one('software_dev.mirrors.commitmap',
                string="Mapped commits",
                help="When this commit is exported/imported from other repos, link "
                    "to the other commits"),
        }

software_dev_commit()

#eof