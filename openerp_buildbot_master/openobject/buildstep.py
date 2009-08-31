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

from buildbot.steps.source import Source, Bzr
from buildbot.steps.shell import ShellCommand
from buildbot.process.buildstep import LoggingBuildStep, LoggedRemoteCommand
from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS
import pickle
import os
from lxml import etree
try:
    import cStringIO
    StringIO = cStringIO.StringIO
except ImportError:
    from StringIO import StringIO


class CreateDB(LoggingBuildStep):
    name = 'create-db'
    flunkOnFailure = False
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


    def __init__(self, dbname='test',workdir=None, addonsdir=None, demo=True, lang='en_US', port=8869 ,**kwargs):

        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(dbname=dbname,workdir=workdir, demo=demo, lang=lang, port=port, addonsdir=addonsdir)
        self.args = {'dbname': dbname,'workdir':workdir, 'demo':demo, 'lang':lang, 'port' : port, 'addonsdir' : addonsdir}
        self.dbname = dbname
        # Compute defaults for descriptions:
        description = ["creating db"]
        self.description = description

    def start(self):
        self.args['command']=["make","Makefile","create-db"]
        if self.args['dbname']:
            self.args['command'].append("database=%s"%(self.args['dbname']))
        if self.args['port']:
            self.args['command'].append("port=%s"%(self.args['port']))
        if self.args['demo']:
            self.args['command'].append("demo=%s"%(self.args['demo']))
        if self.args['addonsdir']:
            self.args['command'].append("addons-path=%s"%(self.args['addonsdir']))
        cmd = LoggedRemoteCommand("shell",self.args)        
        self.startCommand(cmd)
    
    def evaluateCommand(self, cmd):
        if cmd.rc != 0:
            return FAILURE
        return SUCCESS

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

    def __init__(self, dbname='test',workdir=None,port=8869,**kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(dbname=dbname,workdir=workdir,port=port)
        self.args = {'dbname': dbname,'workdir':workdir,'port':port}
        self.dbname = dbname
        # Compute defaults for descriptions:
        description = ["Dropping db"]
        self.description = description

    def start(self):
        self.args['command']=["make","Makefile","drop-db"]
        if self.args['dbname']:
            self.args['command'].append("database=%s"%(self.args['dbname']))
        if self.args['port']:
            self.args['command'].append("port=%s"%(self.args['port']))
        cmd = LoggedRemoteCommand("shell",self.args)        
        self.startCommand(cmd)

    def evaluateCommand(self, cmd):
        if cmd.rc != 0:
            return FAILURE
        return SUCCESS

class CheckQuality(LoggingBuildStep):
    name = 'check-quality'
    flunkOnFailure = True
    MESSAGES = ("ERROR", "CRITICAL", "WARNING")

    def describe(self, done=False,success=False,warn=False,fail=False):
        if done:
            if success:
                return ['Quality Checked  !']
            if warn:
                return ['Check quality had Warnings!']
            if fail:
                return ['Check quality Failed !']
        return self.description
    
    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True) 
        else:
            return self.describe(True, fail=True) 

    def __init__(self, dbname='test',workdir=None,addonsdir=None,netport=8970, port=8869 ,**kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(dbname=dbname,workdir=workdir,addonsdir=addonsdir,netport=netport, port=port)
        self.args = {'dbname': dbname, 'modules':'', 'port' :port,'workdir':workdir,'netport':netport,'addonsdir':addonsdir}
        self.dbname = dbname
        # Compute defaults for descriptions:
        description = ["checking quality"]

        self.description = description

    def start(self):
        s = self.build.getSourceStamp()
        modules = []
        for change in s.changes:
            files = (
                     change.files_added +
                     change.files_modified + 
                     [f[1] for f in change.files_renamed]
                     )
            for f in files:
                module = f.split('/')[0]
                if module in ('bin','Makefile','man','README','setup.cfg','setup.py','doc','MANIFEST.in','openerp.log','pixmaps','rpminstall_sh.txt','setup.nsi','win32'):
                    continue
                if module not in modules:
                    modules.append(str(module))
        
        self.args['modules'] = ','.join(modules)        
        if self.args['modules']:
            self.description.append(self.args['modules'])
            self.args['command']=["make","Makefile","check-quality"]

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
                continue
            elif line.find("CRITICAL") != -1:
                pos = line.find("CRITICAL") + len("CRITICAL") + 5
                m = "CRITICAL"
            elif line.find("Traceback") != -1:
                traceback_log = []
                pos = io.index(line)
                for line in io[pos:-3]:
                    traceback_log.append(line)
                self.addCompleteLog("Check-Quality : Traceback", "".join(traceback_log))
                break;
            elif line.find("WARNING") != -1:
                pos = line.find("WARNING") + len("WARNING") + 5
                m = "WARNING"
            else:
                continue
            line = line[pos:]
            summaries[m].append(line)
            counts[m] += 1
            
        for m in self.MESSAGES:
            if counts[m]:
                msg = "".join(summaries[m])
                if m == "ERROR":
                    self.build.reason = msg
                self.addCompleteLog("Check-Quality : %s" % m, msg)    
                self.setProperty("Check-Quality : %s" % m, counts[m]) 
        if sum(counts.values()):       
            self.setProperty("Check-Quality : MessageCount", sum(counts.values()))

        if logs.find('LOG PATH') != -1:
            path = logs.split('LOG PATH')[1]
            file_path = (path.split('\r'))[0]
            fp = open(file_path,'a+')
            data = pickle.load(fp)
            for module,values in data.items():
                new_detail = values[1]  + '''<head><link rel="stylesheet" type="text/css" href="%s/css/quality-log-style.css" media="all"/></head>''' %(buildbotURL)
                self.addHTMLLog(module+':Score(%s)'%(values[0]),new_detail)
                for test,detail in values[2].items():
                     if detail[1] != '':
                        index = detail[1].find('<html>') + len('<html>')
                        new_detail = detail[1][0:index] + '''<table class="table1"><tr><td class="td1"> Module </td><td class="td1"> : </td><th class="th1"> %s </th></tr><tr><td class="td1"> Test </td><td class="td1"> : </td><th class="th1"> %s </th></tr><tr><td class="td1"> Score </b></td><td class="td1"> : </td><th class="th1"> %s </th></table><hr/>'''%(module, test, detail[0]) + detail[1][index:]+ '''<head><link rel="stylesheet" type="text/css" href="%s/css/quality-log-style.css" media="all"/></head>''' %(buildbotURL)
                        self.addHTMLLog('%s - %s:Score(%s)'%(module,test,detail[0]),new_detail)


class Copy(LoggingBuildStep):
    name = 'copy'
    flunkOnFailure = False
    def describe(self, done=False):
        if done:
            return self.descriptionDone
        return self.description

    def __init__(self, branch=None, workdir=None, addonsdir=None, **kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(branch=branch,workdir=workdir, addonsdir=addonsdir)
        self.args = {'workdir': workdir, 'addonsdir':addonsdir}

        # Compute defaults for descriptions:
        description = ["copy", '"'+workdir+'"', "in", '"'+ addonsdir +'"']
        descriptionDone = ["copy", '"'+workdir+'"' , "in", '"' + addonsdir +'"']

        self.description = description
        self.descriptionDone = descriptionDone
        self.branch = branch
    def start(self):
        s = self.build.getSourceStamp()
        flag = False
        for change in s.changes:
            if change.branch == self.branch:
                flag = True
                break
        if flag:
            cmd = LoggedRemoteCommand("copy", self.args)
            self.startCommand(cmd)
        else:            
            cmd = LoggedRemoteCommand("dummy", self.args)
            self.startCommand(cmd)

class InstallTranslation(LoggingBuildStep):
    name = 'install-translation'
    flunkOnFailure = True
    flunkingIssues = ["ERROR","CRITICAL"]
    MESSAGES = ("ERROR", "CRITICAL", "WARNING")

    def describe(self, done=False,success=False,warn=False,fail=False):
        if done:
            if success:
                return ['Translation %s Installed Sucessfully!'%(','.join(self.pofiles))]
            if warn:
                return ['Translation %s Installed with Warnings!'%(','.join(self.pofiles))]
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

    def __init__(self,workdir=None, addonsdir=None,dbname=False,port=8869, netport=8870, **kwargs):
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

    def start(self):
        s = self.build.getSourceStamp()
        self.pofiles = []
        for change in s.changes:
            files = (
                     change.files_added +
                     change.files_modified + 
                     [f[1] for f in change.files_renamed]
                     )
            for f in files:
                fname,ext = os.path.splitext(f.split('/')[-1])
                if ext == '.po':
                    if 'bin' in f.split('/'):
                        addonsdir = ''
                    else:
                        addonsdir = self.args['addonsdir']+'/'
                    self.pofiles.append(addonsdir+f)
        if len(self.pofiles):
            commands = []
            commands = ["make","Makefile","install-translation"]        

            if self.args['addonsdir']:
                commands.append("addons-path=%s"%(self.args['addonsdir']))            
            if self.args['port']:
                commands.append("port=%s"%(self.args['port']))
            if self.args['dbname']:
                commands.append("database=%s"%(self.args['dbname']))            

            self.args['command'] = commands

            self.description += ["Files",":",",".join(self.pofiles),"on Server","http://localhost:%s"%(self.args['port'])]
            
            self.args['command'].append("i18n-import=%s"%(','.join(self.pofiles)))
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
                break;
                    
            elif line.find("INFO:") != -1:
                continue
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

        for m in self.MESSAGES:
            if counts[m]:
                msg = "".join(summaries[m])
                if m == "ERROR":
                    self.build.reason = msg
                self.addCompleteLog("Install-Translation : %s" % m, msg)    
                self.setProperty("Install-Translation : %s" % m, counts[m]) 
        if sum(counts.values()):       
            self.setProperty("Install-Translation : MessageCount", sum(counts.values()))

    def evaluateCommand(self, cmd):
        if cmd.rc != 0:
            return FAILURE
        for m in self.flunkingIssues:
            try:
                if self.getProperty("Install-Translation : %s" % m):
                    return FAILURE
            except:
                pass
        try:
            if self.getProperty("Install-Translation : MessageCount"):
                return WARNINGS
        except:
            pass
        return SUCCESS

class InstallModule(LoggingBuildStep):
    name = 'install-module'
    flunkOnFailure = True
    flunkingIssues = ["ERROR","CRITICAL"]
    MESSAGES = ("ERROR", "CRITICAL", "WARNING")

    def describe(self, done=False,success=False,warn=False,fail=False):
        if done:
            if success:
                return ['Module(s) %s installed Sucessfully!'%(self.args['modules'])]
            if warn:
                return ['Installed module(s) had Warnings!']
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
 
    def __init__(self,workdir=None, addonsdir=None, modules='', dbname=False,port=8869, netport=8870, **kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir,addonsdir=addonsdir,modules=modules, dbname=dbname, port=port, netport=netport)
        self.args = {'addonsdir': addonsdir,
                     'workdir': workdir,
                     'dbname' : dbname,
                     'modules' : modules,
                     'netport' : netport,
                     'port' : port,
        }
        self.name = 'install-module'
        self.description = ["Installing", "modules %s"%(self.args['modules']),"on Server","http://localhost:%s"%(self.args['port'])]

    def start(self):
        s = self.build.getSourceStamp()
        modules = []
        for change in s.changes:
            for f in change.files:
                module = f.split('/')[0]
                if module in ('bin','Makefile','man','README','setup.cfg','setup.py','doc','MANIFEST.in','openerp.log','pixmaps','rpminstall_sh.txt','setup.nsi','win32'):
                    continue
                if module not in modules:
                    modules.append(module)
        if len(modules):
            self.args['modules'] += ','.join(modules)  

        if self.args['modules']:
            self.args['command'] = ["make","Makefile","install-module"]
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
                break;
            elif line.find("INFO") != -1:
                continue                
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

        for m in self.MESSAGES:
            if counts[m]:
                msg = "".join(summaries[m])
                if m == "ERROR":
                    self.build.reason = msg
                self.addCompleteLog("Install-Module : %s" % m, msg)    
                self.setProperty("Install-Module : %s" % m, counts[m]) 
        if sum(counts.values()):
            self.setProperty("Install-Module : MessageCount", sum(counts.values()))

    def evaluateCommand(self, cmd):
        if cmd.rc != 0:
            return FAILURE
        for m in self.flunkingIssues:
            try:
                if self.getProperty("Install-Module : %s" % m):
                    return FAILURE
            except:
                pass   
        try:
            if self.getProperty("Install-Module : MessageCount"):
                return WARNINGS
        except:
            pass
        return SUCCESS


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
        Bzr.startVC(self,self.branch, revision, patch)
        
        
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
