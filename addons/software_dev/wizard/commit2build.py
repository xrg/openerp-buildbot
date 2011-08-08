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


class commit2build(osv.osv_memory):
    """Manually request a build for a specific commit
    """

    _name = 'software_dev.wizard.commit2build'
    _description = 'Manual build request'

    _columns = {
        'commit_id': fields.many2one('software_dev.commit', 'Commit',
                help="The commit to test"),
        'builder_id': fields.many2one('software_dev.buildseries',
                string='Build Series', required=True,
                help="Configuration of builder + buildbot to use. Also implies the tests requested."),
        'reason': fields.char('Reason', size=256, required=True,
                help="A word to describe the reason this request is being asked"),

        }

    _defaults = {
        'reason': 'manual',
        }

    def request_commit(self, cr, uid, ids, context=None):
        """ Create the buildset and build request
        """
        bset_obj = self.pool.get('software_dev.buildset')
        breq_obj = self.pool.get('software_dev.buildrequest')
        ret_ids = []
        val_now = fields.datetime.now()
        buildbot_ids = set()
        for bro in self.browse(cr, uid, ids, context=context):
            # step 1: create buildset

            bset_id = bset_obj.create(cr, uid, {
                    'commit_id': bro.commit_id.id,
                    'reason': bro.reason,
                    'submitted_at': val_now,
                    'complete': False,
                    },
                    context=context)

            # step 2: request a build for that
            breq_id = breq_obj.create(cr, uid, {
                    'builder_id': bro.builder_id.id,
                    'buildsetid': bset_id,
                    'complete': False,
                    'submitted_at': val_now,
                    },
                    context=context)
            ret_ids.append(bset_id)
            buildbot_ids.add(bro.builder_id.builder_id.id)


        try:
            bc_obj = self.pool.get('base.command.address')
            for bbid in buildbot_ids:
                proxy = bc_obj.get_proxy(cr, uid,
                        'software_dev.buildbot:%d' % (bbid),
                        expires=date_eval('now +1hour'),
                        context=context)
                proxy.triggerMasterRequests()
                # TODO: perhaps narrow to the request we've sent
        except Exception, e:
            print "exception", e
            pass
        return {'type': 'ir.actions.act_window_close'}

commit2build()

#eof