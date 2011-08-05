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
from tools.date_eval import date_eval

class resolve_incomplete(osv.osv_memory):
    """ Request buildbot to scan incomplete commits
    """

    _name = 'software_dev.wizard.resolve_incomplete'
    _description = 'Resolve Incomplete Commits'

    _columns = {
        'repo_ids': fields.many2many('software_dev.repo',
                'resolve_incomplete_repo_rel', 'resolve_incomplete_id', 'repo_id',
                'Repos',
                help="The repositories to find incomplete commits at"),
        'buildbot_id': fields.many2one('software_dev.buildbot',
                string='BuildBot', required=True,
                help="Buildbot to use for resolving commits"),
        }

    def __get_default_repo_id(self, cr, uid, context=None):
        """ Translate from single "active_id" repo to many2many default
        """
        if context:
            if 'default_repo_id' in context:
                return [context['default_repo_id'], ]
        return False

    _defaults = {
        'repo_ids': __get_default_repo_id
        }

    def resolve(self, cr, uid, ids, context=None):
        """ Create the buildset and build request
        """
        commit_obj = self.pool.get('software_dev.commit')
        bc_obj = self.pool.get('base.command.address')
        
        for rinc in self.browse(cr, uid, ids, context=context):
            for rid in rinc.repo_ids:
                # usually they would be only in the '::rest' branch, but we search
                # all of them, nevertheless
                branch_ids = [b.id for b in rid.branch_ids]
                
                commit_res = commit_obj.search_read(cr, uid, [('branch_id', 'in', branch_ids),
                        ('ctype','=','incomplete')], fields=['hash'], context=context)
                if not commit_res:
                    continue
                
                commits = [ c['hash'] for c in commit_res ]
                
                proxy = bc_obj.get_proxy(cr, uid,
                        'software_dev.buildbot:%d' % (rinc.buildbot_id.id),
                        expires=date_eval('now +1hour'),
                        context=context)
                rest_branch_id = rid.get_rest_branch(context=context)

                while commits:
                    proxy.rescan_commits(rid.repo_url, commits[:1000],
                                        branch_id=rest_branch_id, standalone=True)
                    commits = commits[1000:]
        return {'type': 'ir.actions.act_window_close'}

resolve_incomplete()

#eof