# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>). All Rights Reserved
#    Copyright (C) 2010 OpenERP SA. (http://www.openerp.com)
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

# from buildbot.steps.shell import ShellCommand
from buildbot.process.buildstep import LoggingBuildStep, LoggedRemoteCommand, LogLineObserver
from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS, EXCEPTION #, SKIPPED
from buildbot.status.builder import TestResult
from buildbot.process.properties import WithProperties
from bbot_oe.step_iface import StepOE, ports_pool, dbnames_pool

import re
import logging
from openerp_libclient.utils import Pool
from twisted.python import log

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
            self.step.setDescription(testname)
            self.step.setProgress('tests', self.numTests)

class unique_dbnames(object):
    """ A simple pseydo-iterator that will produce unique database names
    """
    def __init__(self):
        self.__count = 0
        self.__uniq = hex(id(self))[-4:]

    def next(self):
        self.__count += 1
        return 'test-db-%s%x' % (self.__uniq, self.__count)

class OpenERPTest(StepOE, LoggingBuildStep):
    name = 'OpenERP-Test'
    step_name = 'OpenERP-Test'
    flunkOnFailure = True
    warnOnWarnings = True

    def describe(self, done=False,success=False,warn=False,fail=False):
        if done: # TODO
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

    def _get_random_dbname(self, props=None):
        global dbnames_pool
        return dbnames_pool.borrow(True)

    #def _get_builddir(self, props):
    #    # must be a function because it shall be rendered late, at start()
    #    return self.build.builder.builddir.replace('/', '_')

    def __init__(self, workdir=None, dbname=False, addonsdir=None, 
                    netport=None, port=None, ftp_port=None,
                    force_modules=None,
                    black_modules=None,
                    test_mode='full', distinct=False,
                    do_warnings=None, lang=None, debug=False,
                    keeper_conf=None, part_subs=None, components=None,
                    **kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        if isinstance(black_modules, basestring):
            black_modules = black_modules.split(' ')
        if isinstance(force_modules, basestring):
            force_modules = force_modules.split(' ')

        self.part_subs = part_subs
        self.components = components
        self.workdir = workdir
        if keeper_conf is not None:
            if not self.part_subs:
                self.part_subs = keeper_conf['builder'].get('component_parts',[])
            if not self.components:
                self.components = keeper_conf['builder'].get('components', [])
            distinct = keeper_conf['builder'].get('is_distinct', False)

        self.addFactoryArguments(workdir=workdir, dbname=dbname, addonsdir=addonsdir, 
                                netport=netport, port=port, ftp_port=ftp_port, logfiles={},
                                force_modules=(force_modules or []),
                                black_modules=(black_modules or []),
                                do_warnings=do_warnings, lang=lang,
                                part_subs=self.part_subs, components=self.components,
                                debug=debug,
                                test_mode=test_mode, distinct=distinct)
        self.args = {'port' :port, 'workdir':workdir, 'dbname': dbname, 
                    'netport':netport, 'addonsdir':addonsdir, 'logfiles':{},
                    'ftp_port': ftp_port,
                    'force_modules': (force_modules or []),
                    'black_modules': (black_modules or []),
                    'do_warnings': do_warnings, 'lang': lang,
                    'test_mode': test_mode, 'debug': debug }
        description = ["Performing OpenERP Test...",]
        self.description = description
        self.summaries = {}
        self.build_result = SUCCESS
        self.last_msgs = [self.name,]

        self.addLogObserver('stdio', BqiObserver())
        self.progressMetrics += ('tests',)
        self.distinct = distinct

    def setDescription(self, txt):
        """ Sets the 2nd member of self.description to txt """
        self.description = self.description[:1] + [txt]
        
    def _allModules(self, chg):
        """ Return the list of all the modules that must have changed
        """
        ret = []
        for fi in chg.properties.getProperty('filesb',[]):
            for rx, subst in self.repo_reges:
                m = rx.match(fi['filename'])
                if m:
                    ret.append(m.expand(subst))
                    break
        return ret

    def start(self):
        self.logfiles = {}
        self.repo_reges = []
        for comp, rege_str, subst in self.part_subs:
            if self.components.get(comp,{'is_rolling': False})['is_rolling']:
                self.repo_reges.append((re.compile(rege_str), subst))

        global ports_pool, dbnames_pool
        if not ports_pool:
            # Effectively, the range of these ports will limit the number of
            # simultaneous databases that can be tested
            min_port = self.build.getProperties().getProperty('min_port',8200)
            max_port = self.build.getProperties().getProperty('max_port',8299)
            port_spacing = self.build.getProperties().getProperty('port_spacing',4)
            ports_pool = Pool(iter(range(min_port, max_port, port_spacing)))

        if not dbnames_pool:
            dbnames_pool = Pool(unique_dbnames())

        if not self.args.get('addonsdir'):
            if self.build.getProperties().getProperty('addons_dir',False):
                self.args['addonsdir'] = self.build.getProperty('addons_dir')
            else:
                add_dirs = []
                for cname, comp in self.components.items():
                    if 'addons' in cname:
                        add_dirs.append( '../' + comp['dest_path'])

                if add_dirs:
                    self.args['addonsdir'] = ','.join(add_dirs)
                else:
                    self.args['addonsdir'] = '../addons/'
        if not self.args.get('port'):
            self.args['port'] = self.get_free_port()
        if self.args.get('ftp_port') is None: # False will skip the arg
            self.args['ftp_port'] = self.get_free_port()
        if self.args.get('dbname', False):
            self.args['dbname'] = self.build.render(self.args['dbname'])
        else:
            self.args['dbname'] = self._get_random_dbname()
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
            for chg in self.build.allChanges():
                more_mods.extend(self._allModules(chg))
                if not more_mods:
                    log.err("No changed modules located")
            try:
                if self.distinct:
                    raise StopIteration()
                if self.args['test_mode'] == 'changed-only':
                    raise StopIteration('Skipped')
                olmods_found = []
                for sbuild in self.build.builder.builder_status.generateFinishedBuilds(num_builds=10):
                    log.msg("Scanning back build %d" % sbuild.getNumber())
                    if sbuild.getResults() == SUCCESS:
                        break
                    our_branch = self.build.getProperties().getProperty('branch', False)
                    if our_branch and sbuild.getProperties().getProperty('branch', False) != our_branch:
                        log.msg("skipping build %s because it refers to %s branch, not %s" % \
                                ( sbuild.getNumber(), sbuild.getProperties().getProperty('branch', False), our_branch))
                        continue
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
            except StopIteration:
                pass
            except Exception, e:
                log.err("Could not figure old failures: %s" % e)
            mods_changed.extend(set(more_mods))

        try:
            todel = []
            for mc in mods_changed:
                if mc in self.args['black_modules']:
                    todel.append(mc)
                    continue
            for td in todel:
                if td in mods_changed: # prevent double-deletions
                    mods_changed.remove(td)
        except Exception, e:
            log.err("Cannot prune non-addon dirs: %s" % e)
        self.args['logfiles'] = self.logfiles
        
        # The general part of the b-q-i command
        root_path = 'bin/'
        self.args['command']=["../../../base_quality_interrogation.py",
                            "--machine-log=stdout", '--root-path='+root_path,
                            "--homedir=../", "-c", '~/.openerp-bqirc-bbot',
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
            elif self.args['test_mode'] == 'no-check-fvg':
                pass
            else:
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

            self.last_msgs = [self.name,] + [ b[0] for b in blame_list[:3]]
            
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

        self.build.builder.db.builds.saveTResults(self.build, self.name,
                                            self.build_result, t_results)

        if bqi_num_modules:
            self.setProperty('num_modules', bqi_num_modules)

        try:
            orm_id = self.getProperty('orm_id') or '?'
        except KeyError:
            orm_id = '?'

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
                del self.args['dbname']
        except RuntimeError, e:
            log.err("%s" % e)
        return res

    def getText2(self, cmd, results):
        return self.last_msgs

# Following Step are used in Migration builder
#TODO: remove, it's broken already
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

exported_buildsteps = [OpenERPTest, StartServer ]

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
