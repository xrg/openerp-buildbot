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

class software_buildbot(osv.osv):
    _name = 'software_dev.buildbot'
    _inherits = { 'software_dev.builder': 'builder_id' }
    
    _columns = {
        'builder_id': fields.many2one('software_dev.builder', 'Builder', required=True, readonly=True),
        'tech_code': fields.char('Code', size=64, required=True, select=1),
        'attribute_ids': fields.one2many('software_dev.battr', 'bbot_id', 'Attributes'),
    }

    _sql_constraints = [ ('code_uniq', 'UNIQUE(tech_code)', 'The tech code must be unique.'), ]
    
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
        
        builder_ids = []
        for bbot_id in self.browse(cr, uid, ids, context=ctx):
            builder_ids.append(bbot_id.builder_id.id)
        
        builder_ids = list(set(builder_ids))
        
        bseries_obj = self.pool.get('software_dev.buildseries')
        series_ids = bseries_obj.search(cr, uid, [('builder_id','in',builder_ids)], context=ctx)  # :(

        def _fmt_branch(branch_bro, fixed_commit=False):
            """Format the branch info into a dictionary
            """
            dret = {}
            dret['rtype'] = branch_bro.repo_id.rtype
            dret['branch_path'] = branch_bro.tech_code or \
                    (branch_bro.sub_url.replace('/','_'))
            dret['fetch_url'] = branch_bro.fetch_url
            dret['poll_interval'] = branch_bro.poll_interval
            
            if branch_bro.repo_id.proxy_location:
                dret['mirrored'] = True
                dret['repo_base'] = branch_bro.repo_id.proxy_location
            
            return dret

        for bser in bseries_obj.browse(cr, uid, series_ids, context=ctx):
            if bser.branch_id.id not in found_branches:
                ret.append(_fmt_branch(bser.branch_id))
                found_branches.append(bser.branch_id.id)
        
            for comp in bser.package_id.component_ids:
                if comp.update_rev and comp.branch_id.id not in found_branches:
                    ret.append(_fmt_branch(comp.branch_id, fixed_commit = comp.commit_id))
                    found_branches.append(comp.branch_id.id)
        
        return ret

    def get_builders(self, cr, uid, ids, context=None):
        """ Return a complete dict with the builders for this bot
        
        Sample:
           name: name
           slavename
           build_dir
           branch_url
           tstimer
           steps [ (name, { props}) ]
        """
        ret = []
        return ret

software_buildbot()

class software_battr(osv.osv):
    """ Build bot attribute
    
        Raw name-value pairs that are fed to the buildbot
    """
    _name = 'software_dev.battr'
    _columns = {
        'bbot_id': fields.many2one('software_dev.buildbot', 'BuildBot', required=True, select=1),
        'name': fields.char('Name', size=64, required=True, select=1),
        'value': fields.char('Value', size=256),
        }

software_battr()

class software_bbot_slave(osv.osv):
    """ A buildbot slave
    """
    _name = 'software_dev.bbslave'
    
    _columns = {
        'bbot_id': fields.many2one('software_dev.buildbot', 'Master bot', required=True),
        'name': fields.char('Name', size=64, required=True, select=1),
        'tech_code': fields.char('Code', size=64, required=True, select=1),
        'password': fields.char('Secret', size=128, required=True,
                    help="The secret code used by the slave to connect to the master"),
        #'property_ids': fields.one2many('software_dev.bsattr', 'bslave_id', 'Properties'),
    }

    _sql_constraints = [ ('code_uniq', 'UNIQUE(tech_code)', 'The tech code must be unique.'), ]

software_bbot_slave()
