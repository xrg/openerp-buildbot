# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>). All Rights Reserved
#    $Id$
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


from buildbot.slave.commands import Command, SlaveShellCommand, ShellCommand, AbandonChain
from twisted.internet import reactor, defer, task
from twisted.python import log, failure, runtime
import os
command_version = "0.0.1"
	

class SlaveCp(SlaveShellCommand):
    def start(self):
        args = self.args
        assert args['workdir'] is not None
        assert args['addonsdir'] is not None
        workdir = os.path.join(self.builder.basedir, args['workdir'])
        addonsdir = args['addonsdir']
        dirs = []
        for dir in os.listdir(workdir):
            if dir not in ['.buildbot-sourcedata','.bzrignore','.bzr']:
                dirs.append(dir)
        commandline = ["cp","-r","-u"]
        commandline += dirs
        commandline += [addonsdir]
        c = ShellCommand(self.builder, commandline,
                         workdir, environ=None,
                         timeout=args.get('timeout', None),
                         sendStdout=args.get('want_stdout', True),
                         sendStderr=args.get('want_stderr', True),
                         sendRC=True,
                         initialStdin=args.get('initial_stdin'),
                         keepStdinOpen=args.get('keep_stdin_open'),
                         logfiles=args.get('logfiles', {}),
                         )
        self.command = c
        d = self.command.start()
        return d
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:        
