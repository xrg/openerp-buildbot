# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
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

from osv import fields, osv
from tools.func import virtual

class software_multibranchseries(osv.osv):
    """ Buildseries for multiple branches
    """
    _name = 'software_dev.buildseries.multibranch'
    _inherits = { 'software_dev.buildseries': 'buildseries_id' }
    
    _columns = {
        'buildseries_id': fields.many2one('software_dev.buildseries', 'Build Series', required=True, select=True, ondelete="cascade"),
        'branch_ids': fields.many2many('software_dev.branch', 'buildseries_branch_rel', 'series_id', 'branch_id',
            string='Branches'),
    }
    
    @virtual
    def get_builders(self, cr, uid, ids, context=None):
        ret = []
        bseries_obj = self.pool.get('software_dev.buildseries')
        def orm_list(item):
            """ Put a single browse record in a browse-browse compatible list
            """
            return osv.orm.browse_record_list([item,], context=context)
        
        for bro in self.browse(cr, uid, ids, context=context):
            r = bseries_obj.get_builders(cr, uid, orm_list(bro.buildseries_id), context=context)
            if not r:
                continue
            assert len(r) == 1, "len(get_builders([%s])): %d" %(bro.buildseries_id.id, len(r))
            r = r[0]
            r['branch_ids'] = [ b.id for b in bro.branch_ids] + [r.pop('branch_id'),]
            ret.append(r)
        return ret

software_multibranchseries()

class software_buildbot(osv.osv):
    _inherit = 'software_dev.buildbot'

    def _iter_polled_branches(self, cr, uid, ids, context=None):
        bmbranch_obj = self.pool.get('software_dev.buildseries.multibranch')
        
        for ib in super(software_buildbot, self).\
                _iter_polled_branches(cr, uid, ids, context=context):
            yield ib

        for bser in bmbranch_obj.browse(cr, uid, [('builder_id','in',ids)], context=context):
            for branch in bser.branch_ids:
                yield branch
        #fn end

software_buildbot()

#eof