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


from buildslave.commands.base import Command
from buildslave.commands.shell import SlaveShellCommand
from buildslave.commands.bzr import Bzr
from buildslave import runprocess
from twisted.internet import reactor, defer, task
from twisted.python import log, failure, runtime
import os
import sys
import platform
import locale

command_version = "0.0.1"

class test_environment():

    def get_test_environment(self, base_dir=''):
        environment = {}
        testbranch_rev_info = ['Not Available !', 'Not Available !']
        if base_dir:
            server_dir_path = os.path.join(base_dir, 'openerp-server')
            addons_dir_path = os.path.join(base_dir, 'openerp-addons')
            bzr_path_ext = '/.bzr/branch/last-revision'
            testbranch_rev_info = []
            try:
                for path in [server_dir_path, addons_dir_path]:
                    fp = open(path + bzr_path_ext,'r')
                    testbranch_rev_info.append(fp.read())
                    fp.close()
            except:
                testbranch_rev_info = ['Not Available !', 'Not Available !']

        openerp_ver_cmd = 'make -C  %s version'%(server_dir_path)
        openerp_version = os.popen(openerp_ver_cmd).read()
        openerp_version = openerp_version.split('\n')[2]

        os_lang = '.'.join( [x for x in locale.getdefaultlocale() if x] )

        if not os_lang:
            os_lang = 'NOT SET'
        if os.name == 'posix':
          if platform.system() == 'Linux':
             lsbinfo = os.popen('lsb_release -a').read()
             lsb = {}
             for val in lsbinfo.split('\n'):
                 info = val.split(':')
                 if len(info) > 1:
                     lsb.update({'A: '+info[0]:info[1].strip()})
          else:
             lsb = {'A: System is not lsb compliant ':''}

        environment = {
                      'A: OpenERP Version ':openerp_version,
                      'A: OpenERP Server ':testbranch_rev_info[0].strip(),
                      'A: OpenERP Addons ':testbranch_rev_info[1].strip(),
                      'A: OS platform ':platform.platform(),
                      'A: OS Name ':platform.os.name,
                      'A: OS Release ':platform.release(),
                      'A: OS Version ':platform.version(),
                      'A: OS Architecture ':platform.architecture()[0],
                      'A: OS Locale ':os_lang,
                      'A: Python Version ':platform.python_version()
                      }
        environment.update(lsb)
        return environment

class OpenObjectShell(SlaveShellCommand):

    def __init__(self, *args, **kwargs):
        SlaveShellCommand.__init__(self, *args, **kwargs)
        self.args.setdefault('logEnviron', False)

class OpenObjectBzr(Bzr):
    def doVCUpdate(self):
        bzr = self.getCommand('bzr')
        if self.revision:
            command = [bzr, 'pull', self.sourcedata.split('\n')[0],
                        '-q', '--overwrite',
                        '-r', str(self.revision)]
        else:
            command = [bzr, 'update', '-q']
        srcdir = os.path.join(self.builder.basedir, self.srcdir)
        c = runprocess.RunProcess(self.builder, command, srcdir, sendRC=False, timeout=self.timeout, logEnviron=False)
        self.command = c
        d = c.start()
        d.addCallback(self.doVCClean)
        return d

    def doVCClean(self, res=None):
        """ Clean the repository after some pull or update
        
        This will remove untracked files (eg. *.pyc, junk) from the repo dir.
        """
        bzr = self.getCommand('bzr')
        command = [bzr, 'clean-tree', '-q', '--force', '--unknown', '--detritus']
        srcdir = os.path.join(self.builder.basedir, self.srcdir)
        c = runprocess.RunProcess(self.builder, command, srcdir, sendRC=False, timeout=self.timeout, logEnviron=False)
        self.command = c
        d = c.start()
        return d

    def doClobber(self, dummy, dirname, **kwargs):
        # Bzr class wouldn't check that, because it assumes dirname == workdir,
        # so already created.
        d = os.path.join(self.builder.basedir, dirname)
        if not os.path.exists(d):
            return defer.succeed(0)
        return Bzr.doClobber(self, dummy, dirname, **kwargs)

    def sourcedataMatches(self):
        """ we don't care, assume it is the right dir
        """
        return True

    def sourcedirIsUpdateable(self):
        if os.path.exists(os.path.join(self.builder.basedir, self.srcdir, ".buildbot-patched")):
            return False
        if os.path.exists(os.path.join(self.builder.basedir, self.srcdir, ".bzr", 'checkout', 'limbo')):
            return False
        # contrary to base class, we allow update when self.revision
        return (not self.sourcedirIsPatched()) and \
                os.path.isdir(os.path.join(self.builder.basedir,
                                           self.srcdir, ".bzr"))

    def parseGotRevision(self):
        # A dirty hack, only for the current OpenERP setup.
        # If we are called for the optional non-revisioned dirs, don't report
        # the revision as a property to the master, because it would incorrectly
        # tag the builds with the wrong branch's rev_num.
        if self.revision:
            Bzr.parseGotRevision(self)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
