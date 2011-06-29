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

class propertyMix(object):
    """ A complementary class that adds properties to osv objects
    
        In principle, these properties could apply to any osv object,
        but we do only use them for the software_dev.* ones.
    """

    _auto_properties = []

    def getProperties(self, cr, uid, ids, names=None, context=None):
        """ Retrieve the properties for a range of ids.
        
            The object is the class inheriting this one.
            Due to a limitation of XML-RPC, we could not regroup the
            result by 'id', so the returning result is that of read() :
            [ { 'id': 1, 'name': prop, 'value': val }, ... ]
        """
        prop_obj = self.pool.get('software_dev.property')

        dom = [('model_id.model', '=', self._name), ('resid', 'in', list(ids)), ]
        if names:
            dom.append(('name', 'in', names))
        pids = prop_obj.search(cr, uid, dom, context=context)

        if not pids:
            return []
        res = prop_obj.read(cr, uid, pids, ['name', 'value'], context=context)

        return res

    def setProperties(self, cr, uid, id, vals, clear=False, context=None):
        """ Set properties for one object
        """
        prop_obj = self.pool.get('software_dev.property')
        imo_obj = self.pool.get('ir.model')
        
        imid = imo_obj.search(cr, uid, [('model', '=', self._name)])[0]

        if clear:
            dom = [('model_id.model', '=', self._name), ('resid', '=', id), ]
            pids = prop_obj.search(cr, uid, dom, context=context)
            if pids:
                prop_obj.unlink(cr, uid, pids)

        for name, value in vals: # yes, values must be a list of tuples
            if name in self._auto_properties:
                # Skip setting these ones, since the class should override
                # and take care of them.
                continue
            prop_obj.create(cr, uid, { 'model_id': imid, 'resid': id,
                                        'name': name, 'value': value }, context=context)

        return True

bbot_results = [(0, "Success"), (1, "Warnings"), (2, "Failure"), (3, "Skipped"), (4,"exception"), (5, "retry")]

#eof

