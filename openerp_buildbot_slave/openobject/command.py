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
        if 'stable_openobject_server' in args['addonsdir'].split('/'):
        	dirs.append('base')
        else:
	        for dir in os.listdir(workdir):
	            if dir not in ['.buildbot-sourcedata','.bzrignore','.bzr','.svn','README.txt']:
	            	if dir == 'base':
	            	   continue
	                dirs.append(dir)
        commandline = ["cp","-r","-u"]
        #commandline = ["find",".", "|" ,"grep" ,"-v","'/\.'"] #| cpio -dump $DESTINATION_DIR/.
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

class CreateDB(SlaveShellCommand):
	def start(self): 
		script_path = self.builder.basedir+'/../openobject/script.py'
		args = self.args
		assert args['workdir'] is not None
		assert args['addonsdir'] is not None
		workdir = os.path.join(self.builder.basedir, args['workdir'])
		addonsdir = args['addonsdir']
		commandline = ["python", script_path, "create-db"]
		commandline.append("--root-path=%s"%(workdir))
		if args['dbname']:
		    commandline.append("--database=%s"%(self.args['dbname']))
		if self.args['port']:
		    commandline.append("--port=%s"%(self.args['port']))
		
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

class InstallModule(SlaveShellCommand):
	def start(self):
		script_path = self.builder.basedir+'/../openobject/script.py'
		args = self.args
		assert args['workdir'] is not None
		assert args['addonsdir'] is not None
		workdir = os.path.join(self.builder.basedir, args['workdir'])
		addonsdir = args['addonsdir']
		commandline = ["python", script_path, "install-module"]
		commandline.append("--root-path=%s"%(workdir))
		if args['dbname']:
		    commandline.append("--database=%s"%(self.args['dbname']))
		if self.args['port']:
		    commandline.append("--port=%s"%(self.args['port']))
		if self.args['modules']:
			commandline.append("--modules=%s"%(self.args['modules']))
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
