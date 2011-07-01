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


""" Repository handling interface classes

"""

class RepoFactory(object):
    
    @classmethod
    def createPoller(cls, poller_dict, conf, tmpconf):
        """ Create, in conf{}, a Poller object according to poller_dict
        
            @param poller_dict data from openerp-server
            @param conf dictionary to receive buildmaster configuration
            @param tmpconf dictionary of configuration calues local to the
                keeper loading algorithm. Holds keeper-wide configuration, as
                well as tmp values (eg. proxied paths map)
        """
        raise NotImplementedError

#eof