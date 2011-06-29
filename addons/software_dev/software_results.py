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
# from properties import propertyMix

class software_test_result(osv.osv):
    """ This is the unit of results for software tests
    """
    
    _name = "software_dev.test_result"
    _columns = {
                'name': fields.char('Name of Step', size=128, help="Name of the Test step"),
                'sequence': fields.integer('Sequence', required=True),
                # TODO 'teststep_id':
                'build_id': fields.many2one('software_dev.commit', 'Build', ondelete='cascade',
                        select=1,
                        help="Build on which the result was taken"),
                'blame_log': fields.text("Summary", help="Quick blame info of thing(s) that failed"),
                'substep': fields.char('Substep', size=256, help="Detailed substep"),
                'rate_pc': fields.float('Score', help='A measure of success, marked as a percentage'),
                
                'state': fields.selection([('unknown','Unknown'), ('fail', 'Failed'), 
                                            ('warning','Warning'), ('exception', 'Exception'),
                                            ('pass', 'Passed'),('skip', 'Skipped'),
                                            ('retry', 'Retry'),
                                            ('debug','Debug')], 
                                            "Test Result", readonly=True, required=True,
                                            help="Final State of the Test Step"),
        }
    _defaults = {
                 'state': 'unknown',
                 'sequence': 0,
                }
    _order = 'build_id, sequence, id'

software_test_result()

#eof