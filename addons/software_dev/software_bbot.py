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

software_buildbot()

class software_battr(osv.osv):
    _name = 'software_dev.battr'
    _columns = {
        'bbot_id': fields.many2one('software_dev.buildbot', 'BuildBot', required=True, select=1),
        'name': fields.char('Name', size=64, required=True, select=1),
        'value': fields.char('Value', size=256),
        }
    
software_battr()

