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
        'part_ids': fields.one2many('software_dev.part', 'component_id', 'Parts'),
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

class software_builder(osv.osv):
    _name = 'software_dev.builder'
    _description = 'Software Builder'
    _columns = {
        'name': fields.char('Name', required=True, size=64),
        'description': fields.text('Description'),
    }

    _defaults = {
    }

software_builder()

class software_dev_part(osv.osv):
    """Parts are divisions of components, which help narrow bugs

        A "component" is mapped to a whole repository branch, which
        may have some further logical divisions (like the doc/ directory,
        the lib/ part or unit tests.

        Then, the output of tests will indicate the part they refer to,
        like 'part_name.subpart.foo_test'.

        Parts can also be wildcards, with one line matching several names.
    """
    _name = 'software_dev.part'
    _description = 'Part of software Component'
    _order = 'sequence'

    _columns = {
        'component_id': fields.many2one('software_dev.component', 'Component',
                required=True, select=True),
        'sequence': fields.integer('Sequence', required=True),
        'name': fields.char('Name', required=True, size=64),
        'regex': fields.char('Expression', required=True, size=256,
                help="A Regular Expression, which is used to scan the logs output"
                    " for the part in question. May contain placeholders"),
        'tech_code': fields.char('Part Code', size=128,
                help="Full part name, or expression (with placeholders) to substitute"
                    " for the Reg.Ex. If not given, the Name will be used"),
    }

    _defaults = {
        'sequence': 10,
    }

software_dev_part()

#eof

