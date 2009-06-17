
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

    def finished(self, signal=None, rc=0):
        log.msg("command finished with signal %s, exit code %s" % (signal,rc))        
        if signal is not None:
            rc = 0        
        d = self.deferred 
        self.deferred = None       
        if d:
            d.callback(rc)
        else:
            log.msg("Hey, command %s finished twice" % self)
        

    def failed(self, why):
        log.msg("  wait command failed [%s]" % self.stepId)
        d = self.deferred
        self.deferred = None
        if d:
            d.errback(why)
        else:
            log.msg("Hey, command %s finished twice" % self)

    def _startCommand(self):
        log.msg("CreateDB._startCommand")
        import xmlrpclib
        port = self.args.get('port',8069)
        host = 'localhost'
        uri = 'http://' + host + ':' + str(port)
        log.msg("Server : " + uri)
        conn = xmlrpclib.ServerProxy(uri + '/xmlrpc/db')        
        ls_db = conn.list() 
        dbname = self.args.get('dbname','test')
        lang = self.args.get('lang','en_us')
        demo = self.args.get('demo',True)
        if dbname in ls_db:
            try:
                conn.drop('admin',dbname)
                msg = " '%s' Database is dropped\n" %(dbname)
            except:
                msg = " '%s' Database cannot be dropped. It is being accessed by other users.\n" %(dbname)
                self.finished(None, -1) 
            self.sendStatus({'header': msg})
            log.msg(msg)
        else:    
            db = conn.create('admin',dbname,demo,lang)
            if db:
                msg = " '%s' Database is created and wait for 30 seconds." %(dbname)
            else:
                msg = " '%s' Database is not created" %(dbname)
            self.sendStatus({'header': msg})
            log.msg(msg)       
            reactor.callLater(30, self.finished)

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
        modules =  args.get('modules',[])
        pofiles =  args.get('pofiles',[])
        pidfile =  args.get('pidfile',[])
        workdir = os.path.join(self.builder.basedir, args['workdir'])
        addonsdir = os.path.join(self.builder.basedir, args['addonsdir'])
        

        #MAKE Config file
        if os.path.isfile(os.path.join(workdir,'.openerp_serverrc')):
           os.remove(os.path.join(workdir,'.openerp_serverrc'))
        
        fp_config = open(os.path.join(workdir,'.openerp_serverrc'),'w')        
        fp_config.write('[options]\n')
        fp_config.write('without_demo=False\n')
        if args.get('netport',8070):
            fp_config.write('netport=%s\n'%(args.get('netport',8070)))
        fp_config.write('secure=False\n')
        fp_config.write('smtp_user=False\n')
        fp_config.write('demo={}\n')
        fp_config.write('syslog=False\n')
        fp_config.write('logfile=/home/tiny/Desktop/openerp.log\n')
        fp_config.write('cache_timeout=100000\n')
        if args.get('netport',8069):
            fp_config.write('port=%s\n'%(args.get('port',8069)))
        fp_config.write('reportgz=False\n')
        fp_config.write('secure_pkey_file=server.pkey\n')        
        fp_config.write('log_level=info\n')
        fp_config.write('admin_passwd=admin\n')
        fp_config.write('assert_exit_level=warn\n')
        fp_config.write('root_path=%s\n'%(workdir))
        if addonsdir:
            fp_config.write('addons_path=%s\n'%(addonsdir))
        if args['dbname']:
            fp_config.write('db_name=%s\n' %(args['dbname']))
        if len(modules):
            fp_config.write("i=%s\n"%(','.join(modules)))

        fnames = []
        if len(pofiles):            
           for pofile in pofiles:
               fname,ext = os.path.splitext(pofile.split('/')[-1])
               fnames.append(fname)           

        if len(fnames):
           fp_config.write("l = %s\n" %(','.join(fnames)))
           fp_config.write("i18n-import = %s\n"%(','.join(pofiles)))
           
        fp_config.close()
        os.chmod(os.path.join(workdir,'.openerp_serverrc'),0777)

        # Make daemon script to start, stop, restart server auto
        if os.path.isfile(os.path.join(workdir,'openerp-server')):
            os.remove(os.path.join(workdir,'openerp-server'))
        fp = open(os.path.join(workdir,'openerp-server'),'w')        
        fp.write('#!/bin/sh\n')
        fp.write('RUN_MODE="daemons"\n')
        fp.write('TINYPATH=%s\n'%(workdir))
        fp.write('TINYPID=$TINYPATH/openerp.pid\n')
        fp.write('TINYLOG=$TINYPATH/openerp.log\n')
        fp.write('TINYCONFIG=$TINYPATH/.openerp_serverrc\n')                   
        
        fp.write("""
if [ $1 ]; then
    echo $1'ing server'
else
    set start
fi


case "$1" in
start)
echo " ---`date +\"%D-%H:%M:%S\"`--- Starting OpenERP Server daemon ..." 
echo "Starting OpenERP Server daemon ..."

if ! start-stop-daemon --start --quiet --background   --pidfile $TINYPID --make-pidfile --exec $TINYPATH/openerp-server.py -- --config=$TINYCONFIG; then
echo " ---`date +\"%D-%H:%M:%S\"`--- ERROR Starting OpenERP Server daemons ..." 
exit 1
fi
echo " ---`date +\"%D-%H:%M:%S\"`--- OpenERP Server daemon is started ..." 

;;
stop)
echo " ---`date +\"%D-%H:%M:%S\"`--- Stopping OpenERP Server daemon ..." 

start-stop-daemon --stop --quiet --pidfile $TINYPID
# Wait a little and remove stale PID file
sleep 1
if [ -f $TINYPID ] && ! ps h `cat $TINYPID` > /dev/null
then
# Stale PID file (nmbd was succesfully stopped),
# remove it (should be removed by nmbd itself IMHO.)
rm -f $TINYPID
fi

echo " ---`date +\"%D-%H:%M:%S\"`--- OpenERP Server daemon stopped ..." 
echo "OpenERP Server daemon stopped ..."
;;
restart|force-reload)
$0 stop
sleep 1
$0 start
;;
*)
echo " ---`date +\"%D-%H:%M:%S\"`--- Usage: /etc/init.d/openerp-server {start|stop|reload|restart|force-reload}" 
exit 1 
;;
esac

exit 0

        """)
        fp.close()
        os.chmod(os.path.join(workdir,'openerp-server'),0777)
        commandline = ["./openerp-server","restart"]
        c = ShellCommand(self.builder, commandline,
                         workdir, environ=None,
                         timeout=args.get('timeout', None),
                         sendStdout=args.get('want_stdout', True),
                         sendStderr=args.get('want_stderr', True),
                         sendRC=True,
                         initialStdin=args.get('initial_stdin'),
                         keepStdinOpen=args.get('keep_stdin_open'),
                         logfiles={'log detail':'openerp.log'},
                         )
        self.command = c
        d = self.command.start()
        return d
    
registerSlaveCommand("start-server", SlaveStartServer, command_version)


