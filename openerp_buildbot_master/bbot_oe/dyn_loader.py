# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Buildbot
#    Copyright (C) 2011 P. Christeas <xrg@hellug.gr>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import os, imp, logging

""" Utility function to dynamically import all modules of a directory
"""

def load_submodules(ourname, magic_vars=None):
    """Scan for python files under 'ourname' and load them as submodules
    
        @param magic_vars  A dictionary of key->collection for variables
            that will be appended from the loaded modules. key is the identifier
            of an attribute to be searched in the loaded module, collection is
            the target to be appended/updated (if list/dict)
            
        All .py files of this directory will be loaded and their 'exported_buildsteps'
        will be appended to our list.
    """
    logger = logging.getLogger('modules')
    
    modpath = os.path.dirname(ourname)
    
    logger.debug("Scanning modules under %s", modpath)
    
    if magic_vars is None:
        magic_vars = {}

    for fname in os.listdir(modpath):
        # logger.debug("located %s", fname)
        m = None
        if fname.startswith('_') or fname.startswith('.'):
            continue
        if os.path.isdir(fname):
            m = fname
        elif fname.endswith('.py'):
            m = fname[:-3]
        elif fname.endswith('.pyc') or fname.endswith('pyo'):
            m = fname[:-4]
            
        if not m:
            continue
        
        try:
            logger.debug("Trying module '%s'", m)
            fm = imp.find_module(m, [modpath,])
            if fm:
                newmod = imp.load_module(m, *fm)
                logger.info("Loaded module %s", m)
                for key, col in magic_vars.items():
                    newcol = getattr(newmod, key, None)
                    if newcol and getattr(col, 'extend', False):
                        col.extend(newcol)
                    elif newcol and getattr(col, 'update', False):
                        col.update(newcol)
                    elif newcol:
                        raise TypeError("How do I append to a %s?" % type(col))
        except ImportError:
            logger.exception("Module %s is not loadable", m)
        finally:
            if fm and fm[0]:
                fm[0].close()

#eof