# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2010 OpenERP SA. (http://www.openerp.com)
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
import time


    
class software_buildbot(osv.osv):
    def get_polled_branches(self, cr, uid, ids, context=None):
        """Helper for the buildbot, list all the repos+branches it needs to poll.
        
        Since it is difficult to write RPC calls for browse(), we'd better return
        a very easy dictionary of values for the buildbot, that may configure
        its pollers.
        @return A list of dicts, with branch (or repo) information
        """
        
        ctx = context or {}
        
        ret = []
        found_branches = []   # ids of branches we have made so far

        bseries_obj = self.pool.get('software_dev.buildseries')
        series_ids = bseries_obj.search(cr, uid, [('builder_id','in',ids), ('is_build','=',True), ('is_template', '=', False)], context=ctx)  # :(

        for bser in bseries_obj.browse(cr, uid, series_ids, context=ctx):
            dret = {}
            dret['branch_id'] = bser.id
            dret['branch_name'] = bser.name
            dret['rtype'] = 'bzr'
            dret['branch_path'] = bser.target_path
            dret['fetch_url'] = bser.branch_url
            dret['poll_interval'] = bser.poll_interval or 600
            if bser.group_id:
                dret['group'] = bser.group_id.name
            ret.append(dret)

        return ret


software_buildbot()

class propertyMix(object):
    pass


# Tests...
_target_paths = [('server', 'Server'), ('addons', 'Addons'), ('extra_addons', 'Extra addons')]
class software_buildseries(propertyMix, osv.osv):
    """ A series is a setup of package+test+branch+result+dependencies+bot scenaria
    """
    _name = 'software_dev.buildseries'
    _description = 'Build Series'
    

    _columns = {
        
        'is_build': fields.boolean('Perform test', required=True,
                help="If checked, this branch will be built. Otherwise, just followed"),
        'target_path': fields.selection(_target_paths, 'Branch Type' ),
        'branch_url': fields.char('Branch Url', size=512, required=True,
                help="The place of the branch in Launchpad (only).",
                ),
        
        'poll_interval': fields.integer('Polling interval',
                help="Poll the upstream repository every N seconds for changes"),
        'test_ids': fields.one2many('software_dev.teststep', 'test_id', 'Test Steps', 
                help="The test steps to perform."),
        #'dep_branch_ids': fields.many2many('software_dev.buildseries', 
        #    'software_dev_branch_dep_rel', 'end_branch_id', 'dep_branch_id',
        #    string="Dependencies",
        #    help="Branches that are built along with this branch"),
        
        'is_template': fields.boolean('Template', required=True,
                help="If checked, will just be a template branch for auto-scanned ones."),
    }

    _defaults = {
        'is_distinct': False,
        'is_build': True,
        'sequence': 10,
        'is_template': False,
    }

software_buildseries()


commit_types = [ ('reg', 'Regular'), ('merge', 'Merge'), ('single', 'Standalone'), 
            ]

change_types = [ ('a', 'Add'), ('m', 'Modify'), ('d', 'Delete'), 
                ('c', 'Copy'), ('r', 'Rename') ]

class software_buildseries2(osv.osv):
    _inherit = 'software_dev.buildseries'
    
    _columns = {
        'latest_commit_id': fields.many2one('software_dev.commit', string='Latest commit'),
        }



#eof
