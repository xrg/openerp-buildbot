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
from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS, EXCEPTION
from buildbot.status.builder import TestResult

import os
import re
import logging
from openobject import tools
from openobject.tools import ustr
from twisted.python import log

try:
    import cStringIO
    StringIO = cStringIO.StringIO
except ImportError:
    from StringIO import StringIO

blame_severities =  { 'warning': 1, 'error': 3, 'exception': 4,
            'critical': 8 , 'blocking': 10 }

# map blame severities to status.builder ones
res_severities = { 0: SUCCESS, 1: WARNINGS, 3: FAILURE, 4: EXCEPTION, 8: EXCEPTION, 10: EXCEPTION }

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

ports_pool = None

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

    def get_free_port(self):
        global ports_pool
        return ports_pool.borrow(True)

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)

    def __init__(self, workdir=None, dbname=False, addonsdir=None, 
                    netport=None, port=None,
                    force_modules=None,
                    black_modules=None,
                    test_mode='full',
                    repo_mode='addons',
                    **kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir, dbname=dbname, addonsdir=addonsdir, 
                                netport=netport, port=port, logfiles={},
                                force_modules=(force_modules or []),
                                black_modules=(black_modules or []),
                                repo_mode=repo_mode,
                                test_mode=test_mode)
        self.args = {'port' :port, 'workdir':workdir, 'dbname': dbname, 
                    'netport':netport, 'addonsdir':addonsdir, 'logfiles':{},
                    'force_modules': (force_modules or []),
                    'black_modules': (black_modules or []),
                    'test_mode': test_mode,
                    'repo_mode': repo_mode }
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
        # builddir = self.build.builder.builddir

        global ports_pool
        if not ports_pool:
            # Effectively, the range of these ports will limit the number of
            # simultaneous databases that can be tested
            min_port = self.build.builder.properties.get('min_port',8200)
            max_port = self.build.builder.properties.get('max_port',8299)
            port_spacing = self.build.builder.properties.get('port_spacing',4)
            ports_pool = tools.Pool(iter(range(min_port, max_port, port_spacing)))

        if not self.args.get('addonsdir'):
            if self.build.builder.properties.get('addons_dir'):
                self.args['addonsdir'] = self.build.builder.properties['addons_dir']
            else:
                self.args['addonsdir'] = '../addons/'
        if not self.args.get('port'):
            self.args['port'] = self.get_free_port()
        if not self.args.get('dbname'):
            self.args['dbname'] = self.build.builder.builddir.replace('/', '_')
        if not self.args.get('workdir'):
            self.args['workdir'] = 'server'

        # try to find all modules that have changed:
        mods_changed = []
        if self.args['force_modules']:
            mods_changed += filter( lambda x: x != '*', self.args['force_modules'])

        all_modules = False
        if self.args['force_modules'] and '*' in self.args['force_modules']:
            # Special directive: scan and try all modules
            all_modules = True
        else:
            more_mods = []
            if self.args['repo_mode'] == 'server':
                repo_expr = r'bin/addons/([^/]+)/.+$'
            else:
                repo_expr = r'([^/]+)/.+$'
            for chg in self.build.allChanges():
                more_mods.extend(chg.allModules(repo_expr))
                if not more_mods:
                    log.err("No changed modules located")
            try:
                if self.args['test_mode'] == 'changed-only':
                    raise Exception('Skipped')
                olmods_found = []
                for sbuild in self.build.builder.builder_status.generateFinishedBuilds(num_builds=10):
                    log.msg("Scanning back build %d" % sbuild.getNumber())
                    for sres in sbuild.getTestResults().values():
                        # RFC: should we perform tests for other failures
                        # like flakes etc?
                        if sres.results == SUCCESS:
                            continue
                        if sres.name == ('bqi', 'rest') or sres.name == ('lint', 'rest'):
                            continue

                        olmods_found.append(sres.name[0]) # it's a tuple, easy

                    if len(olmods_found):  # this loop, too.
                        more_mods.extend(olmods_found)
                        log.msg("Found these modules that failed last time: %s" % \
                                ','.join(olmods_found))
                        break #don't look further back in the history
            except Exception, e:
                log.err("Could not figure old failures: %s" % e)
            mods_changed.extend(set(more_mods))

        try:
            todel = []
            for mc in mods_changed:
                if mc in self.args['black_modules']:
                    todel.append(mc)
                    continue
                # We no longer have access to the slave dirs.
                #if not os.path.isdir(os.path.join(full_addons, mc)):
                    #todel.append(mc)
                #elif not (os.path.isfile(os.path.join(full_addons, mc,'__openerp__.py')) \
                    #or os.path.isfile(os.path.join(full_addons, mc,'__terp__.py'))):
                    #todel.append(mc)
            for td in todel:
                if td in mods_changed: # prevent double-deletions
                    mods_changed.remove(td)
        except Exception, e:
            log.err("Cannot prune non-addon dirs: %s" % e)
        self.args['logfiles'] = self.logfiles
        
        # The general part of the b-q-i command
        self.args['command']=["../../../base_quality_interrogation.py",
                            "--machine-log=stdout", '--root-path=bin/',
                            "--homedir=../",
                            '-d', self.args['dbname']]
        if self.args['addonsdir']:
            self.args['command'].append("--addons-path=%s"%(self.args['addonsdir']))
        if self.args['netport']:
            self.args['command'].append("--net_port=%s"%(self.args['netport']))
        if self.args['port']:
            self.args['command'].append("--port=%s"%(self.args['port']))

        if all_modules:
            self.args['command'].append('--all_modules')
        else:
            for mc in set(mods_changed):
                # put them in -m so that both install-module and check-quality use them.
                self.args['command'] += [ '-m', str(mc) ]

        # Here goes the test sequence, TODO make custom
        self.args['command'] += ['--', '-drop-db']
        
        self.args['command'] += ['--', 'create-db']
        if len(mods_changed):
            self.args['command'] += ['--', 'install-module']  #+ [ modules...]
            if self.args['test_mode'] == 'check-quality':
                self.args['command'] += ['--', 'check-quality' ] # + [modules]
        
        self.args['command'] += ['--', '+drop-db']
        cmd = LoggedRemoteCommand("OpenObjectShell",self.args)
        self.startCommand(cmd)

    def createSummary(self, plog):
        global log
        logs = self.cmd.logs
        # buildbotURL = self.build.builder.botmaster.parent.buildbotURL
        bqi_re = re.compile(r'([^\>\|]+)(\|[^\>]+)?\> (.*)$')
        qlog_re = re.compile(r'Module: "(.+)", score: (.*)$')

        def bq2tr(bqi_name):
            return tuple(bqi_name.split('.'))

        logkeys = logs.keys()
        
        # We will be using TestResult()s for the aggregate output of our
        # steps. 
        # We use like: TestResult(name=(bqi-context), results=<num>, 
        #                         text=blist2str(blame),
        #                         logs= {'stdout': out, 'exception': exc } )
        
        if 'stdio' in logkeys:
            # Here we parse the machine-formatted output of b-q-i
            # Hopefully, it should be straightforward.
            lines = logs['stdio'].getText().split('\n')
            
            server_out = []
            server_err = []
            
            quality_logs = {}
            blame_list = []  # for the general results
            bqi_state = 'debug'
            bqi_context = False
            bqi_rest = TestResult(name=('bqi','rest'), text='', results=0, logs={'stdout': []})
            
            t_results=[] # ordered list
            cur_result= None  # The entry of t_results we are in, when bqi_context
            
            # The order that logs appeared, try to preserve in status.logs
            # May have duplicates. (less used after last refactoring)
            log_order = [ 'server.out', 'server.err', ]
            
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
                        cur_result.logs['stdout'].append(bmsg) # or += ?
                        if bexc:
                            cur_result.logs.setdefault('exception',[]).append(bexc)
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
                        cur_result = None
                    elif bmsg.startswith('set context '):
                        bqi_context = bmsg[len('set context '):]
                        cur_result = None
                        for tr in t_results:
                            if tr.name == bq2tr(bqi_context):
                                cur_result = tr
                                break
                        if not cur_result:
                            cur_result = TestResult(name=bq2tr(bqi_context),
                                        results=SUCCESS,
                                        text='', logs={'stdout': []})
                            t_results.append(cur_result)
                            cur_result.blames = []
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

                    if True:
                        # note that we don't affect bqi_context, cur_result here
                        cur_r = None
                        for tr in t_results:
                            if tr.name == bq2tr(sumk):
                                cur_r = tr
                                break
                        if not cur_r:
                            cur_r = TestResult(name=bq2tr(sumk),
                                        results=SUCCESS,
                                        text='', logs={'stdout': []})
                            t_results.append(cur_r)
                            cur_r.blames = []
                        cur_r.blames.append((blame_info, blame_sev))
                        
                elif blog == 'bqi.qlogs':
                    nline = bmsg.index('\n')
                    first_line = bmsg[:nline].strip()
                    html_log = bmsg[nline+1:]
                    
                    mq = qlog_re.match(first_line)
                    if mq:
                        # FIXME: 
                        sumk = mq.group(1)
                        qscore = mq.group(2)
                        #log_order.append(sumk)
                        test_res = True
                        try:
                            # Hard-coded criterion!
                            test_res = float(qscore) > 0.30
                        except ValueError:
                            pass
                        quality_logs[sumk] = html_log
                        # TODO use score, too.
                    else:
                        log.err("Invalid first line of quality log: %s" % first_line)
                    
                else:
                    bqi_rest.logs['stdout'].append(bmsg)
                    if blevel >= logging.ERROR:
                        bqi_rest.results = FAILURE
                    if bexc:
                        bqi_rest.logs['stdout'].append(bexc)

        if 'stdio' in logkeys:
            logkeys.remove('stdio')
        if len(logkeys):
            log.err("Remaining keys %s in logs" % (', '.join(logkeys)))

        #cleanup t_results
        for tr in t_results:
            sev = 0
            if tr.blames:
                tr.text = blist2str(tr.blames)
                sev = tr.blames[0][1]
            if tr.results < res_severities[sev]:
                tr.results = res_severities[sev]
            if self.build_result < tr.results:
                self.build_result = tr.results
            for lk in tr.logs:
                if isinstance(tr.logs[lk], list):
                    tr.logs[lk] = '\n'.join(tr.logs[lk])

            # and, after it's clean..
            self.build.build_status.addTestResult(tr)

        for qkey in quality_logs:
            self.addHTMLLog(qkey + '.qlog', quality_logs[qkey])

        build_id = self.build.requests[0].id # FIXME when builds have their class
        
        self.build.builder.db.saveTResults(build_id, self.name,
                                            self.build_result, t_results)
        
    def evaluateCommand(self, cmd):
        global ports_pool
        res = SUCCESS
        if cmd.rc != 0:
            # TODO: more results from b-q-i, it has discrete exit codes.
            res = FAILURE
        if self.build_result > res:
            res = self.build_result
        if self.args['port']:
            try:
                ports_pool.free(self.args['port'])
            except RuntimeError, e:
                log.err("%s" % e)

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
        # TODO: make sure we get the result
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
        # TODO: send the result to the db
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
        # TODO: send the result to the db
        return res

class LintTest(LoggingBuildStep):
    """Step to perform lint-check on changed files
    """
    name = 'Lint test'
    flunkOnFailure = False
    known_strs = [ (r'Pyflakes failed for: (.+)$', FAILURE ),
                   (r'Please correct warnings for (.+)$', WARNINGS),
                   (r'Not ready to commit: (.+)$', FAILURE),
                   (r'You used tabs in (.+)\. Please expand them', WARNINGS),
                   (r'XmlLint failed for: (.+)$', FAILURE),
                   # (r'No lint for (.+)$', SUCCESS ),
                   # Must come last:
                   (r'([^:]+):[0-9]+: .+$', SUCCESS ),
                ]

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


    def __init__(self, workdir=None, repo_mode='addons', **kwargs):

        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir, repo_mode=repo_mode)
        self.args = {'workdir': workdir, 'repo_mode': repo_mode }
        # Compute defaults for descriptions:
        description = ["Performing lint check"]
        self.description = description
        self.known_res = []
        self.build_result = SUCCESS
        for kns in self.known_strs:
            self.known_res.append((re.compile(kns[0]), kns[1]))

    def start(self):
        self.args['command']=["../../../file-lint.sh",]
        self.args['command'] += [ str(x) for x in self.build.allFiles()]

        cmd = StdErrRemoteCommand("OpenObjectShell", self.args)
        self.stderr_log = self.addLog("stderr")
        cmd.useLog(self.stderr_log, True)
        self.startCommand(cmd)

    def createSummary(self, log):
        """ Try to read the file-lint.sh output and parse results
        """
        severity = SUCCESS
        if self.args['repo_mode'] == 'server':
            repo_expr = r'bin/addons/([^/]+)/.+$'
        else:
            repo_expr = r'([^/]+)/.+$'

        t_results= {}
        
        repo_re = re.compile(repo_expr)
        for line in StringIO(log.getText()).readlines():
            for rem, sev in self.known_res:
                m = rem.match(line)
                if not m:
                    continue
                fname = m.group(1)
                if sev > severity:
                    severity = sev
                mf = repo_re.match(fname)
                if mf:
                    module = (mf.group(1), 'lint')
                else:
                    module = ('lint', 'rest')
                
                if module not in t_results:
                    t_results[module] = TestResult(name=module,
                                        results=SUCCESS,
                                        text='', logs={'stdout': u''})
                if t_results[module].results < sev:
                    t_results[module].results = sev
                if line.endswith('\r\n'):
                    line = line[:-2] + '\n'
                elif not line.endswith('\n'):
                    line += '\n'
                if sev > SUCCESS:
                    t_results[module].text += ustr(line)
                else:
                    t_results[module].logs['stdout'] += ustr(line)
                
                break # don't attempt more matching of the same line

        # use t_results
        for tr in t_results.values():
            if self.build_result < tr.results:
                self.build_result = tr.results
            # and, after it's clean..
            self.build.build_status.addTestResult(tr)

        self.build_result = severity

        build_id = self.build.requests[0].id # FIXME when builds have their class
        # self.descriptionDone = self.descriptionDone[:]
        self.build.builder.db.saveTResults(build_id, self.name,
                                            self.build_result, t_results.values())

    def evaluateCommand(self, cmd):
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE
        if self.build_result > res:
            res = self.build_result
        return res

class BzrStatTest(LoggingBuildStep):
    """Step to gather statistics of changed files
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
        self.args = {'workdir': workdir }
        # Compute defaults for descriptions:
        description = ["Performing bzr stats"]
        self.description = description
        self.build_result = SUCCESS

    def start(self):
        self.args['command']=["../../../bzr-diffstat.sh",]

        cmd = StdErrRemoteCommand("OpenObjectShell", self.args)
        self.stderr_log = self.addLog("stderr")
        cmd.useLog(self.stderr_log, True)
        self.startCommand(cmd)

    def createSummary(self, log):
        """ Try to read the file-lint.sh output and parse results
        """
        file_stats = {}

        for line in StringIO(log.getText()).readlines():
            if line == 'INSERTED,DELETED,MODIFIED,FILENAME':
                continue
            li,ld, lm, fname = line.rstrip().split(',')
            file_stats[fname] = {'lines_add': li, 'lines_rem':ld }
        
        commits = self.build.allChanges()
        self.build.builder.db.saveStatResults(commits, file_stats )

    def evaluateCommand(self, cmd):
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE
        if self.build_result > res:
            res = self.build_result
        return res

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
