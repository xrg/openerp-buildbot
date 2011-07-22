# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2010 OpenERP SA. (http://www.openerp.com)
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

# from tools.translate import _
from osv import fields, osv
from properties import propertyMix
import netsvc

class software_buildbot(osv.osv):
    _name = 'software_dev.buildbot'
    _inherits = { 'software_dev.builder': 'builder_id' }

    _columns = {
        'builder_id': fields.many2one('software_dev.builder', 'Builder', required=True, readonly=True, ondelete='cascade'),
        'tech_code': fields.char('Code', size=64, required=True, select=1),
        'attribute_ids': fields.one2many('software_dev.battr', 'bbot_id', 'Attributes'),
        'http_port': fields.integer('Http port', help="Port to run the buildbot status server at"),
        'http_url': fields.char('Http URL', size=128, help="Base url of our buildbot server, for formatting the full link to results."),
        'slave_ids': fields.one2many('software_dev.bbslave', 'bbot_id', 'Test Steps',
                help="The test steps to perform."),

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
        bseries_obj = self.pool.get('software_dev.buildseries')
        branch_obj = self.pool.get('software_dev.branch')
        commit_obj = self.pool.get('software_dev.commit')

        def append_ret(new_branch, branch_id):
            group_fields = ('repo_id', 'rtype', 'workdir', 'fetch_url', 'remote_name')
            found_branches.append(branch_id)
            if new_branch['rtype'] == 'git' and 'repo_id' in new_branch:
                for old in ret:
                    if old.get('rtype') == 'git' \
                            and old.get('repo_id') == new_branch['repo_id']:
                        if old.get('fetch_url') != new_branch.get('fetch_url'):
                            continue
                        assert old.get('workdir') == new_branch['workdir']
                        assert old.get('remote_name') == new_branch.get('remote_name')
                        if old.get('mode', 'branch') != 'multibranch':
                            old_branch = old.copy()
                            for fld in group_fields:
                                old_branch.pop(fld, None)
                            for fld in ('local_branch', 'branch_id', 'branch_path'):
                                old.pop(fld, None)
                            old['mode'] = 'multibranch'
                            old['branch_specs'] = [ old_branch,]
                        
                        for fld in group_fields:
                            new_branch.pop(fld, None)
                        poll_intvl = new_branch.pop('poll_interval', None)
                        if poll_intvl and poll_intvl < old.get('poll_interval', 3600):
                            old['poll_interval'] = poll_intvl
                        old['branch_specs'].append(new_branch)
                        return
            
            ret.append(new_branch)

        for bser in bseries_obj.browse(cr, uid, [('builder_id','in',ids)], context=ctx):
            if bser.branch_id.id not in found_branches:
                append_ret(branch_obj._fmt_branch(bser.branch_id), bser.branch_id.id)

            for comp in bser.package_id.component_ids:
                if comp.update_rev and comp.branch_id.id not in found_branches:
                    append_ret(branch_obj._fmt_branch(comp.branch_id, fixed_commit=comp.commit_id), \
                                comp.branch_id.id)


        for r in ret:
            # For each branch, if there are no commits, enable the 'allHistory'
            # mode which will fetch all previous commits.
            if r.get('mode') == 'multibranch':
                for bs in r['branch_specs']:
                    count_commits = commit_obj.search(cr, uid,
                            [('branch_id', '=', bs['branch_id'])], count=True)
                    if not count_commits:
                        r['allHistory'] = True
                        break
            else:
                count_commits = commit_obj.search(cr, uid,
                            [('branch_id', '=', r['branch_id'])], count=True)
                if not count_commits:
                    r['allHistory'] = True

        return ret

    def get_builders(self, cr, uid, ids, context=None):
        """ Return a complete dict with the builders for this bot

        @return a list of dictionaries, with the keys mentioned below
        
        Output keys:
        
           name:         builder name
           properties:   A dictionary of extra values for the builder
           slavename:    name of slave to attach
           branch_name:  used in change filter
           branch_id:    reference to branch whose changes will trigger builds
           tstimer:      treeStableTimer value, optional
           
           steps:        steps to perform, a list: [ (class-name, { props}) ]
        """
        ret = []
        bs_obj = self.pool.get('software_dev.buildseries')
        for bid in bs_obj.browse(cr, uid, [('builder_id', 'in', ids)], context=context):
            r = bid.get_builders(context=context)
            ret += r
        return ret

    def get_conf_timestamp(self, cr, uid, ids, context=None):
        """ Retrieve the max timestamp of configuration changes.

        This should be the maximum of all data that is present on
        a buildbot configuration, so that we know if we need to reload
        the buildbot
        """
        bs_obj = self.pool.get('software_dev.buildseries')
        qry = 'SELECT MAX(GREATEST(write_date, create_date)) FROM "%s" WHERE builder_id = ANY(%%s);' %\
                    (bs_obj._table)
        cr.execute(qry, (ids,))
        res = cr.fetchone()
        # TODO: look at atrributes, properties, buildbot data etc.
        if not (res and res[0]):
            return False
        return res

    def trigger_reconfig(self, cr, uid, ids, kind='all', context=None):
        """Trigger reconfiguration of buildbots
        """

        # So far, we issue an all-buildbots, all-kind reconfig
        netsvc.ExportService.getService('subscription').publish(cr.dbname, '%s:all-reconfig' % self._name)
        return True

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
        'max_builds': fields.integer('Max Builds', required=True,
                    help="Number of maximum builds to run in parallel"),
        'dedicated': fields.boolean('Dedicated', required=True,
                    help="If set, this slave will only receive builds whose series " \
                        "explicitly list it. Otherwise, it could claim builds from " \
                        "any series")
        #'property_ids': fields.one2many('software_dev.bsattr', 'bslave_id', 'Properties'),
    }

    _sql_constraints = [ ('code_uniq', 'UNIQUE(tech_code)', 'The tech code must be unique.'), ]
    
    _defaults = {
        'max_builds': 2,
        'dedicated': False,
    }

software_bbot_slave()

class software_buildscheduler(propertyMix, osv.osv):
    _name = 'software_dev.buildscheduler'
    _description = 'Build Scheduler'
    _columns = {
        'name': fields.char('Name', required=True, size=256, select=1),
        'class_name': fields.char('Class name', size=256, required=True),
        'state_dic': fields.text('State'),
        'change_ids': fields.one2many('software_dev.sched_change', 'sched_id', 'Changes'),
    }

    _sql_constraints = [( 'name_class_uniq', 'UNIQUE(class_name, name)', 'Cannot reuse name at the same scheduler class.'), ]

software_buildscheduler()

class software_schedchange(osv.osv):
    """ Connect a commit to a scheduler and if the sched is interested in it
    """
    _name = 'software_dev.sched_change'
    _description = 'Commit at Scheduler'
    _columns = {
        'commit_id': fields.many2one('software_dev.commit','Commit', required=True),
        'sched_id': fields.many2one('software_dev.buildscheduler','Scheduler', required=True, select=1),
        'important': fields.boolean('Is important', required=True,
                    help="If true, this change will trigger a build, else just recorded."),
    }
    _defaults = {
        'important': True,
    }

    _sql_constraints = [( 'commit_sched_uniq', 'UNIQUE(commit_id, sched_id)', 'A commit can only be at a scheduler once'), ]

software_schedchange()

#eof
