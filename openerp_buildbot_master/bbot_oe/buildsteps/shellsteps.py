# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
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

#from buildbot.process.buildstep import LoggingBuildStep
#from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS, EXCEPTION, SKIPPED
from bbot_oe.step_iface import StepOE
from  buildbot.steps import shell as bs
from  buildbot.steps import master as bm

class ShellCommand(StepOE, bs.ShellCommand):
    """ Slave shell command
    """
    name = 'Command'
    flunkOnFailure = False
    warnOnFailure = True

    def __init__(self, *args, **kwargs):
        """ Initialize, with args being the command items
        
            the ShellCommand class will render properties in *args for us
        """
        StepOE.__init__(self, keeper_conf=kwargs.pop('keeper_conf', None), **kwargs)
        kw2 = kwargs.copy()
        if args:
            kw2['command'] = [a or '' for a in args]
        kw2.pop('workdir', None)
        kw2.setdefault('logEnviron', False)
        bs.ShellCommand.__init__(self, workdir=self.workdir, **kw2)

    def setDefaultWorkdir(self, workdir):
        StepOE.setDefaultWorkdir(self, workdir)
        self.remote_kwargs['workdir'] = self.workdir

class MasterShellCommand(StepOE, bm.MasterShellCommand):
    """Shell command to run at the master side
    """
    name = 'Master Command'
    flunkOnFailure = False
    warnOnFailure = True

    def __init__(self, *args, **kwargs):
        """ Initialize, with args being the command items
        
            the ShellCommand class will render properties in *args for us
        """
        StepOE.__init__(self, keeper_conf=kwargs.pop('keeper_conf', None), **kwargs)
        kw2 = kwargs.copy()
        if args:
            kw2['command'] = [a or '' for a in args]
        bm.MasterShellCommand.__init__(self, **kw2)

exported_buildsteps = [ShellCommand, MasterShellCommand ]
#eof
