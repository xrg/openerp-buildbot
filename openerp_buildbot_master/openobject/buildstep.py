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

from buildbot.steps.source import Source, Bzr, SVN
from buildbot.steps.shell import ShellCommand
from buildbot.process.buildstep import LoggingBuildStep, LoggedRemoteCommand, LogLineObserver
from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS
import base64
import pickle
import os
import re
import logging
from openobject import tools
from twisted.python import log

try:
    import cStringIO
    StringIO = cStringIO.StringIO
except ImportError:
    from StringIO import StringIO

blame_severities =  { 'warning': 1, 'error': 3, 'exception': 4,
            'critical': 8 , 'blocking': 10 }

def append_fail(flist, blames, suffix=None, fmax=None):
    """ Append blames to the flist, in order of severity
    
        @param suffix add that to each blame added
        @param max  Don't let flist grow more than max
        @return True if flist has changed
    """
    
    found = False
    for blame, bsev in blames:
        fi = 0
        while fi < len(flist):
            if flist[fi][1] < bsev:
                break
            fi += 1
        
        if fmax and fi >= fmax:
            break
        if suffix:
            blame += suffix
        flist.insert(fi, (blame, bsev))
        found = True

    if found and fmax:
        while len(flist) > fmax:
            flist.pop()
            # note that we have to use fns, rather than flist = flist[:]
    
    return found

def blist2str(blist):
    blist = filter( lambda x: isinstance(x, tuple), blist)
    return '\n'.join([ x[0] for x in blist])

def create_test_step_log(step_object = None, step_name = '', cmd=None):
    source = step_object.build.builder.test_ids
    properties = step_object.build.builder.openerp_properties
    openerp_host = properties.get('openerp_host', 'localhost')
    openerp_port = properties.get('openerp_port',8069)
    openerp_dbname = properties.get('openerp_dbname','buildbot')
    openerp_userid = properties.get('openerp_userid','admin')
    openerp_userpwd = properties.get('openerp_userpwd','a')
    revision = step_object.build.source.changes[0].revision

    openerp = buildbot_xmlrpc(host = openerp_host, port = openerp_port, dbname = openerp_dbname)
    openerp_uid = openerp.execute('common','login',  openerp.dbname, openerp_userid, openerp_userpwd)

    tested_branch = step_object.build.source.changes[0].branch
    args = [('url','ilike',tested_branch),('is_test_branch','=',False),('is_root_branch','=',False)]
    tested_branch_ids = openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.lp.branch','search',args)

    tested_branch_id = tested_branch_ids[0]
    last_revision_no_stored = properties.get(tested_branch_id, {}).get('latest_rev_no',0)
    last_revision_id_stored = properties.get(tested_branch_id, {}).get('latest_rev_id','')
    test_id = source.get(revision, False)
    summary = step_object.summaries
    test_values = None
    fail_reasons = []
    for logname, data in summary.items():
        state = data.get('state', 'pass')
        if step_name in ('bzr-update', 'bzr_merge'):
            if state == 'fail':
                test_values = {'failure_reason':'This test has been skipped because the step %s has failed ! \n for more details please refer the Test steps tab.'%(step_name),'state':state}
                branch_values = {'latest_rev_no':last_revision_no_stored,'latest_rev_id':last_revision_id_stored}
                openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.lp.branch','write', [int(tested_branch_id)], branch_values)
                openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.test','write', [int(test_id)], test_values)
            openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.test','write', [int(test_id)],{'environment':step_object.env_info})

        params = {}
        params['name'] = logname
        params['test_id'] = int(test_id)
        if data.get('quality_log', False):
           params['quality_log'] = base64.encodestring('\n'.join(data['quality_log']))
        if data.get('log', False):
           params['log'] = base64.encodestring('\n'.join(data['log']))
           
        if data.get('blame', False):
            params['blame_log'] = blist2str(data['blame'])
            if append_fail(fail_reasons, data['blame'], \
                    suffix=' (at %s)' % step_name, fmax=5):
                # By default, only print first failed (blamed) test as reason
                test_values = {'failure_reason': blist2str(fail_reasons),
                                'state':state}
                openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 
                        'buildbot.test','write', [int(test_id)], test_values)

#        if data.get('WARNING', False):
#            params['warning_log'] = '\n'.join(data['WARNING'])
#        if data.get('ERROR', False):
#            params['error_log'] = '\n'.join(data['ERROR'])
#        if data.get('CRITICAL', False):
#            params['critical_log'] = '\n'.join(data['CRITICAL'])
#        if data.get('INFO', False):
#            params['info_log'] = '\n'.join(data['INFO'])
#        if data.get('TEST', False):
#            params['yml_log'] = '\n'.join(data['TEST'])
#        if data.get('TRACEBACK', False):
#            params['traceback_detail'] = '\n'.join(data['TRACEBACK'])
        params['state'] = state
        openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.test.step', 'create', params)

    if not len(step_object.summaries):
        params = {}
        params['name'] = step_name
        params['test_id'] = int(test_id)
        if cmd:
            params['log'] = base64.encodestring( ("No logs for command %s(\"%s\")\n"
                "Command exited with error code %d") % \
                (cmd.remote_command, ' '.join(cmd.args['command']),cmd.rc))
        params['state'] = step_object.summaries.get(step_name,{}).get('state','fail') # No out is bad news.
        openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.test.step','create',params)

    return True

class OpenERPLoggedRemoteCommand(LoggedRemoteCommand):
     def addToLog(self, logname, data):
        if logname in self.logs:
            self.logs[logname].addStdout(data)
        else:
            self.stdio_log = stdio_log = self.addLog("stdio")
            self.useLog(stdio_log, True)

class StdErrRemoteCommand(LoggedRemoteCommand):
    """Variation of LoggedRemoteCommand that separates stderr
    """

    def addStderr(self, data):
        self.logs['stderr'].addStderr(data)

class BqiObserver(LogLineObserver):
    #_line_re = re.compile(...)
    numTests = 0
    finished = False
     
    def outLineReceived(self, line):
        if self.finished:
            return
     
        if line.startswith('bqi.state> set context'):
            testname = line[21:]
            self.numTests += 1
            self.step.setProgress('tests', self.numTests)

class OpenERPTest(LoggingBuildStep):
    name = 'OpenERP-Test'
    flunkOnFailure = True

    def describe(self, done=False,success=False,warn=False,fail=False):
        if done:
            if success:
                return ['Your Commit Passed OpenERP Test !']
            if warn:
                return ['OpenERP Test finished with Warnings !']
            if fail:
                return ['Your Commit Failed to pass OpenERP Test !']
        return self.description

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)

    def __init__(self, workdir=None, dbname=False, addonsdir=None, 
                    netport=None, port=8869,
                    force_modules=None,
                    black_modules=None,
                    test_mode='full',
                    **kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir, dbname=dbname, addonsdir=addonsdir, 
                                netport=netport, port=port, logfiles={},
                                force_modules=(force_modules or []),
                                black_modules=(black_modules or []),
                                test_mode=test_mode)
        self.args = {'port' :port, 'workdir':workdir, 'dbname': dbname, 
                    'netport':netport, 'addonsdir':addonsdir, 'logfiles':{},
                    'force_modules': (force_modules or []),
                    'black_modules': (black_modules or []),
                    'test_mode': test_mode}
        description = ["Performing OpenERP Test..."]
        self.description = description
        self.summaries = {}
        self.build_result = SUCCESS
        
        self.addLogObserver('stdio', BqiObserver())
        self.progressMetrics += ('tests',)

    def start(self):
        #TODO FIX:
        # need to change the static slave path
        self.logfiles = {}
        builddir = self.build.builder.builddir
        full_addons = os.path.normpath(os.getcwd() + '../../openerp_buildbot_slave/build/%s/openerp-addons/'%(builddir))

        # try to find all modules that have changed:
        mods_changed = []
        if self.args['force_modules']:
            mods_changed += filter( lambda x: x != '*', self.args['force_modules'])

        if self.args['force_modules'] and '*' in self.args['force_modules']:
            # Special directive: scan and try all modules
            for modpath in os.listdir(full_addons):
                if (os.path.isfile(os.path.join(full_addons, modpath,'__openerp__.py')) \
                    or os.path.isfile(os.path.join(full_addons, modpath,'__terp__.py'))):
                        mods_changed.append(modpath)
        else:
            more_mods = []
            for chg in self.build.allChanges():
                more_mods.extend(chg.allModules())
            try:
                if self.args['test_mode'] == 'changed-only':
                    raise Exception('Skipped')
                olmods_found = []
                for sbuild in self.build.builder.builder_status.generateFinishedBuilds(num_builds=10):
                    log.msg("Scanning back build %d" % sbuild.getNumber())
                    for sstep in sbuild.getSteps():
                        if sstep.getName() != 'OpenERP-Test':
                            continue
                        # We will try to guess the status from the logs,
                        # just like the web-status does.
                        
                        for slog in sstep.getLogs():
                            if not slog.getName().endswith('.blame'):
                                continue
                            if slog.getName().startswith('bqi.'):
                                continue
                            # Hopefully, the first part of the name is a
                            # module!
                            olmods_found.append(slog.getName().split('.',1)[0])
                        
                        if len(olmods_found):
                            log.msg("Found these modules that failed last time: %s" % \
                                    ','.join(olmods_found))
                            more_mods.extend(olmods_found)
                            break
                
                    if len(olmods_found):  # this loop, too.
                        break
            except Exception, e:
                log.err("Could not figure old failures: %s" % e)
            mods_changed.extend(set(more_mods))

        try:
            todel = []
            for mc in mods_changed:
                if mc in self.args['black_modules']:
                    todel.append(mc)
                    continue
                if not os.path.isdir(os.path.join(full_addons, mc)):
                    todel.append(mc)
                elif not (os.path.isfile(os.path.join(full_addons, mc,'__openerp__.py')) \
                    or os.path.isfile(os.path.join(full_addons, mc,'__terp__.py'))):
                    todel.append(mc)
            for td in todel:
                if td in mods_changed: # prevent double-deletions
                    mods_changed.remove(td)
        except Exception, e:
            log.err("Cannot prune non-addon dirs: %s" % e)
        self.args['logfiles'] = self.logfiles
        
        # The general part of the b-q-i command
        self.args['command']=["../../../base_quality_interrogation.py",
                            "--machine-log=stdout", '--root-path=bin/',
                            '-d', self.args['dbname']]
        if self.args['addonsdir']:
            self.args['command'].append("--addons-path=%s"%(self.args['addonsdir']))
        if self.args['netport']:
            self.args['command'].append("--net_port=%s"%(self.args['netport']))
        if self.args['port']:
            self.args['command'].append("--port=%s"%(self.args['port']))

        for mc in mods_changed:
            # put them in -m so that both install-module and check-quality use them.
            self.args['command'] += [ '-m', str(mc) ]

        # Here goes the test sequence, TODO make custom
        self.args['command'] += ['--', '-drop-db']
        
        self.args['command'] += ['--', 'create-db']
        if len(mods_changed):
            self.args['command'] += ['--', 'install-module']  #+ [ modules...]
            if self.args['test_mode'] not in ('install',):
                self.args['command'] += ['--', 'check-quality' ] # + [modules]
        
        self.args['command'] += ['--', '+drop-db']
        cmd = LoggedRemoteCommand("OpenObjectShell",self.args)
        self.startCommand(cmd)

    def createSummary(self, plog):
        global log
        logs = self.cmd.logs
        buildbotURL = self.build.builder.botmaster.parent.buildbotURL
        bqi_re = re.compile(r'([^\>\|]+)(\|[^\>]+)?\> (.*)$')
        qlog_re = re.compile(r'Module: "(.+)", score: (.*)$')

        logkeys = logs.keys()
        
        if 'stdio' in logkeys:
            # Here we parse the machine-formatted output of b-q-i
            # Hopefully, it should be straightforward.
            lines = logs['stdio'].getText().split('\n')
            
            server_out = []
            server_err = []
            bqi_rest = []
            summaries = {}
            blame_list = []
            bqi_state = 'debug'
            bqi_context = False
            # The order that logs appeared, try to preserve in status.logs
            # May have duplicates.
            log_order = [ 'bqi.rest', 'server.out', 'server.err', ]
            
            while len(lines):
                if not lines[0]:
                    lines = lines[1:]
                    continue
                mr = bqi_re.match(lines[0])
                i = 1
                if not mr:
                    raise RuntimeError("Stray line %r in bqi output!" % lines[0])
                blog = mr.group(1)
                blevel = mr.group(2) or '|20'
                try:
                    blevel = int(blevel[1:])
                except ValueError:
                    # bqi_rest.append('Strange level %r' % blevel)
                    pass
                bmsg = mr.group(3)
                bexc = None
                while lines[i] and lines[i].startswith('+ '):
                    bmsg += '\n'+ lines[i][2:]
                    i += 1
                
                if lines[i] and lines[i].startswith(':@'):
                    # Exception text follows
                    bexc = lines[i][3:]
                    i += 1
                    while lines[i] and lines[i].startswith(':+ '):
                        bexc += '\n' + lines[i][3:]
                        i += 1
                
                lines = lines[i:]
                # Now, process the message we have.
                
                if blog == 'server.stdout':
                    # always log the full log of the server into a
                    # summary
                    server_out.append(bmsg)
                    if bexc:
                        server_out.append(bexc)
                    if bqi_context:
                        log_order.append(bqi_context)
                        summaries[bqi_context]['log'].append(bmsg)
                        if bexc:
                            summaries[bqi_context]['log'].append(bexc)
                elif blog == 'server.stderr':
                    server_err.append(bmsg)
                    if bexc:
                        server_err.append(bexc)
                elif blog == 'bqi.state':
                    # this is a special logger, which expects us to do sth
                    # with its lines = commands
                    bmsg = bmsg.rstrip()
                    if bmsg == 'clear context':
                        bqi_context = False
                    elif bmsg.startswith('set context '):
                        bqi_context = bmsg[len('set context '):]
                        summaries.setdefault(bqi_context, {'state':'pass', 'log': []})
                    else:
                        log.msg("Strange command %r came from b-q-i" % bmsg)
                elif blog == 'bqi.blame':
                    # our precious blame information
                    blame_dict = {}
                    
                    # it is a dict, parse it
                    for bbline in bmsg.split('\n'):
                        if ':' not in bbline:
                            # If some stderr is printed after the blame,
                            # the shell process will falsely attach it to the
                            # bqi.blame line, and hence corrupt it. 
                            # Once we see it, we know it is not bqi.blame content.
                            break
                        bkey, bval = bbline.split(':',1)
                        bkey = bkey.strip()
                        bval = bval.strip()
                        blame_dict[bkey] = bval
                    
                    if 'context' in blame_dict:
                        sumk = blame_dict['context']
                    elif 'module' in blame_dict and 'module-mode' in blame_dict:
                        sumk = '%s.%s' % ( blame_dict['module'], blame_dict['module-mode'])
                    else:
                        sumk = bqi_context
                    if not sumk:
                        sumk = 'bqi.rest'

                    blame_info = '%s' % blame_dict.get('module','')
                    blame_sev = 3 # error
                    if 'module-file' in blame_dict:
                        blame_info += '/%s' % blame_dict['module-file']
                        if 'file-line' in blame_dict:
                            blame_info += ':%s' % blame_dict['file-line']
                            if 'file-col' in blame_dict:
                                blame_info += ':%s' % blame_dict['file-col']
                    if 'severity' in blame_dict:
                        blame_info += '[%s]' % blame_dict['severity']
                        blame_sev = blame_severities.get(blame_dict['severity'], 3)

                    blame_info += ': '
                    if 'Exception type' in blame_dict:
                        blame_info += '%s: ' % blame_dict['Exception type']
                    if 'Message' in blame_dict:
                        blame_info += blame_dict['Message']
                    elif 'Exception' in blame_dict:
                        blame_info += blame_dict['Exception']
                    else:
                        blame_info += 'FAIL'

                    if append_fail(blame_list, [(blame_info, blame_sev),], fmax=5):
                        self.build.build_status.reason = blist2str(blame_list)
                    summaries.setdefault(sumk, { 'log': [] })
                    log_order.append(sumk)
                    summaries[sumk]['state'] = 'fail'
                    summaries[sumk].setdefault('blame', [])
                    summaries[sumk]['blame'].append( (blame_info, blame_sev) )
                elif blog == 'bqi.qlogs':
                    nline = bmsg.index('\n')
                    first_line = bmsg[:nline].strip()
                    html_log = bmsg[nline+1:]
                    
                    mq = qlog_re.match(first_line)
                    if mq:
                        sumk = "%s.test" % mq.group(1)
                        qscore = mq.group(2)
                        log_order.append(sumk)
                        test_res = True
                        try:
                            # Hard-coded criterion!
                            test_res = float(qscore) > 0.30
                        except ValueError:
                            pass
                        summaries.setdefault(sumk, {'state': test_res, 'log':[], })
                        summaries[sumk]['quality_log'] = html_log
                        # TODO use score, too.
                    else:
                        log.err("Invalid first line of quality log: %s" % first_line)
                    
                else:
                    bqi_rest.append(bmsg)
                    if blevel >= logging.ERROR:
                        bqi_state = 'fail'
                    if bexc:
                        bqi_rest.append(bexc)
            
            summaries['server.out'] = { 'state': 'debug', 'log': server_out }
            if server_err:
                summaries['server.err'] = { 'state': 'debug', 'log': server_err }
            if bqi_rest:
                summaries.setdefault('bqi.rest', {}).update({ 'state': bqi_state, 'log': bqi_rest })
                
            self.summaries.update(summaries)
            logkeys.remove('stdio')
            del logs['stdio']
            
        
        if 'stderr' in logkeys:
            self.summaries.setdefault('stderr',{'state': 'unknown', 'log': ''})['log'] += logs['stderr'].getText()
            logkeys.remove('stderr')
            del logs['stderr']
            
        if len(logkeys):
            log.err("Remaining keys %s in logs" % (', '.join(logkeys)))

        for lkey in self.summaries.keys():
            # Make sure log_order has all our summaries
            if lkey not in log_order:
                log_order.append(lkey)

        logs_done = []
        for lkey in log_order:
            if lkey in logs_done:
                continue
            if lkey not in self.summaries:
                # we have the first hard-coded keys, which may not exist
                continue
            logs_done.append(lkey)
            sdict = self.summaries[lkey]

            # Put parsed summaries back in logs, with the correct
            # channel name. Used in web status.
            if sdict.get('state') == 'fail':
                self.build_result = FAILURE
            if sdict.get('blame', False):
                self.addCompleteLog(lkey+'.blame', blist2str(sdict['blame']))
                if not 'log' in sdict:
                    # put an empty log in steps that have a blame,
                    # so that they appear
                    sdict['log'] = [' ',]
            if sdict.get('log', False):
                self.addCompleteLog(lkey, '\n'.join(sdict['log']))
            if 'quality_log' in sdict:
                self.addHTMLLog(lkey + '.qlog', sdict['quality_log'])

    def evaluateCommand(self, cmd):
        res = SUCCESS
        if cmd.rc != 0 or self.build_result == FAILURE:
            # TODO: more results from b-q-i, it has discrete exit codes.
            res = FAILURE
        try:
            create_test_step_log(self, step_name='openerp-test', cmd=cmd)
        except Exception, e:
            log.err("Cannot log result of %s to db: %s" % (cmd, e))
        return res

class OpenObjectBzr(Bzr):
    flunkOnFailure = False
    haltOnFailure = True

    def describe(self, done=False,success=False,warn=False,fail=False):
        branch_short = self.branch.replace('https://launchpad.net/','lp:')
        if done:
            if success:
                return ['Updated branch %s Sucessfully!' % ( branch_short)]
            if warn:
                return ['Updated branch %s with Warnings!' % (branch_short)]
            if fail:
                return ['Updated branch %s Failed!' % (branch_short)]
        return self.description

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)

    def __init__(self, repourl=None, baseURL=None,
                 defaultBranch=None,workdir=None, mode='update', alwaysUseLatest=True, 
                 timeout=40*60, retry=None, **kwargs):
        # LoggingBuildStep.__init__(self, **kwargs)
        Bzr.__init__(self, repourl=repourl, baseURL=baseURL,
                   defaultBranch=defaultBranch,workdir=workdir,mode=mode,alwaysUseLatest=alwaysUseLatest,timeout=timeout,
                   retry=retry, **kwargs)
        self.name = 'bzr-update'
        self.branch = repourl
        self.description = ["updating", "branch %s"%(repourl)]
        self.descriptionDone = ["updated", "branch %s"%(repourl)]
        self.env_info = ''
        self.summaries = {}

    def startVC(self, branch, revision, patch):
        slavever = self.slaveVersion("bzr")
        if not slavever:
            m = "slave is too old, does not know about bzr"
            raise NotImplementedError(m)

        if self.repourl:
        #    assert not branch # we need baseURL= to use branches
            self.args['repourl'] = self.repourl
        else:
            self.args['repourl'] = self.baseURL + self.branch # self.baseURL + branch

        if self.args['repourl'] == branch:
            self.args['revision'] = revision
        else:
            self.args['revision'] = None
        self.args['patch'] = patch

        revstuff = []
        self.description.extend(revstuff)
        self.descriptionDone.extend(revstuff)
        cmd = LoggedRemoteCommand("openobjectbzr", self.args)
        self.startCommand(cmd)

    def createSummary(self, log):
        io = StringIO(log.getText()).readlines()
        summaries = {self.name:{'log': []}}
        counts = {"log": 0}
        for line in io:
            if line.find("ERROR") != -1:
                pos = line.find("ERROR") + len("ERROR")
                line = line[pos:]
                summaries[self.name]["log"].append(line)
                counts["log"] += 1
            else:
                pass
        self.summaries = summaries
        if counts["log"]:
            msg = "".join(summaries[self.name]["log"])
            self.addCompleteLog("Branch Update  : ERROR", msg)
            self.setProperty("Branch Update : ERROR", counts["log"])
        if sum(counts.values()):
            self.setProperty("Branch Update : MessageCount", sum(counts.values()))

    def evaluateCommand(self, cmd):
        state = 'pass'
        for ch, txt in cmd.logs['stdio'].getChunks():
            if ch == 2:
                if txt.find('environment')!= -1:
                    pos = txt.find('environment')
                    self.env_info = txt[pos:]
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE
            state = 'skip'
        self.summaries[self.name]['state'] = state
        create_test_step_log(self, step_name=self.name)
        return res

class OpenObjectSVN(SVN):
    flunkOnFailure = False
    haltOnFailure = True
    def __init__(self, svnurl=None, baseURL=None, defaultBranch=None,
                 directory=None, workdir=None, mode='update',alwaysUseLatest=True,timeout=20*60, retry=None,**kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        SVN.__init__(self, svnurl=svnurl, baseURL=baseURL, defaultBranch=defaultBranch,
                 directory=directory, workdir=workdir, mode=mode, alwaysUseLatest=alwaysUseLatest, timeout=timeout, retry=retry,**kwargs)
        self.name = 'svn-update'
        self.description = ["updating", "branch %s%s"%(baseURL,defaultBranch)]
        self.descriptionDone = ["updated", "branch %s%s"%(baseURL,defaultBranch)]

    def startVC(self, branch, revision, patch):
        svnurl = self.baseURL + self.branch
        if  svnurl == branch:
            pass
        else:
            revision= None
            patch=None
        branch = self.branch
        SVN.startVC(self,self.branch, revision, patch)

# Following Step are used in Migration builder
class StartServer(LoggingBuildStep):
    name = 'start_server'
    flunkOnFailure = False
    def describe(self, done=False,success=False,warn=False,fail=False):
         if done:
            if success:
                return ['Server started Sucessfully !']
            if warn:
                return ['Server started with Warnings !']
            if fail:
                return ['Server Failed !']
         return self.description

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)


    def __init__(self, dbname='test',workdir=None, addonsdir=None, demo=True, lang='en_US', port=8869, netport=8975,**kwargs):

        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(dbname=dbname,workdir=workdir, demo=demo, lang=lang, netport=netport,port=port, addonsdir=addonsdir)
        self.args = {'dbname': dbname,'workdir':workdir, 'netport':netport,'port' : port, 'addonsdir' : addonsdir}
        # Compute defaults for descriptions:
        description = ["Starting server with upgradetion"]
        self.description = description

    def start(self):
        modules=['base']
        s = self.build.getSourceStamp()
        for change in s.changes:
            for f in change.files:
                try:
                    module = f.split('/')[1]
                    if module not in modules:
                        modules.append(module)
                except:
                    pass
        self.args['modules'] = ','.join(modules)
        commands = ['python','bin/openerp-server.py']
        if self.args['addonsdir']:
            commands.append("--addons-path=%s"%(self.args['addonsdir']))
        if self.args['port']:
            commands.append("--port=%s"%(self.args['port']))
        if self.args['netport']:
           self.args['netport'].append("--net_port=%s"%(self.args['netport']))
        if self.args['dbname']:
            commands.append("--database=%s"%(self.args['dbname']))
        commands.append("--update=%s"%(self.args['modules']))
        commands.append("--stop-after-init")

        self.args['command'] = commands

        cmd = LoggedRemoteCommand("OpenObjectShell",self.args)
        self.startCommand(cmd)


#class CreateDB2(CreateDB):
#    def start(self):
#        cmd = LoggedRemoteCommand("create-db",self.args)
#        self.startCommand(cmd)
#
#class InstallModule2(InstallModule):
#    def start(self):
#        s = self.build.getSourceStamp()
#        modules = []
#        for change in s.changes:
#            for f in change.files:
#                try:
#                    module = f.split('/')
#                    if change.branch == 'https://svn.tinyerp.com/be/maintenance':
#                        module = (len(module) > 1) and module[1] or ''
#                    else:
#                        module = module[0]
#                    if module not in modules:
#                        if module not in ('README.txt'):
#                            modules.append(module)
#                except:
#                    pass
#        self.args['modules'] += ','.join(modules)
#        cmd = LoggedRemoteCommand("install-module",self.args)
#        self.startCommand(cmd)


class BzrMerge(LoggingBuildStep):
    name = 'bzr_merge'
    haltOnFailure = True
    def describe(self, done=False,success=False,warn=False,fail=False):
         if done:
            if success:
                return ['Merge Sucessfull !']
            if warn:
                return ['Merge had Warnings !']
            if fail:
                return ['Merge Failed !']
         return self.description

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)


    def __init__(self, branch=None, workdir=None, **kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(branch=branch, workdir=workdir)
        self.args = {'branch': branch,'workdir':workdir}
        # Compute defaults for descriptions:
        self.branch = branch
        description = ["Merging Branch"]
        self.description = description
        self.env_info = ''
        self.summaries = {}

    def start(self):
        s = self.build.getSourceStamp()
        latest_rev_no = False
        for change in s.changes:
            latest_rev_no = change.revision

        self.args['command']=["bzr","merge"]
        if latest_rev_no:
          self.args['command'] += ["-r", str(latest_rev_no)]

        if self.args['branch']:
           self.args['command'].append(self.args['branch'])
        cmd = LoggedRemoteCommand("OpenObjectShell",self.args)
        self.startCommand(cmd)

    def createSummary(self, log):
        counts = {"log": 0}
        summaries = {self.name:{'log': [], 'state':None}}
        io = StringIO(log.getText()).readlines()
        for line in io:
            if line.find("ERROR") != -1:
                pos = line.find("ERROR") + len("ERROR")
                line = line[pos:]
                summaries[self.name]["log"].append(line)
                counts["log"] += 1
            else:
                pass
        self.summaries = summaries
        if counts["log"]:
            msg = "".join(summaries[self.name]["log"])
            self.addCompleteLog("Bzr Merge : ERROR", msg)
            self.setProperty("Bzr Merge : ERROR", counts["log"])
        if sum(counts.values()):
            self.setProperty("Bzr Merge : MessageCount", sum(counts.values()))

    def evaluateCommand(self, cmd):
        state = 'pass'
        for ch, txt in cmd.logs['stdio'].getChunks():
            if ch == 2:
                if txt.find('environment')!= -1:
                    pos = txt.find('environment')
                    self.env_info = txt[pos:]
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE
            state = 'skip'
        self.summaries[self.name]['state'] = state
        create_test_step_log(self, step_name='bzr_merge')
        return res

class BzrRevert(LoggingBuildStep):
    name = 'bzr-revert'
    flunkOnFailure = True
    haltOnFailure = True

    def describe(self, done=False,success=False,warn=False,fail=False):
         if done:
            if success:
                return ['Merge reverted from %s Sucessfully!'%(self.workdir)]
            if warn:
                return ['Merge reverted from %s with Warnings!'%(self.workdir)]
            if fail:
                return ['Merge revert from %s Failed!'%(self.workdir)]
         return self.description

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)


    def __init__(self, workdir=None, **kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir)
        self.args = {'workdir':workdir}
        self.workdir = workdir
        # Compute defaults for descriptions:
        description = ["Reverting Branch"]
        self.description = description
        self.summaries = {}

    def start(self):
        self.args['command']=["bzr","revert"]
        cmd = LoggedRemoteCommand("OpenObjectShell",self.args)
        self.startCommand(cmd)

    def createSummary(self, log):
        counts = {"log":0}
        summaries = {self.name:{'log': [], 'state':None}}
        io = StringIO(log.getText()).readlines()
        for line in io:
            if line.find("ERROR") != -1:
                pos = line.find("ERROR") + len("ERROR")
                line = line[pos:]
                summaries[self.name]["log"].append(line)
                counts["log"] += 1
            else:
                pass
        self.summaries = summaries
        if counts["log"]:
            msg = "".join(summaries[self.name]["log"])
            self.addCompleteLog("Bzr Merge : ERROR", msg)
            self.setProperty("Bzr Merge : ERROR", counts["log"])
        if sum(counts.values()):
            self.setProperty("Bzr Merge : MessageCount", sum(counts.values()))

    def evaluateCommand(self, cmd):
        state = 'pass'
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE
            state = 'fail'
        self.summaries[self.name]['state'] = state
        create_test_step_log(self, res)
        return res

class LintTest(LoggingBuildStep):
    """Step to perform lint-check on changed files
    """
    name = 'Lint test'
    flunkOnFailure = False

    def describe(self, done=False,success=False,warn=False,fail=False):
         if done:
            if success:
                return ['Lint test passed !']
            if warn:
                return ['Lint test has Warnings !']
            if fail:
                return ['Lint test Failed !']
         return self.description

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)


    def __init__(self, workdir=None, **kwargs):

        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir)
        self.args = {'workdir': workdir, }
        # Compute defaults for descriptions:
        description = ["Performing lint check"]
        self.description = description

    def start(self):
        self.args['command']=["../../../file-lint.sh",]
        self.args['command'] += [ str(x) for x in self.build.allFiles()]

        cmd = StdErrRemoteCommand("OpenObjectShell", self.args)
        self.stderr_log = self.addLog("stderr")
        cmd.useLog(self.stderr_log, True)
        self.startCommand(cmd)

class BzrStatTest(LoggingBuildStep):
    """Step to perform lint-check on changed files
    """
    name = 'Bzr stats'
    flunkOnFailure = False

    def describe(self, done=False,success=False,warn=False,fail=False):
         if done:
            if success:
                return ['Bzr stats finished!']
            if warn:
                return ['Warnings at bzr stats !']
            if fail:
                return ['Bzr stats Failed !']
         return self.description

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)


    def __init__(self, workdir=None, **kwargs):

        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir)
        self.args = {'workdir': workdir, }
        # Compute defaults for descriptions:
        description = ["Performing bzr stats"]
        self.description = description

    def start(self):
        self.args['command']=["../../../bzr-diffstat.sh",]

        cmd = StdErrRemoteCommand("OpenObjectShell", self.args)
        self.stderr_log = self.addLog("stderr")
        cmd.useLog(self.stderr_log, True)
        self.startCommand(cmd)


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
