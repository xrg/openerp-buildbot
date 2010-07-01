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
import base64
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

def create_test_step_log(step_object = None, step_name = ''):
    source = step_object.build.builder.test_ids
    properties = step_object.build.builder.openerp_properties
    openerp_host = properties.get('openerp_host', 'localhost')
    openerp_port = properties.get('openerp_port',8069)
    openerp_dbname = properties.get('openerp_dbname','buildbot')
    openerp_userid = properties.get('openerp_userid','admin')
    openerp_userpwd = properties.get('openerp_userpwd','a')
    revision = step_object.build.source.changes[0].revision

    openerp = buildbot_xmlrpc(host = openerp_host, port = openerp_port, dbname = openerp_dbname)
    openerp_uid = openerp.execute('common','login',  openerp.dbname, openerp_userid, openerp_userpwd)

    tested_branch = step_object.build.source.changes[0].branch
    args = [('url','ilike',tested_branch),('is_test_branch','=',False),('is_root_branch','=',False)]
    tested_branch_ids = openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.lp.branch','search',args)

    tested_branch_id = tested_branch_ids[0]
    last_revision_no_stored = properties.get(tested_branch_id, {}).get('latest_rev_no',0)
    last_revision_id_stored = properties.get(tested_branch_id, {}).get('latest_rev_id','')
    test_id = source.get(revision, False)
    summary = step_object.summaries
    for logname, data in summary.items():
        state = data.get('state', 'pass')
        if step_name in ('bzr-update', 'bzr_merge'):
            if state == 'fail':
                test_values = {'failure_reason':'This test has been skipped because the step %s has failed ! \n for more details please refer the Test steps tab.'%(step_name),'state':state}
                branch_values = {'latest_rev_no':last_revision_no_stored,'latest_rev_id':last_revision_id_stored}
                openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.lp.branch','write', [int(tested_branch_id)], branch_values)
                openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.test','write', [int(test_id)], test_values)
            openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.test','write', [int(test_id)],{'environment':step_object.env_info})

        params = {}
        params['name'] = logname
        params['test_id'] = int(test_id)
        if data.get('quality_log', False):
           params['quality_log'] = base64.encodestring('\n'.join(data['quality_log']))
        if data.get('log', False):
           params['log'] = base64.encodestring('\n'.join(data['log']))
#        if data.get('WARNING', False):
#            params['warning_log'] = '\n'.join(data['WARNING'])
#        if data.get('ERROR', False):
#            params['error_log'] = '\n'.join(data['ERROR'])
#        if data.get('CRITICAL', False):
#            params['critical_log'] = '\n'.join(data['CRITICAL'])
#        if data.get('INFO', False):
#            params['info_log'] = '\n'.join(data['INFO'])
#        if data.get('TEST', False):
#            params['yml_log'] = '\n'.join(data['TEST'])
#        if data.get('TRACEBACK', False):
#            params['traceback_detail'] = '\n'.join(data['TRACEBACK'])
        params['state'] = state
        openerp.execute('object', 'execute', openerp.dbname, openerp_uid, openerp_userpwd, 'buildbot.test.step','create',params)
    return True

class OpenERPLoggedRemoteCommand(LoggedRemoteCommand):
     def addToLog(self, logname, data):
        if logname in self.logs:
            self.logs[logname].addStdout(data)
        else:
            self.stdio_log = stdio_log = self.addLog("stdio")
            self.useLog(stdio_log, True)

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

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)

    def __init__(self, workdir=None, addonsdir=None, netport=8972, port=8869, **kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(workdir=workdir, addonsdir=addonsdir, netport=netport, port=port, logfiles={})
        self.args = {'port' :port, 'workdir':workdir, 'netport':netport, 'addonsdir':addonsdir, 'logfiles':{}}
        description = ["Performing OpenERP Test..."]
        self.description = description
        self.summaries = {}
        self.build_result = SUCCESS

    def start(self):
        #TODO FIX:
        # need to change the static slave path
        self.logfiles = {}
        builddir = self.build.builder.builddir
        full_addons = os.path.normpath(os.getcwd() + '../../openerp_buildbot_slave/build/%s/openerp-addons/'%(builddir))
        for module in os.listdir(full_addons):
            if module in ['.bzrignore','.bzr']:
                continue
            self.logfiles['%s'%module] = ('%s/%s/%s.html'%('test_logs', module, module))

        self.args['command']=["make","openerp-test"]
        self.args['logfiles'] = self.logfiles
        if self.args['addonsdir']:
            self.args['command'].append("addons-path=%s"%(self.args['addonsdir']))
        if self.args['netport']:
            self.args['command'].append("net_port=%s"%(self.args['netport']))
        if self.args['port']:
            self.args['command'].append("port=%s"%(self.args['port']))
        cmd = LoggedRemoteCommand("OpenObjectShell",self.args)
        self.startCommand(cmd)

    def createSummary(self, log):
        logs = self.cmd.logs
        buildbotURL = self.build.builder.botmaster.parent.buildbotURL

        for logname, log in logs.items():
            state = 'pass'
            if logname == 'stdio':
                continue
            log_data = log.getText()
            summaries = {logname:{}}
            general_log = []
            chk_qlty_log = []
            io = StringIO(log_data).readlines()
            for line in io:
                if line.find('Failed') != -1:
                    state = 'fail'
                    self.build_result = FAILURE
                if line.find("Final score") != -1:
                    pos = io.index(line)
                    for l in io[pos:]:
                        if l.find("Final score") != -1 and l.find("</div>") != -1:
                            l = l[ l.find("</div>") + 6:]
                        chk_qlty_log.append(l)
                    break
                general_log.append(line)

            summaries[logname]['state'] = state
            summaries[logname]['log'] = general_log
            summaries[logname]['quality_log'] = chk_qlty_log
            self.summaries.update(summaries)

    def evaluateCommand(self, cmd):
        res = SUCCESS
        if cmd.rc != 0 or self.build_result == FAILURE:
            res = FAILURE
        create_test_step_log(self)
        return res

class OpenObjectBzr(Bzr):
    flunkOnFailure = False
    haltOnFailure = True

    def describe(self, done=False,success=False,warn=False,fail=False):
         if done:
            if success:
                return ['Updated branch %s Sucessfully!'%(self.branch)]
            if warn:
                return ['Updated branch %s with Warnings!'%(self.branch)]
            if fail:
                return ['Updated branch %s Failed!'%(self.branch)]
         return self.description

    def getText(self, cmd, results):
        if results == SUCCESS:
            return self.describe(True, success=True)
        elif results == WARNINGS:
            return self.describe(True, warn=True)
        else:
            return self.describe(True, fail=True)

    def __init__(self, repourl=None, baseURL=None,
                 defaultBranch=None,workdir=None, mode='update', alwaysUseLatest=True, timeout=40*60, retry=None,**kwargs):
        LoggingBuildStep.__init__(self, **kwargs)
        Bzr.__init__(self, repourl=repourl, baseURL=baseURL,
                   defaultBranch=defaultBranch,workdir=workdir,mode=mode,alwaysUseLatest=alwaysUseLatest,timeout=timeout,
                   retry=retry,**kwargs)
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
            raise BuildSlaveTooOldError(m)

        if self.repourl:
        #    assert not branch # we need baseURL= to use branches
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

    def createSummary(self, log):
        io = StringIO(log.getText()).readlines()
        summaries = {self.name:{}}
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
        create_test_step_log(self, step_name=self.name)
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


#class CreateDB2(CreateDB):
#    def start(self):
#        cmd = LoggedRemoteCommand("create-db",self.args)
#        self.startCommand(cmd)
#
#class InstallModule2(InstallModule):
#    def start(self):
#        s = self.build.getSourceStamp()
#        modules = []
#        for change in s.changes:
#            for f in change.files:
#                try:
#                    module = f.split('/')
#                    if change.branch == 'https://svn.tinyerp.com/be/maintenance':
#                        module = (len(module) > 1) and module[1] or ''
#                    else:
#                        module = module[0]
#                    if module not in modules:
#                        if module not in ('README.txt'):
#                            modules.append(module)
#                except:
#                    pass
#        self.args['modules'] += ','.join(modules)
#        cmd = LoggedRemoteCommand("install-module",self.args)
#        self.startCommand(cmd)


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
        summaries = {self.name:{}}
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
        create_test_step_log(self, step_name='bzr_merge')
        return res

class BzrRevert(LoggingBuildStep):
    name = 'bzr-revert'
    flunkOnFailure = True
    haltOnFailure = True

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
        summaries = {self.name:{}}
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
        create_test_step_log(self, res)
        return res

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
