
from twisted.application import service
from buildbot.slave.bot import BuildSlave

basedir = r'/home/hmo/Office/Projects/openerp-buildbot/openerp_buildbot_slave'
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
from buildbot.slave.commands import Command, SlaveShellCommand, ShellCommand, AbandonChain
from twisted.internet import reactor, defer, task
from twisted.python import log, failure, runtime
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


class CreateDB(Command):

    def _startCommand(self):
        log.msg("CreateDB._startCommand")
        import xmlrpclib
        conn = xmlrpclib.ServerProxy('http://localhost:8069' + '/xmlrpc/db')
        ls_db = conn.list()
        dbname = self.args.get('dbname','test')
        lang = self.args.get('lang','en_us')
        demo = self.args.get('demo',True)
        if dbname in ls_db:
            conn.drop('admin',dbname)
            msg = " '%s' Database is drop" %(dbname)
            self.sendStatus({'header': msg})
        db = conn.create('admin',dbname,demo,lang)
        msg = " '%s' Database is created" %(db)
        self.sendStatus({'header': msg})

    def start(self):
        self.deferred = defer.Deferred()
        try:
            self._startCommand()
        except:
            log.msg("error in CreateDB._startCommand")
            log.err()
            # pretend it was a shell error
            self.deferred.errback(AbandonChain(-1))
        
        return self.deferred
    
registerSlaveCommand("create-db", CreateDB, command_version)


class SlaveStartServer(SlaveShellCommand):

    def finished(self, sig, rc):
        if rc==-1:
            rc = 0
        SlaveShellCommand.finished(sig, rc)
    def start(self):
        args = self.args                              
        assert args['workdir'] is not None
        assert args['addonsdir'] is not None
        self.timeout = 30
        modules =  args.get('modules',[])
        pofiles =  args.get('pofiles',[])
        pidfile =  args.get('pidfile',[])
        workdir = os.path.join(self.builder.basedir, args['workdir'])
        addonsdir = os.path.join(self.builder.basedir, args['addonsdir'])
        if os.path.isfile(os.path.join(workdir+'/bin',pidfile)):
            file = open(os.path.join(workdir+'/bin',pidfile))
            pid = file.read()
            os.kill(int(pid),9)
        commandline = ["nohup","./openerp-server.py"]
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
        
        if args.get('stop_after_init',False):
            commandline += ["--stop-after-init"]
        commandline += "&"
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
    
registerSlaveCommand("start-server", SlaveStartServer, command_version)


