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


""" BuildStep interface classes

"""

class StepOE:
    """Mix-in class for BuildbotOE-aware Steps
    
        By mixing this class in a Buildstep, master-keeper will know that it
        needs to supply the `keeper_conf` dict automatically to the keyword
        arguments of the step.
        
        TODO doc for keeper_conf
    """
    def __init__(self, **kwargs):
        assert 'keeper_conf' in kwargs
        if kwargs.get('workdir',False):
            self.workdir = kwargs['workdir']
        elif kwargs.get('keeper_conf'):
            self.workdir = None
            components = kwargs['keeper_conf']['builder'].get('components',[])
            for comp in components.values():
                if comp['is_rolling']:
                    if comp.get('dest_path'):
                        self.workdir = comp['dest_path']
                        break
            else:
                if len(components) > 1:
                    # we have to override the default 'build' one
                    self.workdir = '.'
        else:
            if not hasattr(self, 'workdir'):
                self.workdir = None

    def setDefaultWorkdir(self, workdir):
        if not self.workdir:
            self.workdir = workdir


#eof
