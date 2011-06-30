# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP Buildbot
#    Copyright (C) 2011 P. Christeas <xrg@hellug.gr>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import os, imp, logging
exported_buildsteps = []

def load_submodules(ourname):
    """Scan for python files under 'ourname' and load them as submodules
    
       All .py files of this directory will be loaded and their 'exported_buildsteps'
       will be appended to our list.
    """
    logger = logging.getLogger('modules')
    
    modpath = os.path.dirname(ourname)
    
    logger.debug("Scanning modules under %s", modpath)
    
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
                newexps = getattr(newmod, 'exported_buildsteps', None)
                if newexps:
                    exported_buildsteps.extend(newexps)
        except ImportError:
            logger.exception("Module %s is not loadable", m)
        finally:
            if fm and fm[0]:
                fm[0].close()

load_submodules(__file__)

#eof