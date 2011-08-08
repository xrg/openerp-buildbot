# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2011 P. Christeas <xrg@hellug.gr>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from buildbot.process.buildstep import LoggingBuildStep, LoggedRemoteCommand
from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS #, EXCEPTION, SKIPPED
from buildbot.status.builder import TestResult
from openerp_libclient.tools import ustr
import re

""" BuildStep interface classes

"""

try:
    import cStringIO
    StringIO = cStringIO.StringIO
except ImportError:
    from StringIO import StringIO

class StepOE:
    """Mix-in class for BuildbotOE-aware Steps

        By mixing this class in a Buildstep, master-keeper will know that it
        needs to supply the `keeper_conf` dict automatically to the keyword
        arguments of the step.

        TODO doc for keeper_conf
    """
    def __init__(self, **kwargs):
        assert 'keeper_conf' in kwargs
        if kwargs.get('workdir',False):
            self.workdir = kwargs['workdir']
        elif kwargs.get('keeper_conf'):
            self.workdir = None
            components = kwargs['keeper_conf']['builder'].get('components',{})
            for comp in components.values():
                if comp['is_rolling']:
                    if comp.get('dest_path'):
                        self.workdir = comp['dest_path']
                        break
            else:
                if len(components) > 1:
                    # we have to override the default 'build' one
                    self.workdir = '.'
        else:
            if not hasattr(self, 'workdir'):
                self.workdir = None

    def setDefaultWorkdir(self, workdir):
        if not self.workdir:
            self.workdir = workdir

class StdErrRemoteCommand(LoggedRemoteCommand):
    """Variation of LoggedRemoteCommand that separates stderr
    """

    def addStderr(self, data):
        self.logs['stderr'].addStderr(data)


class LoggedOEmixin(StepOE):
    """mix-in that handles regex-parsed logs (w. component parts)

        known_strs is a list of 2-3 item tuples of the form:

            (regex_str, severity, field_dict)
    """
    known_strs = [] #: please define them in subclasses!
    _test_name = None

    def __init__(self, **kwargs):
        assert isinstance(self, LoggingBuildStep)
        StepOE.__init__(self, **kwargs)
        self.part_subs = kwargs.get('part_subs')
        if kwargs.get('keeper_conf'):
            if not self.part_subs:
                self.part_subs = kwargs['keeper_conf']['builder'].get('component_parts',[])

        #note: we are NOT keeping the keeper_conf, because we don't want to keep
        # its memory referenced
        self.addFactoryArguments(part_subs=self.part_subs)
        self.build_result = SUCCESS
        self.last_msgs = [self.name]

        self.known_res = []
        for kns in self.known_strs:
            rec = re.compile(kns[0])
            sev = kns[1]
            if len(kns) > 2:
                fdict = kns[2]
            else:
                fdict = {}
            self.known_res.append((rec, sev, fdict))

    def createSummary(self, log):
        """ Try to read the file-lint.sh output and parse results
        """
        severity = SUCCESS
        repo_reges = []
        for comp, rege_str, subst in self.part_subs:
            repo_reges.append((re.compile(rege_str), subst))

        t_results= {}
        last_msgs = []
        last_module = None
        clean_name = self.name.lower().replace(' ', '_')
        test_name = 'rest'

        for line in StringIO(log.getText()).readlines():
            for rem, sev, fdict in self.known_res:
                m = rem.match(line)
                if not m:
                    continue
                mgd = m.groupdict()
                fname = mgd.get('fname',fdict.get('fname',''))
                msg = ustr(mgd.get('msg',False) \
                    or fdict.get('msg', False) \
                    or line.strip())

                module = None
                if 'module' in mgd:
                    module = m.group('module')
                else:
                    for rege, subst in repo_reges:
                        mf = rege.match(fname)
                        if mf:
                            module = mf.expand(subst)
                            break
                    else:
                        if fname and fdict.get('module_from_fname', False):
                            # Try to get the cleanest part of the filename, as module name
                            module = fname.split('.',1)[0].replace('/','_').replace(' ','_').strip()

                if not module:
                    module = fdict.get('module', last_module or clean_name)
                else:
                    if fdict.get('module_persist', False):
                        last_module = module
                    else:
                        last_module = None

                # test name, detail after the module
                if 'test_name' in mgd:
                    test_name = mgd['test_name']
                elif 'test_name' in fdict:
                    test_name = fdict['test_name']
                
                module = (module, test_name)
                if module not in t_results:
                    t_results[module] = TestResult(name=module,
                                        results=SUCCESS,
                                        text='', logs={'stdout': u''})
                if t_results[module].results < sev:
                    t_results[module].results = sev

                if sev > severity:
                    severity = sev
                    last_msgs = [msg,] # and discard lower msgs
                elif sev == severity:
                    last_msgs.append(msg)

                if fdict.get('short', False):
                    tline = msg
                else:
                    if line.endswith('\r\n'):
                        line = line[:-2] + '\n'

                    tline = ustr(line)

                if not tline.endswith('\n'):
                    tline += '\n'
                if sev > SUCCESS:
                    t_results[module].text += ustr(tline)

                if fdict.get('stdout', True):
                    t_results[module].logs['stdout'] += ustr(line)

                break # don't attempt more matching of the same line

        # use t_results
        for tr in t_results.values():
            if self.build_result < tr.results:
                self.build_result = tr.results
            # and, after it's clean..
            self.build.build_status.addTestResult(tr)

        self.build_result = severity

        if last_msgs:
            self.last_msgs = [self.name,] + last_msgs

        self.build.builder.db.builds.saveTResults(self.build, self.name,
                                            self.build_result, t_results.values())

    def getText2(self, cmd, results):
        return self.last_msgs

#eof
