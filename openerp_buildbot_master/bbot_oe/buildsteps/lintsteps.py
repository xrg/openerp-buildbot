# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
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

from buildbot.process.buildstep import LoggingBuildStep
from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS #, EXCEPTION, SKIPPED
import re
from bzrsteps import StdErrRemoteCommand
from buildbot.status.builder import TestResult
from openerp_libclient.tools import ustr
from bbot_oe.step_iface import StepOE

try:
    import cStringIO
    StringIO = cStringIO.StringIO
except ImportError:
    from StringIO import StringIO


class LintTest(StepOE, LoggingBuildStep):
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


    def __init__(self, workdir=None, strict=False, keeper_conf=None, part_subs=None, **kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        StepOE.__init__(self, workdir=workdir, keeper_conf=keeper_conf, **kwargs)
        if keeper_conf:
            if not part_subs:
                part_subs = keeper_conf['builder'].get('component_parts',[])
        
        #note: we are NOT keeping the keeper_conf, because we don't want to keep
        # its memory referenced
        self.addFactoryArguments(workdir=workdir or self.workdir, strict=strict, part_subs=part_subs)
        self.args = {'workdir': workdir or self.workdir, 'strict': strict, 'part_subs': part_subs}
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
        self.args['command']=["file-lint.sh",]
        self.args['command'] += [ str(x) for x in self.build.allFiles()]
        self.args['workdir'] = self.workdir
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
        repo_reges = []
        for comp, rege_str, subst in self.args['part_subs']:
            repo_reges.append((re.compile(rege_str), subst))

        t_results= {}
        
        for line in StringIO(log.getText()).readlines():
            for rem, sev in self.known_res:
                m = rem.match(line)
                if not m:
                    continue
                fname = m.group(1)
                if sev > severity:
                    severity = sev
                for rege, subst in repo_reges:
                    mf = rege.match(fname)
                    if mf:
                        module = (mf.expand(subst), 'lint')
                        break
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

        if severity >= FAILURE: # TODO: remove
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

exported_buildsteps = [LintTest,]

#eof
