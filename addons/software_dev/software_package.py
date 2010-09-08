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

class software_component(osv.osv):
    _name = 'software_dev.component'
    _description = 'Software Component'
    _columns = {
        'name': fields.char('Name', required=True, size=64),
        'tech_code': fields.char('Tech code', size=64,
                help="Technical code of the component."),
        'description': fields.text('Description'),
        'dest_path': fields.char("Dest. Path", size=128,
                help="Path where this component will be installed. May be relative."),
        # 'component_ids': fields.many2many(...),
    }

    _defaults = {
    }

software_component()

class software_package(osv.osv):
    _name = 'software_dev.package'
    _description = 'Software Package'
    _columns = {
        'name': fields.char('Name', required=True, size=64),
        'description': fields.text('Description'),
        'component_ids': fields.many2many('software_dev.component', 
            'software_dev_pack_comp_rel', 'pkg_id', 'comp_id', 
            string="Components"),
        'project_id': fields.many2one('project.project', 'Related project'),
    }

    _defaults = {
    }

software_package()

#eof

