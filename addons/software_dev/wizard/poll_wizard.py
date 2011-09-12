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

class poll_wizard(osv.osv_memory):
    """ Request branch to poll remote side immediately
    
        For repositories like Git, this command will act on all sibling
        branches of the same repository, too.
    """

    _name = 'software_dev.wizard.poll_repo_wizard'
    _description = 'Poll Remote Repositories'

    _columns = {
        'repo_ids': fields.many2many('software_dev.repo',
                'poll_wizard_repo_rel', 'poll_wizard_id', 'repo_id',
                'Repos',
                help="The repositories to fetch from remote"),
        'buildbot_id': fields.many2one('software_dev.buildbot',
                string='BuildBot', required=True,
                help="Buildbot to use for polling"),
        }

    def __get_default_repo_ids(self, cr, uid, context=None):
        """ Translate from single "active_id" repo to many2many default
        """
        if context:
            if 'default_repo_id' in context:
                return [context['default_repo_id'], ]
        return False

    _defaults = {
        'repo_ids': __get_default_repo_ids
        }

    def poll(self, cr, uid, ids, context=None):
        """ Create the buildset and build request
        """
        bc_obj = self.pool.get('base.command.address')
        
        
        for rinc in self.browse(cr, uid, ids, context=context):
            done_fetch_urls = []
            proxy = bc_obj.get_proxy(cr, uid,
                    'software_dev.buildbot:%d' % (rinc.buildbot_id.id),
                    expires=date_eval('now +2mins'),
                    context=context)

            for repo in rinc.repo_ids:
                fu = repo.repo_url
                if fu in done_fetch_urls:
                    continue
                done_fetch_urls.append(fu)
                
            proxy.pollSources(done_fetch_urls)
        return {'type': 'ir.actions.act_window_close'}

poll_wizard()

#eof