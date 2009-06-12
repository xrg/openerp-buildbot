
from twisted.application import service
from buildbot.slave.bot import BuildSlave

basedir = r'/home/hmo/Office/Projects/openerp_buildbot_slave'
buildmaster_host = 'localhost'
port = 9999
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
from buildbot.slave.commands import SlaveShellCommand, ShellCommand
import os
command_version = "0.0.1"
class SlavePyFlakes(SlaveShellCommand):
    def start(self):
        args = self.args                      
        assert args['workdir'] is not None
        assert args['files'] is not None
        commandline = ["pyflakes"]
        commandline += args['files']
        workdir = os.path.join(self.builder.basedir, args['workdir'])
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
    
registerSlaveCommand("pyflakes", SlavePyFlakes, command_version)


class SlaveCreateDB(SlaveShellCommand):
    def start(self):
        args = self.args                              
        assert args['dbname'] is not None       
        workdir = os.path.join(self.builder.basedir, args['workdir'])
        commandline = ["createdb",args['dbname']]
        c = ShellCommand(self.builder, commandline,
                         workdir=workdir, environ=None,
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
    
registerSlaveCommand("create-db", SlaveCreateDB, command_version)


class SlaveDropDB(SlaveShellCommand):
    def start(self):
        args = self.args                              
        assert args['dbname'] is not None       
        workdir = os.path.join(self.builder.basedir, args['workdir'])
        commandline = ["dropdb", args['dbname']]               
        c = ShellCommand(self.builder, commandline,
                         workdir=workdir, environ=None,
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
    
registerSlaveCommand("drop-db", SlaveDropDB, command_version)


class SlaveTestServer(SlaveShellCommand):
    def start(self):
        args = self.args                      
        assert args['workdir'] is not None
        assert args['addonsdir'] is not None
        modules =  args['modules'] 
        pofiles =  args['pofiles']
        pidfile =  args['pidfile']           
        workdir = os.path.join(self.builder.basedir, args['workdir'])
        addonsdir = os.path.join(self.builder.basedir, args['addonsdir'])
        if os.path.isfile(os.path.join(workdir+'/bin',pidfile)):
            file = open(os.path.join(workdir+'/bin',pidfile))
            pid = file.read()
            os.kill(int(pid),9)
        commandline = ["./openerp-server.py"]
        if pidfile:            
            commandline += ["--pidfile",pidfile]
        if len(pofiles):
            fnames = []
            for pofile in pofiles:
                fname,ext = os.path.splitext(pofile.split('/')[-1])
                fnames.append(fname)
            commandline += ["-l",','.join(fnames),"--i18n-import",','.join(pofiles)]
        if addonsdir:
            commandline += ["--addons-path",addonsdir]
        if args['dbname']:
            commandline += ["-d",args['dbname']]
        if len(modules):
            commandline += ["-i",','.join(modules)]
        
        
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
    
registerSlaveCommand("test-server", SlaveTestServer, command_version)


