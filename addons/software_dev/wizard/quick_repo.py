# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2011 P. Christeas <xrg@hellug.gr>
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

from osv import osv, fields
from ..software_builds import schedulers

class quick_add_repo(osv.osv_memory):
    """Quickly add a repository, branch and build series
    """
    
    _name = 'software_dev.wizard.quick_add_repo'
    _description = 'Quick add repository'
    
    _columns = {
        # repo:
        "repohost": fields.many2one('software_dev.repohost', "Host", required=True),
        'base_url': fields.char('Location', size=1024,
                help='Location of repository, according to repohost'),
        'proxy_location': fields.char('Proxy location', size=1024,
                help="A local path where this repository is replicated, for caching"),
        'slave_proxy_url': fields.char('Slave proxy url', size=1024,
                help="The url from which a slave bot can fetch the proxied repository content"),
        'local_prefix': fields.char('Local prefix', size=64,
                help="If the local proxy is shared among repos, prefix branch names with this, to avoid conflicts"),
        
        # branch:
        'branch_name': fields.char('Branch Name', required=True, size=64),
        'tech_code': fields.char('Branch Tech name', size=128, select=1),
        'sub_url': fields.char('Branch URL', size=1024, required=True,
                    help="Location of branch, sometimes relative to repository"),
        
        # package
        'package_name': fields.char('Package Name', required=True, size=64),
        'package_tech_name': fields.char('Technical Name', required=True, size=64,
                help="A short, technical name of the package, to be used in paths etc"),
        
        # series
        'group_id': fields.many2one('software_dev.buildgroup', 'Group', ),
        'scheduler': fields.selection(schedulers, 'Scheduler', required=True),
        'builder_id': fields.many2one('software_dev.buildbot',
                string='BuildBot', required=True,
                help="Machine that will build this series"),
        'test_id': fields.many2one('software_dev.test', 'Test', 
                help="The test to perform. Steps are configured in the test."),


        }

    _defaults = {
        }
        
    def onchange_package_name(self, cr, uid, ids, package_name, context=None):
        return {'values': { } }
        
    def create_records(self, cr, uid, ids, context=None):
        """Main operation, create all records from this wizard
        """
        pack_obj = self.pool.get('software_dev.package')
        repo_obj = self.pool.get('software_dev.repo')
        bseries_obj = self.pool.get('software_dev.buildseries')
        branch_obj = self.pool.get('software_dev.branch')
        ret_ids = []
        bbot_ids = set()
        for bro in self.browse(cr, uid, ids, context=context):
            # step 1: create repo, branch
            repo_id = repo_obj.create(cr, uid, {
                    'name': bro.package_name,
                    'base_url': bro.base_url,
                    
                    'host_id': bro.repohost.id,
                    'local_prefix': bro.local_prefix,
                    'proxy_location': bro.proxy_location,
                    'rtype': bro.repohost.rtype,
                    'slave_proxy_url': bro.slave_proxy_url,
                    },
                    context=context)

            # step 1.1: create branch
            branch_id = branch_obj.create(cr, uid, {
                    'repo_id': repo_id,
                    'name': bro.branch_name,
                    'sub_url': bro.sub_url,
                    'tech_code': bro.tech_code,
                    },
                    context=context)

            # step 2: create package+component
            package_id = pack_obj.create(cr, uid, {
                    'name': bro.package_name,
                    'component_ids': [(0, 0,{
                        'name': '%s Main' % bro.package_name,
                        'tech_code': '%s_main' % bro.package_tech_name,
                        'branch_id': branch_id,
                        }),],
                    },
                    context=context)

            # step 3: create build series
            bser_id = bseries_obj.create(cr, uid, {
                    'name': bro.package_name,
                    'branch_id': branch_id,
                    'builder_id': bro.builder_id.id,
                    'group_id': bro.group_id.id,
                    'package_id': package_id,
                    'scheduler': bro.scheduler,
                    'test_id': bro.test_id.id,
                    },
                    context=context)
            ret_ids.append(bser_id)
            bbot_ids.add(bro.builder_id.id)
        
        try:
            self.pool.get('software_dev.buildbot').trigger_reconfig(cr, uid, 
                    list(bbot_ids), kind='all', context=context)
        except Exception:
            pass
        return {'type': 'ir.actions.act_window_close'}

quick_add_repo()

#eof