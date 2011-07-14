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


{
    'name': 'Software Development and Testing',
    'version': '0.2',
    'category': 'Generic Modules/Others',
    'description': """Integrate the software development procedures, automated
builds and testing into the ERP.
    
""",
    'author': 'OpenERP SA',
    'website': 'http://www.openerp.com',
    'depends': ['base','project', 'hr', 'koo'],
    'init_xml': [],
    'update_xml': [
        'security/software_security.xml',
        'security/ir.model.access.csv',
        'software_dev_view.xml',
        'software_dev_data.xml',
    ],
    'api_depends': ['engine-pg84', 'exec_dict', 'search-browse',
            'virtual-fns', 'search-read', 'browse-browse',
            'struct-field',
            ],
    'demo_xml': [ 'software_dev_demo.xml'],
    'test': [
        # 'test/software_dev.yml',
    ],
    'installable': True,
    'active': False,
    'certificate': None,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
