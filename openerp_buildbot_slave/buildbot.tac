
from twisted.application import service
from buildbot.slave.bot import BuildSlave

basedir = r'/home/nch/openERP/Extra-branch/HMOsir/openerp-buildbot/openerp_buildbot_slave'
buildmaster_host = '127.0.0.1'
port = 8999
slavename = 'openerp_bot'
passwd = 'tiny'
keepalive = 600
usepty = 1
umask = None

application = service.Application('buildslave')
s = BuildSlave(buildmaster_host, port, slavename, passwd, basedir,
               keepalive, usepty, umask=umask)
s.setServiceParent(application)

	
from buildbot.slave.registry import registerSlaveCommand
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
            if dir != '.bzr':
                dirs.append(dir)
        commandline = ["cp","-r"]
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
registerSlaveCommand("copy", SlaveCp, command_version)



