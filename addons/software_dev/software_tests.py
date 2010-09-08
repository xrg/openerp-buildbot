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

class software_group(osv.osv):
    _name = 'software_dev.buildgroup'
    _description = 'Software Build Group'
    _columns = {
        'name': fields.char('Name', required=True, size=64),
        'description': fields.text('Description'),
        'public': fields.boolean('Public', required=True,
                help="If true, the results will be at the main page"),
        'sequence': fields.integer('Sequence', required=True),
    }

    _defaults = {
        'public': True,
        'sequence': 10,
    }
software_group()

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

class software_buildseries(osv.osv):
    """ A series is a setup of package+test scenaria
    """
    _name = 'software_dev.buildseries'
    _description = 'Build Series'
    _columns = {
        'name': fields.char('Name', required=True, size=64),
        'description': fields.text('Description'),
        'group_id': fields.many2one('software_dev.buildgroup', 'Group', ),
        'is_distinct': fields.boolean('Distinct builds', required=True,
                help="If set, this series has random builds, not commits that follow each other"),
        
        'package_id': fields.many2one('software_dev.package', 'Package', required=True),
        'branch_id': fields.many2one('software_dev.branch', 'Rolling branch', required=True,
                help="One branch, that is used to test against different commits.",
                ),
        'builder_id': fields.many2one('software_dev.builder', 
                string='Builder', required=True,
                help="Machine that will build this series"),
        'sequence': fields.integer('Sequence', required=True),
        # 'attribute_ids': fields.one2many('software_dev.attr.bseries', '' TODO)
    }

    _defaults = {
        'is_distinct': False,
        'sequence': 10,
    }

software_buildseries()


