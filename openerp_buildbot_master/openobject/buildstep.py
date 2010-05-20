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
from buildbot.process.buildstep import LoggingBuildStep, LoggedRemoteCommand
from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS
from sql import db_connection
from xmlrpc import buildbot_xmlrpc

import pickle
import os
from openobject import tools
ignore_module_list = ['bin','Makefile','man','README','setup.cfg','debian','python25-compat','sql','change-loglevel.sh',
        'get-srvstats.sh','setup.py','doc','MANIFEST.in','openerp.log','pixmaps','rpminstall_sh.txt','setup.nsi','win32',
        '.bzrignore','.bzr']
try:
    import cStringIO
    StringIO = cStringIO.StringIO
except ImportError:
    from StringIO import StringIO

#TODO:We need to get test_id passed from schedular and the following fixed args.

openerp_host = 'localhost'
openerp_port = 8069
openerp_dbname = 'buildbot'
openerp_userid = 'admin'
openerp_userpwd = 'a'

def create_test_step_log(step_object = None, res=SUCCESS):
    state = 'pass'
    source = step_object.build.builder.test_ids
    revision = step_object.build.source.changes[0].revision
    test_id = source.get(revision, False)
    summary = step_object.summaries
    if res == FAILURE:
        state = 'fail'
    params={}
    params['name'] = step_object.name
    params['test_id'] = int(test_id)
    params['warning_log'] = '\n'.join(summary['WARNING'])
    params['error_log'] = '\n'.join(summary['ERROR'])
    params['critical_log'] = '\n'.join(summary['CRITICAL'])
    params['info_log'] = '\n'.join(summary['INFO'])
    params['yml_log'] = '\n'.join(summary['TEST'])
    params['traceback_detail'] = '\n'.join(summary['TRACEBACK'])
    params['state'] = state
    openerp = buildbot_xmlrpc(host = openerp_host, port = openerp_port, dbname = openerp_dbname)
    openerp_uid = openerp.execute('common','login',  openerp.dbname, openerp_userid, openerp_userpwd)
    result_id = openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.test.step','create',params)
    return result_id

class CreateDB(LoggingBuildStep):
    name = 'create-db'
    flunkOnFailure = True
    haltOnFailure = True
    flunkingIssues = ["ERROR","CRITICAL"]
    MESSAGES = ("ERROR", "CRITICAL", "WARNING", "TEST", "INFO", "TRACEBACK")
    def describe(self, done=False,success=False,warn=False,fail=False):
         if done:
            if success:
                return ['Created db %s Sucessfully!'%(self.dbname)]
            if warn:
                return ['Created db %s with Warnings!'%(self.dbname)]
            if fail:
                return ['Creation of db %s Failed!'%(self.dbname)]
         return self.description

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)


    def __init__(self, dbname='test',workdir=None, addonsdir=None, demo=True, lang='en_US',netport=8970, port=8869 ,**kwargs):

        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(dbname=dbname,workdir=workdir, demo=demo, lang=lang, netport=netport,port=port, addonsdir=addonsdir)
        self.args = {'dbname': dbname,'workdir':workdir, 'demo':demo, 'lang':lang,'netport':netport, 'port' : port, 'addonsdir' : addonsdir}
        self.dbname = dbname
        # Compute defaults for descriptions:
        description = ["creating db"]
        self.description = description

    def start(self):
        self.args['command']=["make","create-db"]
        if self.args['dbname']:
           self.args['command'].append("database=%s"%(self.args['dbname']))
        if self.args['port']:
           self.args['command'].append("port=%s"%(self.args['port']))
        if self.args['netport']:
           self.args['command'].append("net_port=%s"%(self.args['netport']))
        if self.args['demo']:
           self.args['command'].append("demo=%s"%(self.args['demo']))
        if self.args['addonsdir']:
           self.args['command'].append("addons-path=%s"%(self.args['addonsdir']))
        cmd = LoggedRemoteCommand("shell",self.args)
        self.startCommand(cmd)

    def createSummary(self, log):
        data = False
        logs = log.getText()
        buildbotURL = self.build.builder.botmaster.parent.buildbotURL

        counts = {}
        summaries = {}
        for m in self.MESSAGES:
            counts[m] = 0
            summaries[m] = []

        io = StringIO(log.getText()).readlines()

        for line in io:
            if line.find("ERROR") != -1:
                pos = line.find("ERROR") + len("ERROR") + 5
                m = "ERROR"
            elif line.find("INFO:") != -1:
                pos = line.find("INFO") + len("INFO") + 5
                m = "INFO"
                #continue
            elif line.find("CRITICAL") != -1:
                pos = line.find("CRITICAL") + len("CRITICAL") + 5
                m = "CRITICAL"
            elif line.find("Traceback") != -1:
                traceback_log = []
                pos = io.index(line)
                for line in io[pos:-14]:
                    traceback_log.append(line)
                self.addCompleteLog("create-db : Traceback", "".join(traceback_log))
                m = "TRACEBACK"
                summaries[m].extend(traceback_log)
                counts[m] += 1
                break;
            elif line.find("WARNING") != -1:
                pos = line.find("WARNING") + len("WARNING") + 5
                m = "WARNING"
            else:
                continue
            line = line[pos:]
            summaries[m].append(line)
            counts[m] += 1
        self.summaries = summaries
        for m in self.MESSAGES:
            if not m == 'TRACEBACK':
                if counts[m]:
                    msg = "".join(summaries[m])
                    self.addCompleteLog("create-db : %s" % m, msg)
                    self.setProperty("create-db : %s" % m, counts[m])
        if sum(counts.values()):
            self.setProperty("create-db : MessageCount", sum(counts.values()))

    def evaluateCommand(self, cmd):
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE
        else:
            for m in self.flunkingIssues:
                try:
                    if self.getProperty("create-db : %s" % m):
                        res = FAILURE
                except:
                    pass
            try:
                if self.getProperty("create-db : MessageCount"):
                    res = WARNINGS
            except:
                pass
        create_test_step_log(self, res)
        return res

class DropDB(LoggingBuildStep):
    name = 'drop-db'
    flunkOnFailure = False
    def describe(self, done=False,success=False,warn=False,fail=False):
         if done:
            if success:
                return ['Dropped db %s Sucessfully!'%(self.dbname)]
            if warn:
                return ['Dropped db %s with Warnings!'%(self.dbname)]
            if fail:
                return ['Dropping of db %s Failed!'%(self.dbname)]
         return self.description

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)

    def __init__(self, dbname='test',workdir=None,port=8869,netport=8971,**kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(dbname=dbname,workdir=workdir,port=port,netport=netport)
        self.args = {'dbname': dbname,'workdir':workdir,'netport':netport, 'port':port}
        self.dbname = dbname
        # Compute defaults for descriptions:
        description = ["Dropping db"]
        self.description = description

    def start(self):
        self.args['command']=["make","drop-db"]
        if self.args['dbname']:
           self.args['command'].append("database=%s"%(self.args['dbname']))
        if self.args['port']:
           self.args['command'].append("port=%s"%(self.args['port']))
        if self.args['netport']:
           self.args['command'].append("net_port=%s"%(self.args['netport']))
        cmd = LoggedRemoteCommand("shell",self.args)
        self.startCommand(cmd)

    def evaluateCommand(self, cmd):
        res = SUCESS
        if cmd.rc != 0:
            res = FAILURE
        create_test_step_log(self, res)
        return res

class CheckQuality(LoggingBuildStep):
    name = 'check-quality'
    flunkOnFailure = True
    flunkingIssues = ["ERROR","CRITICAL"]
    MESSAGES = ("ERROR", "CRITICAL", "WARNING", "TEST", "INFO", "TRACEBACK")

    def describe(self, done=False,success=False,warn=False,fail=False):
        if done:
            if success:
                return ['Quality Checked  !']
            if warn:
                return ['Check quality had Warnings!']
            if fail:
                if self.quality_stage == 'fail':
                    self.name = 'Module(s) failed to reach minimum quality score!'
                    return ['Module failed to reach minimum quality score!']
                return ['Check quality Failed !']
        return self.description

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)

    def __init__(self, dbname='test',workdir=None,addonsdir=None,netport=8972, port=8869 ,**kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(dbname=dbname,workdir=workdir,addonsdir=addonsdir,netport=netport, port=port, logfiles={})
        self.args = {'dbname': dbname, 'modules':'', 'port' :port,'workdir':workdir,'netport':netport,'addonsdir':addonsdir,'logfiles':{}}
        self.dbname = dbname
        # Compute defaults for descriptions:
        description = ["checking quality"]
        self.description = description
        self.quality_stage = 'pass'

    def start(self):
        s = self.build.getSourceStamp()
        modules = []
        quality_logs = 'quality-logs'
        self.logfiles={}
        for change in s.changes:
            files = (
                     change.files_added +
                     change.files_modified +
                     [f[1] for f in change.files_renamed]
                     )
            for f in files:
                module = f.split('/')[0]
                if module in ignore_module_list:
                    continue
                if module not in modules:
                    modules.append(str(module))
                    self.logfiles['Quality Log - %s'%module] = ('%s/%s.html'%(quality_logs,module))

        self.args['modules'] = ','.join(modules)
        self.args['logfiles'] = self.logfiles
        if self.args['modules']:
            self.description += self.args['modules'].split(',')
            self.args['command']=["make","check-quality"]

            if self.args['addonsdir']:
                self.args['command'].append("addons-path=%s"%(self.args['addonsdir']))
            if self.args['netport']:
                self.args['command'].append("net_port=%s"%(self.args['netport']))
            if self.args['port']:
                self.args['command'].append("port=%s"%(self.args['port']))
            if self.args['modules']:
                self.args['command'].append("module=%s"%(self.args['modules']))
            if self.args['dbname']:
                self.args['command'].append("database=%s"%(self.args['dbname']))
            cmd = LoggedRemoteCommand("shell",self.args)
            self.startCommand(cmd)
        else:
            cmd = LoggedRemoteCommand("dummy", self.args)
            self.startCommand(cmd)

    def createSummary(self, log):
        data = False
        logs = log.getText()
        buildbotURL = self.build.builder.botmaster.parent.buildbotURL

        counts = {}
        summaries = {}
        for m in self.MESSAGES:
            counts[m] = 0
            summaries[m] = []

        io = StringIO(log.getText()).readlines()

        for line in io:
            if line.find("ERROR") != -1:
                pos = line.find("ERROR") + len("ERROR") + 5
                m = "ERROR"
            elif line.find("INFO:") != -1:
                pos = line.find("INFO") + len("INFO") + 5
                m = "INFO"
                #continue
            elif line.find("CRITICAL") != -1:
                pos = line.find("CRITICAL") + len("CRITICAL") + 5
                m = "CRITICAL"
            elif line.find("Traceback") != -1:
                traceback_log = []
                pos = io.index(line)
                for line in io[pos:-3]:
                    traceback_log.append(line)
                self.addCompleteLog("Check-Quality : Traceback", "".join(traceback_log))
                m = "TRACEBACK"
                summaries[m].append(traceback_log)
                counts[m] += 1
                break;
            elif line.find("WARNING") != -1:
                pos = line.find("WARNING") + len("WARNING") + 5
                m = "WARNING"
            else:
                continue
            line = line[pos:]
            summaries[m].append(line)
            counts[m] += 1
        self.summaries = summaries

        for m in self.MESSAGES:
            if not m == 'TRACEBACK':
                if counts[m]:
                    msg = "".join(summaries[m])
                    self.addCompleteLog("Check-Quality : %s" % m, msg)
                    self.setProperty("Check-Quality : %s" % m, counts[m])
        if sum(counts.values()):
            self.setProperty("Check-Quality : MessageCount", sum(counts.values()))


    def evaluateCommand(self, cmd):
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE
        else:
            for m in self.flunkingIssues:
                try:
                    if self.getProperty("Check-Quality : %s" % m):
                        res = FAILURE
                except:
                    pass
            try:
                if self.getProperty("Check-Quality : MessageCount"):
                    res = WARNINGS
            except:
                pass
        create_test_step_log(self, res)
        return res

class Copy(LoggingBuildStep):
    name = 'copy'
    flunkOnFailure = False
    def describe(self, done=False):
        if done:
            return self.descriptionDone
        return self.description

    def __init__(self, workdir=None, addonsdir=None, **kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir, addonsdir=addonsdir)
        self.args = {'workdir': workdir, 'addonsdir':addonsdir}

        # Compute defaults for descriptions:
        description = ["copy", '"'+workdir+'"', "in", '"'+ addonsdir +'"']
        descriptionDone = ["copy", '"'+workdir+'"' , "in", '"' + addonsdir +'"']

        self.description = description
        self.descriptionDone = descriptionDone

    def start(self):
        s = self.build.getSourceStamp()
        cmd = LoggedRemoteCommand("copy", self.args)
        self.startCommand(cmd)

    def evaluateCommand(self, cmd):
        res = FAILURE
        if (cmd.rc == 0) or (cmd.rc == 1):
            res = SUCCESS
        create_test_step_log(self, res)
        return res

class InstallTranslation(LoggingBuildStep):
    name = 'install-translation'
    flunkOnFailure = True
    flunkingIssues = ["ERROR","CRITICAL"]
    MESSAGES = ("ERROR", "CRITICAL", "WARNING", "TEST", "INFO", "TRACEBACK")

    def describe(self, done=False,success=False,warn=False,fail=False):
        if done:
            if success:
                return ['Translation'] + self.translation_lst.split('\n') + ['Installed Sucessfully!']
            if warn:
                return ['Translation'] + self.translation_lst.split('\n') + ['Installed with Warnings!']
            if fail:
                return ['Translation(s) Installing Failed!']
        return self.description

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)

    def __init__(self,workdir=None, addonsdir=None,dbname=False,port=8869, netport=8973, **kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir,addonsdir=addonsdir,dbname=dbname, port=port, netport=netport)
        self.args = {'addonsdir': addonsdir,
                     'workdir': workdir,
                     'dbname' : dbname,
                     'netport' : netport,
                     'port' : port,
        }
        self.name = 'install-translation'
        self.description = ["Installing Translation"]
        self.translation_lst = ''

    def start(self):
        s = self.build.getSourceStamp()
        self.pofiles = {}

        for change in s.changes:
            files = (
                     change.files_added +
                     change.files_modified +
                     [f[1] for f in change.files_renamed]
                     )
            for f in files:
                mod_lst = f.split('/')
                fname,ext = os.path.splitext(mod_lst[-1])
                if ext == '.po':
                    modName = mod_lst[0]
                    if modName == 'bin':
                        modName = 'base'
                    if modName not in self.pofiles:
                        self.pofiles[modName] = []
                    self.pofiles[modName].append(mod_lst[-1])


        if len(self.pofiles):
            commands = []
            commands = ["make","install-translation"]

            if self.args['addonsdir']:
                commands.append("addons-path=%s"%(self.args['addonsdir']))
            if self.args['port']:
                commands.append("port=%s"%(self.args['port']))
            if self.args['netport']:
                commands.append("net_port=%s"%(self.args['netport']))
            if self.args['dbname']:
                commands.append("database=%s"%(self.args['dbname']))
            self.args['command'] = commands

            buildbotURL = self.build.builder.botmaster.parent.buildbotURL

            i18n_str = ''

            for module,files in self.pofiles.items():
                i18n_str += module + ':'+','.join(files) + '+'
                self.translation_lst += module + ':'+','.join(files) + '\n'

            self.description += ["Files:"] + self.translation_lst.split('\n') + ["on Server","%s:%s"%(buildbotURL[:-1],self.args['port'])]
            self.args['command'].append("i18n-import=%s"%(i18n_str[:-1]))
            cmd = LoggedRemoteCommand("shell",self.args)
            self.startCommand(cmd)
        else:
            cmd = LoggedRemoteCommand("dummy", self.args)
            self.startCommand(cmd)

    def createSummary(self, log):
        counts = {}
        summaries = {}
        for m in self.MESSAGES:
            counts[m] = 0
            summaries[m] = []

        io = StringIO(log.getText()).readlines()

        for line in io:
            if line.find("Traceback") != -1:
                traceback_log = []
                pos = io.index(line)
                for line in io[pos:-3]:
                    traceback_log.append(line)
                    if line.find("Exception:") != -1:
                        index = traceback_log.index(line) + 2
                    else:
                        index = -3
                traceback_property = []
                for line in traceback_log[index:-1]:
                        traceback_property.append(line)
                self.addCompleteLog("Install-Translation : Traceback", "".join(traceback_log))
                self.setProperty("Install-Translation : Traceback", "".join(traceback_property))
                m = "TRACEBACK"
                summaries[m].append(traceback_log)
                counts[m] += 1
                break;

            elif line.find("INFO:") != -1:
                pos = line.find("INFO") + len("INFO") + 5
                m = "INFO"
                #continue
            elif line.find("CRITICAL") != -1:
                pos = line.find("CRITICAL") + len("CRITICAL") + 5
                m = "CRITICAL"
            elif line.find("ERROR") != -1:
                pos = line.find("ERROR") + len("ERROR") + 5
                m = "ERROR"
            elif line.find("WARNING") != -1:
                pos = line.find("WARNING") + len("WARNING") + 5
                m = "WARNING"
            else:
                continue
            line = line[pos:]
            summaries[m].append(line)
            counts[m] += 1
        self.summaries = summaries

        for m in self.MESSAGES:
            if not m == 'TRACEBACK':
                if counts[m]:
                    msg = "".join(summaries[m])
                    self.addCompleteLog("Install-Translation : %s" % m, msg)
                    self.setProperty("Install-Translation : %s" % m, counts[m])
        if sum(counts.values()):
            self.setProperty("Install-Translation : MessageCount", sum(counts.values()))

    def evaluateCommand(self, cmd):
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE
        else:
            for m in self.flunkingIssues:
                try:
                    if self.getProperty("Install-Translation : %s" % m):
                        res = FAILURE
                except:
                    pass
            try:
                if self.getProperty("Install-Translation : MessageCount"):
                    res = WARNINGS
            except:
                pass
        create_test_step_log(self, res)
        return res


class InstallModule(LoggingBuildStep):
    name = 'install-module'
    flunkOnFailure = True
    flunkingIssues = ["ERROR","CRITICAL"]
    MESSAGES = ("ERROR", "CRITICAL", "WARNING", "TEST", "INFO", "TRACEBACK")

    def describe(self, done=False,success=False,warn=False,fail=False):
        if done:
            if success:
                return ['Module(s)'] + self.args['modules'].split(',') + ['installed Sucessfully!']
            if warn:
                return ['Module(s)'] + self.args['modules'].split(',') + ['installed with Warnings!']
            if fail:
                return ['Installing module(s) Failed!']
        return self.description

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)

    def __init__(self,workdir=None, addonsdir=None, modules='',extra_addons='', dbname=False,port=8869, netport=8974, **kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir,addonsdir=addonsdir,extra_addons=extra_addons,modules=modules, dbname=dbname, port=port, netport=netport)
        self.args = {'addonsdir': addonsdir,
                     'workdir': workdir,
                     'dbname' : dbname,
                     'modules' : modules,
                     'netport' : netport,
                     'port' : port,
                     'extra_addons':extra_addons,
        }
        self.name = 'install-module'
        self.description = ['Installing Module(s)']
	self.descriptionDone = ['Module Installed Sucessfully']

    def start(self):
        s = self.build.getSourceStamp()
        modules = []
        for change in s.changes:
            for f in change.files:
                module = f.split('/')[0]
                if module in ignore_module_list:
                    continue
                if module not in modules:
                    modules.append(module)
        if len(modules):
            self.args['modules'] += ','.join(modules)
        buildbotURL = self.build.builder.botmaster.parent.buildbotURL
        self.description += self.args['modules'].split(',') + ["on Server","%s:%s"%(buildbotURL[:-1],self.args['port'])]
        if self.args['modules']:
            self.args['command'] = ["make","install-module"]
            if self.args['addonsdir']:
                self.args['command'].append("addons-path=%s"%(self.args['addonsdir']))
            if self.args['modules']:
                self.args['command'].append("module=%s"%(self.args['modules']))
            if self.args['netport']:
                self.args['command'].append("net_port=%s"%(self.args['netport']))
            if self.args['port']:
                self.args['command'].append("port=%s"%(self.args['port']))
            if self.args['dbname']:
                self.args['command'].append("database=%s"%(self.args['dbname']))
            if self.args['extra_addons']:
                self.args['command'].append("extra-addons=%s"%(self.args['extra_addons']))
            cmd = LoggedRemoteCommand("shell",self.args)
            self.startCommand(cmd)
        else:
            cmd = LoggedRemoteCommand("dummy", self.args)
            self.startCommand(cmd)

    def createSummary(self, log):
        counts = {}
        summaries = {}
        for m in self.MESSAGES:
            counts[m] = 0
            summaries[m] = []

        io = StringIO(log.getText()).readlines()

        for line in io:
            if line.find("Traceback") != -1:
                traceback_log = []
                pos = io.index(line)
                for line in io[pos:-1]:
                    traceback_log.append(line)
                    index = -3
                    if line.find("Exception:") != -1:
                        index = traceback_log.index(line) + 2
                traceback_property = []
                for line in traceback_log[(index):-1]:
                        traceback_property.append(line)
                self.addCompleteLog("Install-Module : Traceback", "".join(traceback_log))
                self.setProperty("Install-Module : Traceback", "".join(traceback_property))
                m = "TRACEBACK"
                summaries[m].append("".join(traceback_log))
                counts[m] += 1
                break;
            elif line.find("INFO") != -1:
                pos = line.find("INFO") + len("INFO") + 5
                m = "INFO"
                #continue
            elif line.find("CRITICAL") != -1:
                m = "CRITICAL"
                pos = line.find("CRITICAL") + len("CRITICAL") + 5
            elif line.find("ERROR") != -1:
                m = "ERROR"
                pos = line.find("ERROR") + len("ERROR") + 5
            elif line.find("WARNING") != -1:
                m = "WARNING"
                pos = line.find("WARNING") + len("WARNING") + 5
            else:
                continue
            line = line[pos:]
            summaries[m].append(line)
            counts[m] += 1
        self.summaries = summaries

        for m in self.MESSAGES:
            if not m == 'TRACEBACK':
                if counts[m]:
                    msg = "".join(summaries[m])
                    self.addCompleteLog("Install-Module : %s" % m, msg)
                    self.setProperty("Install-Module : %s" % m, counts[m])
        if sum(counts.values()):
            self.setProperty("Install-Module : MessageCount", sum(counts.values()))

    def evaluateCommand(self, cmd):
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE
        else:
            for m in self.flunkingIssues:
                try:
                    if self.getProperty("Install-Module : %s" % m):
                        res = FAILURE
                except:
                    pass
            try:
                if self.getProperty("Install-Module : MessageCount"):
                    res = WARNINGS
            except:
                pass
        create_test_step_log(self, res)
        return res


class OpenObjectBzr(Bzr):
    flunkOnFailure = False
    haltOnFailure = True
    def __init__(self, repourl=None, baseURL=None,
                 defaultBranch=None,workdir=None, mode='update', alwaysUseLatest=True, timeout=20*60, retry=None,**kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        Bzr.__init__(self, repourl=repourl, baseURL=baseURL,
                   defaultBranch=defaultBranch,workdir=workdir,mode=mode,alwaysUseLatest=alwaysUseLatest,timeout=timeout,
                   retry=retry,**kwargs)
        self.name = 'bzr-update'
        self.description = ["updating", "branch %s%s"%(baseURL,defaultBranch)]
        self.descriptionDone = ["updated", "branch %s%s"%(baseURL,defaultBranch)]

    def startVC(self, branch, revision, patch):
        slavever = self.slaveVersion("bzr")
        if not slavever:
            m = "slave is too old, does not know about bzr"
            raise BuildSlaveTooOldError(m)

        if self.repourl:
            assert not branch # we need baseURL= to use branches
            self.args['repourl'] = self.repourl
        else:
            self.args['repourl'] = self.baseURL + self.branch # self.baseURL + branch

        if  self.args['repourl'] == branch:
            self.args['revision'] = revision
        else:
            self.args['revision'] = None
        self.args['patch'] = patch

        revstuff = []
        self.description.extend(revstuff)
        self.descriptionDone.extend(revstuff)
        cmd = LoggedRemoteCommand("openobjectbzr", self.args)
        self.startCommand(cmd)

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
                return ['Server started Sucessfully!']
            if warn:
                return ['Server started with Warnings!']
            if fail:
                return ['Server Failed!']
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
        description = ["Starting server with upgration"]
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

        cmd = LoggedRemoteCommand("shell",self.args)
        self.startCommand(cmd)


class CreateDB2(CreateDB):
    def start(self):
        cmd = LoggedRemoteCommand("create-db",self.args)
        self.startCommand(cmd)

class InstallModule2(InstallModule):
    def start(self):
        s = self.build.getSourceStamp()
        modules = []
        for change in s.changes:
            for f in change.files:
                try:
                    module = f.split('/')
                    if change.branch == 'https://svn.tinyerp.com/be/maintenance':
                        module = (len(module) > 1) and module[1] or ''
                    else:
                        module = module[0]
                    if module not in modules:
                        if module not in ('README.txt'):
                            modules.append(module)
                except:
                    pass
        self.args['modules'] += ','.join(modules)
        cmd = LoggedRemoteCommand("install-module",self.args)
        self.startCommand(cmd)


class BzrMerge(LoggingBuildStep):
    name = 'bzr-merge'
    flunkOnFailure = True
    haltOnFailure = True
    flunkingIssues = ["ERROR","CRITICAL"]
    MESSAGES = ("ERROR", "CRITICAL", "WARNING", "TEST", "INFO", "TRACEBACK")

    def describe(self, done=False,success=False,warn=False,fail=False):
         if done:
            if success:
                return ['Merge branch %s Sucessfully!'%(self.branch)]
            if warn:
                return ['Merge branch %s with Warnings!'%(self.branch)]
            if fail:
                return ['Merge branch %s Failed!'%(self.branch)]
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
        description = ["Merging Branch"]
        self.description = description

    def start(self):
        s = self.build.getSourceStamp()        
        lestest_rev_no = False
        for change in s.changes:
            lestest_rev_no = change.revision
        
        self.args['command']=["bzr","merge"]
        if lestest_rev_no:
          self.args['command'] += ["-r", lestest_rev_no]

        if self.args['branch']:
           self.args['command'].append(branch)        
        cmd = LoggedRemoteCommand("shell",self.args)
        self.startCommand(cmd)    

    def evaluateCommand(self, cmd):
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE        
        create_test_step_log(self, res)
        return res

class BzrRevert(LoggingBuildStep):
    name = 'bzr-revert'
    flunkOnFailure = True
    haltOnFailure = True
    flunkingIssues = ["ERROR","CRITICAL"]
    MESSAGES = ("ERROR", "CRITICAL", "WARNING", "TEST", "INFO", "TRACEBACK")

    def describe(self, done=False,success=False,warn=False,fail=False):
         if done:
            if success:
                return ['Merge revert %s Sucessfully!'%(self.workdir)]
            if warn:
                return ['Merge revert %s with Warnings!'%(self.workdir)]
            if fail:
                return ['Merge revert %s Failed!'%(self.workdir)]
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
        # Compute defaults for descriptions:
        description = ["Reverting Branch"]
        self.description = description

    def start(self):
        self.args['command']=["bzr","revert"]               
        cmd = LoggedRemoteCommand("shell",self.args)
        self.startCommand(cmd)    

    def evaluateCommand(self, cmd):
        res = SUCCESS
        if cmd.rc != 0:
            res = FAILURE        
        create_test_step_log(self, res)
        return res

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
