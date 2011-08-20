# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Software Development Solution
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
    'name': 'Software Development Mirrors',
    'version': '0.1',
    'category': 'Generic Modules/Others',
    'description': """ Adds repository mirroring functionality to the Software
Development module

    This will create special models that keep the mirroring data (fastimport
    marks) and relations between branches of alien repositories.
""",
    'author': 'P. Christeas <xrg@hellug.gr>',
    'website': 'http://pefnos2.homelinux.org',
    'depends': ['software_dev'],
    'init_xml': [],
    'update_xml': [
        'security/ir.model.access.csv',
        'software_dev_mirrors_view.xml',
        'wizard/verify_marks.xml',
    ],
    'api_depends': ['engine-pg84',
            ],
    'demo_xml': [ ],
    'test': [
        # 'test/software_dev_mirrors.yml',
    ],
    'installable': True,
    'active': False,
    'certificate': None,
}

# eof
