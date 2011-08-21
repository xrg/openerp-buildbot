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
from bbot_oe.step_iface import LoggedOEmixin, StdErrRemoteCommand


class LintTest(LoggedOEmixin, LoggingBuildStep):
    """Step to perform lint-check on changed files
    """
    name = 'Lint test'
    flunkOnFailure = False
    warnOnFailure = True

    known_strs = [ (r'Pyflakes failed for: (?P<fname>.+)$', FAILURE, {'test_name': 'pyflakes', }),
                   (r'Please correct warnings for (?P<fname>.+)$', WARNINGS, {'test_name': 'lint', }),
                   (r'Not ready to commit: (?P<fname>.+)$', FAILURE, {'test_name': 'lint', }),
                   (r'You used tabs in (?P<fname>.+)\. Please expand them', WARNINGS, {'test_name': 'whitespace', }),
                   (r'XmlLint failed for: (?P<fname>.+)$', FAILURE, {'test_name': 'lint', }),
                   # (r'No lint for (.+)$', SUCCESS , {'test_name': 'lint', }),
                   # Must come last:
                   (r'(?P<fname>[^:]+):[0-9]+: (?P<msg>.+)$', SUCCESS , {'test_name': 'lint', }),
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
        LoggedOEmixin.__init__(self, workdir=workdir, keeper_conf=keeper_conf, part_subs=part_subs, **kwargs)
        self.addFactoryArguments(workdir=workdir or self.workdir, strict=strict)
        self.args = {'workdir': workdir or self.workdir, 'strict': strict}
        # Compute defaults for descriptions:
        description = ["Performing lint check"]
        self.description = description
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

    def evaluateCommand(self, cmd):
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE
        if self.build_result > res:
            res = self.build_result
        return res

exported_buildsteps = [LintTest,]

#eof
