# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2010 OpenERP SA. (http://www.openerp.com)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################


from buildbot.process.buildstep import LoggingBuildStep, LoggedRemoteCommand
from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS, EXCEPTION

""" Build steps that maintain a proxy repository on the master side.
"""

import os
import logging
from twisted.python import log


from twisted.python import runtime
from twisted.internet import reactor
from buildbot.process.buildstep import BuildStep
from buildbot.process.buildstep import SUCCESS, FAILURE
from twisted.internet.protocol import ProcessProtocol

class MirrorRepoStep(LoggingBuildStep):
    """Step to perform lint-check on changed files
    """
    name = 'Mirror Repo'
    description='Mirroring Repo'
    descriptionDone='Repo synchronized'
    flunkOnFailure = False

    def __init__(self, workdir=None, repo_base=None, **kwargs):

        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir, repo_base=repo_base)
        self.args = {'workdir': workdir, 'repo_base': repo_base }
        # Compute defaults for descriptions:
        #self.description = ...

    class LocalPP(ProcessProtocol):
        def __init__(self, step, next_cmd=None):
            self.step = step
            self.next_cmd = next_cmd

        def outReceived(self, data):
            self.step.stdio_log.addStdout(data)

        def errReceived(self, data):
            self.step.stdio_log.addStderr(data)
            
        def processEnded(self, status_object):
            self.step.stdio_log.addHeader("exit status %d\n" % status_object.value.exitCode)
            if status_object.value.exitCode == 0 and self.next_cmd:
                self.next_cmd()
            else:
                self.step.processEnded(status_object)

    def start(self):
        self.stdio_log = stdio_log = self.addLog("stdio")

        stdio_log.addHeader("** RUNNING ON BUILDMASTER **\n")
        stdio_log.addHeader(" in dir %s\n" % os.getcwd())
        
        self._cmd_init()
        
    def _cmd_init(self):
        raise NotImplementedError

    def _start_command(self, command, pp_klass, path=None):
        self.stdio_log.addHeader(" ".join(command) + "\n\n")
        self.step_status.setText(list(self.description))

        # TODO add a timeout?
        if path is None:
            path = self.args.get('workdir', None)
        # FIXME reactor.spawnProcess(local_pp, command[0], command, path=path)
        # (the LocalPP object will call processEnded for us)

    def processEnded(self, status_object):
        if status_object.value.exitCode != 0:
            self.step_status.setText(["failed (%d)" % status_object.value.exitCode])
            self.finished(FAILURE)
        else:
            self.step_status.setText(list(self.descriptionDone))
            self.finished(SUCCESS)


class BzrMirrorStep(MirrorRepoStep):
    """ Mirror a bazaar branch inside a shared repository
    """

    def __init__(self, workdir=None, repo_base=None, branch_path=None,
                fetch_url=None, **kwargs):
        MirrorRepoStep.__init__(self, workdir=workdir, repo_base=repo_base, **kwargs)
        self.addFactoryArguments(branch_path=branch_path, fetch_url=fetch_url)
        self.args['branch_path'] = branch_path
        self.args['fetch_url'] = fetch_url

    def _cmd_init(self):
        if os.path.isabs(self.args['repo_base']):
            repo_base = self.args['repo_base']
        else:
            repo_base = os.path.join(self.args['workdir'], self.args['repo_base'])
        if not os.path.exists(repo_base):
            try:
                self.step_status.setText(["Create dir %s" % repo_base,])
                os.mkdirs(repo_base)
            except EnvironmentError, e:
                self.step_status.setText(["Could not make dir %s" % repo_base,
                        str(e) ])
                self.finished(FAILURE)
                return
            cmd = [ 'bzr', 'init-repo', '--quiet', '--no-trees']
            cmd.append(repo_base)
            self.step_status.setText(["Bzr init shared repo in %s" % repo_base,])
            self._start_command(cmd, MirrorRepoStep.LocalPP(self, self._cmd_fetch))
        else:
            if not os.path.isdir(repo_base):
                self.step_status.setText(
                        ["Path %s is not a directory, cannot use" % self.args['repo_base'], ])
                self.finished(EXCEPTION)
                return
            self._cmd_fetch()
        
    def _cmd_fetch(self):
        if os.path.isabs(self.args['repo_base']):
            repo_base = self.args['repo_base']
        else:
            repo_base = os.path.join(self.args['workdir'], self.args['repo_base'])


        branch_path = os.path.join(repo_base, self.args['branch_path'])

        if not os.path.exists(branch_path):
            self.step_status.setText(["Bzr checkout %s" % self.args['fetch_url'],])
            cmd = [ 'bzr', 'checkout', '--quiet', '--no-tree', '--bind' ]
            cmd.append(self.args['fetch_url'])
            cmd.append(self.args['branch_path'])
            self._start_command(cmd, MirrorRepoStep.LocalPP(self), path=repo_base)
            # and finish
        else:
            self.step_status.setText(["Bzr pull at in %s" % branch_path,])
            cmd = [ 'bzr', 'pull', '--quiet', '--overwrite' ]
            self._start_command(cmd, MirrorRepoStep.LocalPP(self), path=branch_path)


#eof
