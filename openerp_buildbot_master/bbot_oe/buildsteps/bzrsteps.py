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

from buildbot.process.buildstep import LoggingBuildStep, LoggedRemoteCommand
from buildbot.process.properties import WithProperties
from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS, EXCEPTION, SKIPPED
from buildbot.status.builder import TestResult
from buildbot.status.builder import Results as status_Results
from buildbot.steps.source import Bzr
from buildbot.steps.master import MasterShellCommand
from bbot_oe.lp_poller import MS_Service
from twisted.python import log
import re
#import os
#from openerp_libclient import tools
from openerp_libclient.tools import ustr
#from twisted.internet import defer

try:
    import cStringIO
    StringIO = cStringIO.StringIO
except ImportError:
    from StringIO import StringIO


class StdErrRemoteCommand(LoggedRemoteCommand):
    """Variation of LoggedRemoteCommand that separates stderr
    """

    def addStderr(self, data):
        self.logs['stderr'].addStderr(data)

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
        self.args['command'] += [ '-r', change.properties['hash']]
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
            return
        
        if isinstance(res, dict) and res.get('trigger'):
            return self.build.builder.botmaster.maybeStartBuildsForBuilder(res['trigger'])
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

    
    def __init__(self, proxied_bzrs={}, threshold=None, sync_mode=None, command=False, alt_branch=None, **kwargs):
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
                    '-l', alt_branch or WithProperties('%(branch_url)s'),
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

        self.addFactoryArguments(threshold=threshold, alt_branch=alt_branch)
        self.args = {'threshold': threshold, 'alt_branch': alt_branch}

    def doStepIf(self, *args):
        """ Check if this step needs to run
        """
        if self.build.result >= self.args['threshold']:
            return False
        else:
            return True

exported_buildsteps = [OpenObjectBzr, BzrMerge, BzrRevert,
        BzrStatTest, BzrCommitStats, BzrTagFailure,
        ProposeMerge, MergeToLP, BzrPerformMerge,
        BzrCommit, BzrSyncUp ]

#eof