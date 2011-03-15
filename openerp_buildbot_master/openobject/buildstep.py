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
# from buildbot.steps.shell import ShellCommand
from buildbot.process.buildstep import LoggingBuildStep, LoggedRemoteCommand, LogLineObserver
from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS, EXCEPTION, SKIPPED
from buildbot.status.builder import TestResult
from buildbot.steps.master import MasterShellCommand
from buildbot.process.properties import WithProperties
from buildbot.status.builder import Results as status_Results

import os
import re
import logging
from openobject import tools
from openobject.tools import ustr
from twisted.python import log
from twisted.internet import defer
from openobject.lp_poller import MS_Service

try:
    import cStringIO
    StringIO = cStringIO.StringIO
except ImportError:
    from StringIO import StringIO

blame_severities =  { 'pywarn': 1, 'warning': 2, 'error': 3, 'exception': 4,
            'critical': 8 , 'blocking': 10 }

# map blame severities to status.builder ones
res_severities = { 0: SUCCESS, 1: SUCCESS, 2: WARNINGS, 3: FAILURE, 
                4: EXCEPTION, 8: EXCEPTION, 10: EXCEPTION }

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
        fo = fi
        while fo < len(flist) and flist[fo][1] == bsev:
            if flist[fo] == (blame, bsev):
                blame = None
        if blame is None:
            continue
        
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
dbnames_pool = None

class unique_dbnames(object):
    """ A simple pseydo-iterator that will produce unique database names
    """
    def __init__(self):
        self.__count = 0
        self.__uniq = hex(id(self))[-4:]

    def next(self):
        self.__count += 1
        return 'test-db-%s%x' % (self.__uniq, self.__count)

class OpenERPTest(LoggingBuildStep):
    name = 'OpenERP-Test'
    flunkOnFailure = True
    warnOnWarnings = True

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

    def _get_random_dbname(self, props):
        global dbnames_pool
        return dbnames_pool.borrow(True)

    #def _get_builddir(self, props):
    #    # must be a function because it shall be rendered late, at start()
    #    return self.build.builder.builddir.replace('/', '_')

    def __init__(self, workdir=None, dbname=False, addonsdir=None, 
                    netport=None, port=None, ftp_port=None,
                    force_modules=None,
                    black_modules=None,
                    test_mode='full',
                    server_series='v600',
                    do_warnings=None, lang=None, debug=False,
                    repo_mode=WithProperties('%(repo_mode)s'),
                    **kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        if isinstance(black_modules, basestring):
            black_modules = black_modules.split(' ')
        if isinstance(force_modules, basestring):
            force_modules = force_modules.split(' ')
        if not dbname:
            dbname = '%(random)s'
        if isinstance(dbname, basestring) and '%' in dbname:
            dbname = WithProperties(dbname, random=self._get_random_dbname)

        self.addFactoryArguments(workdir=workdir, dbname=dbname, addonsdir=addonsdir, 
                                netport=netport, port=port, ftp_port=ftp_port, logfiles={},
                                force_modules=(force_modules or []),
                                black_modules=(black_modules or []),
                                do_warnings=do_warnings, lang=lang,
                                repo_mode=repo_mode,
                                debug=debug,
                                test_mode=test_mode,
                                server_series=server_series)
        self.args = {'port' :port, 'workdir':workdir, 'dbname': dbname, 
                    'netport':netport, 'addonsdir':addonsdir, 'logfiles':{},
                    'ftp_port': ftp_port,
                    'force_modules': (force_modules or []),
                    'black_modules': (black_modules or []),
                    'do_warnings': do_warnings, 'lang': lang,
                    'test_mode': test_mode, 'server_series': server_series,
                    'repo_mode': repo_mode, 'debug': debug }
        description = ["Performing OpenERP Test..."]
        self.description = description
        self.summaries = {}
        self.build_result = SUCCESS

        self.addLogObserver('stdio', BqiObserver())
        self.progressMetrics += ('tests',)

    def start(self):
        self.logfiles = {}
        global ports_pool, dbnames_pool
        builder_props = self.build.getProperties()
        if not ports_pool:
            # Effectively, the range of these ports will limit the number of
            # simultaneous databases that can be tested
            min_port = builder_props.getProperty('min_port',8200)
            max_port = builder_props.getProperty('max_port',8299)
            port_spacing = builder_props.getProperty('port_spacing',4)
            ports_pool = tools.Pool(iter(range(min_port, max_port, port_spacing)))

        if not dbnames_pool:
            dbnames_pool = tools.Pool(unique_dbnames())

        if not self.args.get('addonsdir'):
            if builder_props.getProperty('addons_dir'):
                self.args['addonsdir'] = builder_props['addons_dir']
            else:
                self.args['addonsdir'] = '../addons/'
        if not self.args.get('port'):
            self.args['port'] = self.get_free_port()
        if self.args.get('ftp_port') is None: # False will skip the arg
            self.args['ftp_port'] = self.get_free_port()
        self.args['dbname'] = builder_props.render(self.args.get('dbname', False))
        assert self.args['dbname'], "I can't go on without a dbname!"
        if not self.args.get('workdir'):
            self.args['workdir'] = 'server'
        
        self.args['repo_mode'] = builder_props.render(self.args.get('repo_mode', ''))

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
                if self.args['server_series'] == 'srv-lib':
                    repo_expr = r'openerp/addons/([^/]+)/.+$'
                else:
                    repo_expr = r'bin/addons/([^/]+)/.+$'
            else:
                if self.args['repo_mode'] != 'addons':
                    log.msg("Repo mode is \"%s\"" % self.args['repo_mode'])
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
                    if sbuild.getResult() == SUCCESS:
                        break
                    for sres in sbuild.getTestResults().values():
                        # RFC: should we perform tests for other failures
                        # like flakes etc?
                        if sres.results == SUCCESS:
                            continue
                        if sres.name == ('bqi', 'rest') or sres.name == ('lint', 'rest') or \
                                ( len(sres.name) == 2 and sres.name[1] == 'lint'):
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
        root_path = 'bin/'
        if self.args['server_series'] == 'srv-lib':
            root_path = './'
        self.args['command']=["../../../base_quality_interrogation.py",
                            "--machine-log=stdout", '--root-path='+root_path,
                            "--homedir=../", "-c", '~/.openerp-bqirc-bbot',
                            '--server-series=%s' % self.args['server_series'],
                            '-d', self.args['dbname']]
        if self.args.get('do_warnings', False):
            self.args['command'].append('-W%s' % self.args.get('do_warnings'))
        if self.args.get('debug', False):
            self.args['command'].append('--debug')
        if self.args['addonsdir']:
            self.args['command'].append("--addons-path=%s"%(self.args['addonsdir']))
        if self.args['netport']:
            self.args['command'].append("--net_port=%s"%(self.args['netport']))
        if self.args['port']:
            self.args['command'].append("--port=%s"%(self.args['port']))
        if self.args['ftp_port']:
            self.args['command'].append("--ftp-port=%s"%(self.args['ftp_port']))

        if self.args['lang']:
            self.args['command'].append("--language=%s"%(self.args['lang']))

        if all_modules:
            self.args['command'].append('--all-modules')
            if self.args['black_modules']:
                self.args['command'].extend(['--black-modules', ' '.join(self.args['black_modules'])])
        else:
            for mc in set(mods_changed):
                # put them in -m so that both install-module and check-quality use them.
                self.args['command'] += [ '-m', str(mc) ]

        # Here goes the test sequence, TODO make custom
        self.args['command'] += ['--', '-drop-db']
        
        self.args['command'] += ['--', 'create-db']
        if len(mods_changed) or all_modules:
            self.args['command'] += ['--', 'install-module']  #+ [ modules...]
            if self.args['test_mode'] == 'check-quality':
                self.args['command'] += ['--', 'check-quality' ] # + [modules]
            elif self.args['test_mode'] == 'check-fvg':
                self.args['command'] += ['--', 'fields-view-get' ]
        
        self.args['command'] += ['--', '+drop-db']
        self.args['env'] = { 'SSH_AGENT_PID': None, 'SSH_AUTH_SOCK': None, 
                            'SSH_CLIENT': None, 'SSH_CONNECTION': None,
                            'SSH_TTY': None }
        cmd = LoggedRemoteCommand("OpenObjectShell",self.args)
        self.startCommand(cmd)

    def createSummary(self, plog):
        global log
        logs = self.cmd.logs
        bqi_num_modules = None
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
                    elif bmsg.startswith('set num_modules'):
                        bqi_num_modules = int(bmsg[16:])
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
                        if blame_dict.get('module', False):
                            blame_info += '/'
                        blame_info += '%s' % blame_dict['module-file']
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
                        if blame_sev >= 3 or ((blame_info, blame_sev) not in cur_r.blames):
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

        if bqi_num_modules:
            self.setProperty('num_modules', bqi_num_modules)

        try:
            orm_id = self.getProperty('orm_id') or '?'
        except KeyError:
            orm_id = '?'

        if False and self.build_result == SUCCESS:
            self.setProperty('failure_tag', 'openerp-buildsuccess-%s-%s' % \
                            (orm_id, build_id) )

        if self.build_result == FAILURE:
            # Note: We only want to tag on failure, not on exception
            # or skipped, which means buildbot (and not the commmit) failed
            self.setProperty('failure_tag', 'openerp-buildfail-%s-%s' % \
                            (orm_id, build_id) )

    def evaluateCommand(self, cmd):
        global ports_pool, dbnames_pool
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
        if self.args['ftp_port']:
            try:
                ports_pool.free(self.args['ftp_port'])
            except RuntimeError, e:
                log.err("%s" % e)

        try:
            if 'test-db-' in self.args['dbname']:
                dbnames_pool.free(self.args['dbname'])
        except RuntimeError, e:
            log.err("%s" % e)
        return res

class OpenObjectBzr(Bzr):
    flunkOnFailure = False
    haltOnFailure = True
    warnOnWarnings = True
    warnOnFailure = True

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

    def __init__(self, repourl=None, baseURL=None, proxy_url=None,
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
        self.args['proxy_url'] = proxy_url
        self.addFactoryArguments(proxy_url=proxy_url)
        self.env_info = ''
        self.summaries = {}
        self.build_result = SUCCESS

    def computeSourceRevision(self, changes):
        """Return the one of changes that we need to consider.
        
        Unlike the parent Bzr algorithm, we do not want to have
        the maximum revno as the "master" change here.
        Our convention is that changes[1] is the master one, 
        changes[0] needs to be merged in.
        
        Typically we only need the first of the changes list.
        To be reviewed, if the criterion should be the repourl
        or the branch of each change
        """
        if not changes:
            return None
        return changes[-1].revision or changes[-1].parent_revno

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

        if not self.alwaysUseLatest:
            if not self.args['repourl'].endswith(branch):
                log.err("Repo url %s != %s" % (self.args['repourl'], branch))
            self.args['revision'] = revision
            self.setProperty('branch_url', self.args['repourl'])
            self.setProperty('revision_hash', revision) # FIXME
        else:
            self.args['revision'] = None
        self.args['patch'] = patch
        
        if self.args.get('proxy_url'):
            self.args['repourl'] = self.args['proxy_url']

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
            self.addCompleteLog("Branch Update: ERROR", msg)
            self.setProperty("Branch Update: ERROR", counts["log"])
            self.build_result = FAILURE
        if sum(counts.values()):
            self.setProperty("Branch Update: MessageCount", sum(counts.values()))

    def evaluateCommand(self, cmd):
        state = 'pass'
        for ch, txt in cmd.logs['stdio'].getChunks():
            if ch == 2:
                if txt.find('environment')!= -1:
                    pos = txt.find('environment')
                    self.env_info = txt[pos:]
        res = self.build_result
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
    warnOnWarnings = True

    known_strs = [ (r'Text conflict in (.+)$', FAILURE ),
                   (r'Conflict adding file (.+)\. +Moved.*$', FAILURE),
                   (r'Contents conflict in (.+)$', FAILURE),
                   (r'Conflict because (.+) is not versioned, but has versioned children\.', FAILURE),
                   (r'Conflict adding files to (.+)\.  Created directory\.', FAILURE),
                   (r'Conflict: can\'t delete (.+) because it is not empty\.  Not deleting\.', FAILURE),
                   (r'Path conflict: (.+) / ', FAILURE),
                   (r'Conflict moving (.+) into .+\.  Cancelled move.', FAILURE),
                   # (r'No lint for (.+)$', SUCCESS ),
                   # Must come last:
                   (r'([^:]+):[0-9]+: .+$', SUCCESS ),
                ]

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
        self.known_res = []
        self.build_result = SUCCESS
        for kns in self.known_strs:
            self.known_res.append((re.compile(kns[0]), kns[1]))

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
        """ Try to read the bzr merge output and parse results
        """
        severity = SUCCESS
        if self.args['workdir'] == 'server':
            repo_expr = r'(?:bin|openerp)/addons/([^/]+)/.+$'
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
                    module = (mf.group(1), 'merge')
                else:
                    module = ('merge', 'rest')
                
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

        if severity >= FAILURE:
            try:
                orm_id = self.getProperty('orm_id') or '?'
            except KeyError:
                orm_id = '?'
            self.setProperty('failure_tag', 'openerp-mergefail-%s-%s' % \
                                (orm_id, build_id) )
        else:
            self.setProperty('need_commit', 't')

    def evaluateCommand(self, cmd):
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE
        if self.build_result > res:
            res = self.build_result
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


    def __init__(self, workdir=WithProperties('%(repo_mode)s'), **kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir)
        self.args = {'workdir':workdir}
        self.workdir = workdir
        # Compute defaults for descriptions:
        description = ["Reverting Branch"]
        self.description = description
        self.summaries = {}

    def start(self):
        builder_props = self.build.getProperties()
        self.args['workdir'] = builder_props.render(self.args.get('workdir', ''))
        self.args['command']=["bzr","revert", '-q', '--no-backup']
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
    warnOnFailure = True

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


    def __init__(self, workdir=WithProperties('%(repo_mode)s'), 
                    repo_mode=WithProperties('%(repo_mode)s'),
                    strict=False, **kwargs):

        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir, repo_mode=repo_mode, strict=strict)
        self.args = {'workdir': workdir, 'repo_mode': repo_mode, 'stict': strict }
        # Compute defaults for descriptions:
        description = ["Performing lint check"]
        self.description = description
        self.known_res = []
        self.build_result = SUCCESS
        for kns in self.known_strs:
            self.known_res.append((re.compile(kns[0]), kns[1]))
        if self.args.get('strict', False):
            self.haltOnFailure = True

    def start(self):
        self.args['command']=["../../../file-lint.sh",]
        self.args['command'] += [ str(x) for x in self.build.allFiles()]
        builder_props = self.build.getProperties()
        self.args['workdir'] = builder_props.render(self.args.get('workdir', ''))
        self.args['repo_mode'] = builder_props.render(self.args.get('repo_mode', ''))
        self.args['env'] = { 'SSH_AGENT_PID': None, 'SSH_AUTH_SOCK': None, 
                            'SSH_CLIENT': None, 'SSH_CONNECTION': None,
                            'SSH_TTY': None }
        cmd = StdErrRemoteCommand("OpenObjectShell", self.args)
        self.stderr_log = self.addLog("stderr")
        cmd.useLog(self.stderr_log, True)
        self.startCommand(cmd)

    def createSummary(self, log):
        """ Try to read the file-lint.sh output and parse results
        """
        severity = SUCCESS
        if self.args['repo_mode'] == 'server':
            repo_expr = r'(?:bin|openerp)/addons/([^/]+)/.+$'
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

        if severity >= FAILURE:
            try:
                orm_id = self.getProperty('orm_id') or '?'
            except KeyError:
                orm_id = '?'
            self.setProperty('failure_tag', 'openerp-buildfail-%s-%s' % \
                                (orm_id, build_id) )

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
    warnOnFailure = False

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


    def __init__(self, workdir=WithProperties('%(repo_mode)s'), **kwargs):

        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir)
        self.args = {'workdir': workdir }
        # Compute defaults for descriptions:
        description = ["Performing bzr stats"]
        self.description = description
        self.build_result = SUCCESS

    def start(self):
        self.args['command']=["../../../bzr-diffstat.sh",]
        builder_props = self.build.getProperties()
        self.args['workdir'] = builder_props.render(self.args.get('workdir', ''))
 
        cmd = StdErrRemoteCommand("OpenObjectShell", self.args)
        self.stderr_log = self.addLog("stderr")
        cmd.useLog(self.stderr_log, True)
        self.startCommand(cmd)

    def createSummary(self, slog):
        """ Try to read the file-lint.sh output and parse results
        """
        file_stats = {}

        try:
            for line in StringIO(slog.getText()).readlines():
                if line == 'INSERTED,DELETED,MODIFIED,FILENAME':
                    continue
                li,ld, lm, fname = line.rstrip().split(',')
                file_stats[fname] = {'lines_add': li, 'lines_rem':ld }
        except Exception, e:
            log.err("Problem in parsing the stats: %s" % e)
        
        commits = self.build.allChanges()
        self.build.builder.db.saveStatResults(commits, file_stats )

    def evaluateCommand(self, cmd):
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE
        if self.build_result > res:
            res = self.build_result
        return res

class BzrCommitStats(LoggingBuildStep):
    """Step to gather statistics of changed files
    """
    name = 'Bzr commit stats'
    flunkOnFailure = False
    warnOnWarnings = False

    def __init__(self, workdir=WithProperties('%(repo_mode)s'), **kwargs):

        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir)
        self.args = {'workdir': workdir }
        # Compute defaults for descriptions:
        description = ["Performing bzr stats"]
        self.description = description
        self.build_result = SUCCESS
        self.changeno = None

    def start(self):
        self.args['command']=["bzr","stats", "--output-format=csv", "--quiet",
                    "--rows=author,commits,files,lineplus,lineminus"]
        builder_props = self.build.getProperties()
        self.args['workdir'] = builder_props.render(self.args.get('workdir', ''))
        
        change = self.build.allChanges()[0]
        self.changeno = change.number
        self.args['command'] += [ '-r', change.hash]
        cmd = StdErrRemoteCommand("OpenObjectShell", self.args)
        self.stderr_log = self.addLog("stderr")
        cmd.useLog(self.stderr_log, True)
        self.startCommand(cmd)

    def createSummary(self, slog):
        """ Try to read the file-lint.sh output and parse results
        """
        cstats = {}

        cid = self.changeno
        try:
            for line in StringIO(slog.getText()).readlines():
                line = line.strip()
                if not line:
                    continue
                if not ',' in line:
                    log.err("Line is not csv: %r" % line)
                    continue
                aut, coms, cfil, ladd, lrem = line.split(',')
                if aut == 'Total':
                    continue
                cstats.update({ 'author': aut, 'commits': coms, 'count_files': cfil,
                                    'lines_add': ladd, 'lines_rem': lrem })
        except Exception, e:
            log.err("Cannot parse commit stats: %s" % e)
        
        self.build.builder.db.saveCStats(cid, cstats)
        self.description = "Commit stats calculated"

    def evaluateCommand(self, cmd):
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE
        if self.build_result > res:
            res = self.build_result
        return res

class BzrTagFailure(MasterShellCommand):
    """ Put a bzr tag on a commit that failed the OpenERP tests
    
    It should run on the master, because only that one may have a key
    to upload Launchpad tags.
    
    This step has reverse logic, ie. it will only run when previous
    steps have failed (it checks itself).
    
    In order to avoid overriding things in this class, we expect the 
    previous commands (OpenERPTest, LintTest) to have placed some
    properties at the build, for us.
    """
    
    name = "Bzr Tag Failures"
    flunkOnFailure = False
    warnOnFailure = False
    alwaysRun = True
    
    def __init__(self, command=False, **kwargs):
        if not command:
            command = ['bzr', 'tag', '-q', 
                    '-d', WithProperties("%(branch_url)s"),
                    '-r', WithProperties('%(revision_hash)s'),
                    WithProperties('%(failure_tag)s') ]
        MasterShellCommand.__init__(self, command, **kwargs)

    def doStepIf(self, *args):
        """ Check if this step needs to run
        """
        try:
            if self.build.getProperty('failure_tag'):
                return True
        except KeyError:
            return False
        except Exception, e:
            print "exc:", e
        return False


class ProposeMerge(LoggingBuildStep):
    """ If this commit has built, ask to merge into another branch
    
        This step must be setup /after/ the test/build steps, when everything
        has worked right. It will then do no more than register the current
        commit as a candidate for merging into another branch.
        
        If watch_lp is True, then the proposal will only happen if it's also
        registered on LP
    """
    name = 'Merge Request'
    flunkOnFailure = False
    warnOnFailure = False

    def __init__(self, target_branch, workdir=WithProperties('%(repo_mode)s'), 
            watch_lp=False, alt_branch=None, **kwargs):

        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(target_branch=target_branch, workdir=workdir, watch_lp=watch_lp, alt_branch=alt_branch)
        self.args = {'target_branch': target_branch, 'workdir': workdir, 'watch_lp': watch_lp, 'alt_branch': alt_branch }
        # Compute defaults for descriptions:
        description = ["Requesting merge"]
        self.description = description
        self.build_result = SUCCESS


    def doStepIf(self, *args):
        """ Check if this step needs to run
        """
        try:
            if self.build.getProperty('failure_tag'):
                return False
            if self.build.result >= FAILURE:
                return False
        except KeyError:
            return True
        except Exception, e:
            print "exc:", e
        return True

    def start(self):
        builder_props = self.build.getProperties()
        self.args['workdir'] = builder_props.render(self.args.get('workdir', ''))
        change = self.build.allChanges()[-1]
        self.changeno = change.number
        if self.args['watch_lp']:
            try:
                lp = MS_Service.get_LP()
                branch_url = self.build.allChanges()[0].branch
                if not branch_url.startswith('lp:'):
                    raise ValueError("This is not a launchpad branch")
                # branch_url = branch_url.replace('lp:~', 'lp://staging/~')
                tb_url = self.args['target_branch']
                lp_branch = lp.branches.getByUrl(url=branch_url)
                if not lp_branch:
                    log.err("Cannot locate branch %s in Launchpad" % branch_url)
                    raise KeyError(branch_url)
                for mp in lp_branch.landing_targets:
                    if mp.queue_status not in ['Work in progress', 'Needs review', 'Needs review', 'Needs Information']:
                        continue
                    if self.args['alt_branch'] == '*':
                        break
                    if mp.target_branch.bzr_identity in (tb_url, self.args['alt_branch']):
                        break
                else:
                    # Branch doesn't have a merge proposal!
                    return SKIPPED

            except Exception, e:
                log.err("Something has gone bad, cannot watch LP: %s" % e)
            
        res = self.build.builder.db.requestMerge(commit=change.number, 
                        target=self.args['target_branch'], target_path=self.args['workdir'])
        if not res:
            # could not request
            self.build_result = FAILURE
            self.description = 'Could not request merge'
            self.finished(FAILURE)
        
        if isinstance(res, dict) and res.get('trigger'):
            for sched in self.build.builder.botmaster.master.allSchedulers():
                if res['trigger'] in sched.builderNames:
                    d = sched.run()
                    d.addCallback(lambda x: self.finished(SUCCESS))
                    return d
        self.finished(SUCCESS)

class MergeToLP(ProposeMerge):
    """ Send the merge results to a corresponding LP merge
    
        Note that this step will be placed *after* all the others, not before,
        like the ProposeMerge.
    """
    name = 'Update Merge Proposal'
    flunkOnFailure = False
    haltOnFailure = False
    warnOnWarnings = False
    alwaysRun = True
    status_mappings = { SUCCESS: ('Approve', 'The code seems able to be merged'), 
                WARNINGS: ('Needs Fixing', 'The code may be merged, but some warning points could be improved'),
                EXCEPTION: ('Abstain', 'Buildbot was not able to test this merge proposal'),
                FAILURE: ('Disapprove', 'Do not merge this, the tests of Buildbot have failed!'),
                }

    def __init__(self, target_branch=None, **kwargs):
        ProposeMerge.__init__(self, target_branch=target_branch, **kwargs)

    def doStepIf(self, *args):
        return True

    def start(self):
        builder_props = self.build.getProperties()
        self.args['workdir'] = builder_props.render(self.args.get('workdir', ''))
        changes = self.build.allChanges()
        
        if self.build.result not in self.status_mappings:
            self.description = 'No status for %r' % self.build.result
            return SKIPPED
        
        try:
            lp = MS_Service.get_LP()
            branch_url = changes[0].branch
            if not branch_url.startswith('lp:'):
                raise ValueError("This is not a launchpad branch")
            tb_url = None
            if len(changes) > 1:
                tb_url = changes[-1].branch
            assert branch_url != tb_url
            lp_branch = lp.branches.getByUrl(url=branch_url)
            if not lp_branch:
                raise KeyError(branch_url)
            sm = self.status_mappings[self.build.result]
            self.description = "No proposal for branch"
            for mp in lp_branch.landing_targets:
                if mp.queue_status not in ['Work in progress', 'Needs review', 'Needs Fixing', 'Needs Information']:
                    continue
                if self.args['alt_branch'] != '*' \
                        and mp.target_branch.bzr_identity not in (tb_url, self.args['target_branch'], self.args['alt_branch']):
                    continue
                log.msg("attaching information to %s" % mp)
                mp.createComment(vote=sm[0], subject=sm[1], content=self.build.build_status.reason)
                self.description = "Commented a Proposal"
        
        except Exception, e:
            log.err("Something has gone bad, cannot update LP: %s" % e)
            self.finished(FAILURE)
            return

        self.finished(SUCCESS)

class BzrPerformMerge(BzrMerge):
    """If there is a merge_id in the current commit, merge that
    """
    name = 'bzr-perform-merge'
    haltOnFailure = True
    flunkOnFailure = True
    warnOnWarnings = True


    def __init__(self, branch=None, workdir=WithProperties('%(repo_mode)s'), proxied_bzrs={}, **kwargs):
        BzrMerge.__init__(self, **kwargs)
        self.addFactoryArguments(branch=branch, workdir=workdir, proxied_bzrs=proxied_bzrs)
        self.args = {'branch': branch,'workdir':workdir, 'proxied_bzrs': proxied_bzrs}
        # Compute defaults for descriptions:
        self.branch = branch
        description = ["Merging Branch"]
        self.description = description
        self.env_info = ''
        self.summaries = {}

    def doStepIf(self, *args):
        s = self.build.getSourceStamp()
        if len(s.changes) > 1:
            return True
        else:
            return False

    def start(self):
        builder_props = self.build.getProperties()
        self.args['workdir'] = builder_props.render(self.args.get('workdir', ''))
        # We have to compute the source URL for the merge branch
        s = self.build.getSourceStamp()

        if len(s.changes) != 2:
            log.err("Strange, we are into a merge loop with %d changes" % len(s.changes))

        if len(s.changes) < 2: # fuse
            return SKIPPED

        change = s.changes[0]
        # print "Have this change: %s @ %s / %s / %s" %( change.revision, change.branch, change.repository, change.revlink)

        repourl = self.args['proxied_bzrs'].get(change.branch, change.branch)
        self.args['command']=['bzr', 'merge', '-q']
        self.args['command'] += ["-r", str(change.revision), repourl]

        cmd = LoggedRemoteCommand("OpenObjectShell", self.args)
        self.startCommand(cmd)

class BzrCommit(LoggingBuildStep):
    """Commit the (merged) changes into bzr
    """
    name = 'Bzr commit'
    haltOnFailure = True
    warnOnWarnings = True

    def describe(self, done=False,success=False,warn=False,fail=False):
         if done:
            if success:
                return ['Bzr commit finished!']
            if warn:
                return ['Warnings at bzr commit !']
            if fail:
                return ['Bzr commit Failed !']
         return self.description

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)


    def __init__(self, workdir=WithProperties('%(repo_mode)s'), **kwargs):

        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir)
        self.args = {'workdir': workdir }
        # Compute defaults for descriptions:
        description = ["Performing bzr commit"]
        self.description = description
        self.build_result = SUCCESS

    def doStepIf(self, *args):
        """ Check if the branch is changed, so that commit makes sense
        """
        try:
            if self.build.result >= FAILURE:
                return False

            return self.build.getProperty('need_commit') == 't'
        except KeyError:
            return False

    def start(self):
        self.args['command']=["bzr","commit", "--local"] # not -q, we need to read the revno
        
        builder_props = self.build.getProperties()
        self.args['workdir'] = builder_props.render(self.args.get('workdir', ''))

        s = self.build.getSourceStamp()
        self.args['command'] += ['-m', str(s.changes[-1].comments)]
        
        cmd = StdErrRemoteCommand("OpenObjectShell", self.args)
        self.stderr_log = self.addLog("stderr")
        cmd.useLog(self.stderr_log, True)
        self.startCommand(cmd)

    def createSummary(self, slog):
        """ Try to read the file-lint.sh output and parse results
        """
        revno_re = re.compile(r'Committed revision ([0-9]+)\.')
        try:
            revno = False
            for line in StringIO(slog.getText().replace('\r','\n')).readlines():
                line = line.strip()
                if not line:
                    continue
                if 'ERROR' in line:
                    self.build_result = FAILURE
                    self.description = 'Commit FAILED!'
                    continue
                m = revno_re.match(line)
                if m:
                    revno = m.group(1)
                    break
            if revno:
                s = self.build.getSourceStamp()
                change = s.changes[-1]
                change.revision = revno
                self.build.builder.db.saveCommit(change)
                self.setProperty('revision', change.revision)
                self.description = "Commit recorded in DB"
        except Exception, e:
            log.err("Cannot commit output: %s" % e)
        

    def evaluateCommand(self, cmd):
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE
        if self.build_result > res:
            res = self.build_result
        return res

class BzrSyncUp(MasterShellCommand):
    """ Pull from the buildslave, push to LP (if needed)
    
    It should run on the master, because only that one may have a key
    to upload into Launchpad.
    
    """
    
    name = "bzr-sync-up"
    flunkOnFailure = False
    warnOnFailure = True
    alwaysRun = False

    
    def __init__(self, proxied_bzrs={}, threshold=None, sync_mode=None, command=False, **kwargs):
        def _get_proxy_path(props):
            return proxied_bzrs.get(props['branch_url'], False) \
                    or props['branch_url']
        
        def _get_slavename(props):
            ret = ''
            if 'group' in props:
                ret = props['group'].replace(' ', '_') + '_'
            ret += props['branch_url'].rsplit('/')[-1]
            return ret

        if not command:
            command = ['./bzr-pushpull.sh',
                    '-s', WithProperties('%(slavename)s'),
                    '-l', WithProperties('%(branch_url)s'),
                    '-r', WithProperties('%(revision)s'),
                    '-m', WithProperties('%(repo_mode)s'),
                    '-b', WithProperties('%(gsl)s', gsl=_get_slavename),
                    '-p', WithProperties('%(proxy_url)s', proxy_url=_get_proxy_path)
                    ]
            if sync_mode:
                command += [ '--sync-mode', str(sync_mode) ]

        MasterShellCommand.__init__(self, command, **kwargs)
        if isinstance(threshold, int):
            pass
        elif isinstance(threshold, basestring) and threshold:
            for x, status in enumerate(status_Results):
                if threshold.lower() == status:
                    threshold = x
                    break
            else:
                threshold = FAILURE
        else:
            threshold = FAILURE

        self.addFactoryArguments(threshold=threshold)
        self.args = {'threshold': threshold}

    def doStepIf(self, *args):
        """ Check if this step needs to run
        """
        if self.build.result >= self.args['threshold']:
            return False
        else:
            return True

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
