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

from osv import fields, osv

class software_dev_property(osv.osv):
    """ A class for generic properties on buildbot classes
    """
    
    _name = 'software_dev.property'
    
    _columns = {
        'model_id': fields.many2one('ir.model', 'Model', required=True,
                        select=1,
                        domain= [('model', 'like','software_dev.')],
                        help="The model to have the property"),
        'resid': fields.integer('Res ID', required=True, select=1),
        'name': fields.char('Name', size=256, required=True),
        'value': fields.text('Value', required=True),
    }
    
software_dev_property()


class software_dev_state_obj(osv.osv):
    """ Object states, properties for arbitrary buildbot-side classes

        Unlike software_dev.property, these are attached to remote-side
        classes, and have multiple name-value pairs
    """

    _name = 'software_dev.state_obj'

    _columns = {
        'name': fields.char('Name', size=128, required=True),
        'class_name': fields.char('Name', size=128, required=True),
        'val_ids': fields.one2many('software_dev.state_val', 'object_id', 'Values'),
    }

    _sql_constraints = [ ('name_class_uniq', 'UNIQUE(name, class_name)', 'Objects must be unique'), ]

software_dev_state_obj()

class software_dev_state_obj_val(osv.osv):
    """ Complementary class to state_obj, holds the name-value pairs
    """
    _name = 'software_dev.state_val'
    _log_access = False

    _columns = {
        'object_id': fields.many2one('software_dev.state_obj', 'Object',
                required=True, ondelete='cascade'),
        'name': fields.char('Name', size=256, required=True),
        'value': fields.struct('Value'),
    }

    _sql_constraints = [ ('object_name_uniq', 'UNIQUE(object_id, name)', 'Name must be unique per object'), ]

software_dev_state_obj_val()

#eof