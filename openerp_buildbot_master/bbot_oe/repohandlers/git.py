# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP Buildbot
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

from bbot_oe.repo_iface import RepoFactory
from buildbot.changes.gitmultipoller import GitMultiPoller
from twisted.internet import utils, defer
from twisted.python import log, failure
import os
from buildbot.util import epoch2datetime

class GitPoller_OE(GitMultiPoller):
    """ Enhanced subclass to fit OpenERP backend, record more data

    """
    log_arguments = ['--first-parent', '--name-status']
    def __init__(self, branch, localBranch=None, allHistory=False, **kwargs):
        branch_id = kwargs.pop('branch_id') # mandatory
        bspecs = [(branch, localBranch or branch, {'branch_id': branch_id}),]
        GitMultiPoller.__init__(self, branchSpecs=bspecs, allHistory=allHistory, **kwargs)
        self.branch_id = branch_id
        self.log_fields.update(author_name='%an', author_timestamp='%at',
                parent_hashes='%P',committer_name='%cn', committer_email='%cE'
                # commit notes? Or isn't there a way to fetch them from remote anyway?
                )

    def _get_commit_files3(self, rev):
        """Get list of commit files and diff stats

            The second part, list lines added/removed at files
        """
        # git show HEAD --no-walk --numstat --format='%n'
        args = ['log', rev, '--numstat', '--no-walk', r'--format=%n']
        d = utils.getProcessOutput(self.gitbin, args, path=self.workdir, env=dict(PATH=os.environ['PATH']), errortoo=False )
        def process(git_output):
            fileDic = {}
            for x in git_output.split('\n'):
                if not x:
                    continue
                add, rem, fname = x.split('\t',2)
                fileDic[fname] = (add, rem)
            return fileDic
        d.addCallback(process)
        return d

    def _doAddChange(self, branch, revDict, historic=False, props=None):
        """ do last steps and add the change
        
            unlike the parent function, we need to defer one more task,
            of getting the commitstats of each commit (separately)
        """
        assert isinstance(props, dict)
        
        def _final_add(files3):
            
            # files 2: (name, status), parse from plain string list
            files2 = {}
            for x in revDict.pop('files'):
                if not x:
                    continue
                status, fname = x.split('\t',1)
                files2[fname] = status

            #process the files
            filesb = []
            for fname, stats in files3.items():
                if stats == ('-', '-'):
                    stats = (False, False)
                else:
                    stats = map(int, stats)

                if not fname in files2:
                    # it was cleanly merged
                    filesb.append(dict(filename=fname, ctype='f',
                            merge_add=stats[0], merge_rem=stats[1]))
                else:
                    status = files2[fname]
                    ctype = '?'
                    for letter in 'MDARC': #ordered by importance
                        if letter in status:
                            ctype = letter.lower()
                            break
                    filesb.append(dict(filename=fname, ctype=ctype,
                            lines_add=stats[0], lines_rem=stats[1]))

            properties = dict(branch_id=props['branch_id'], hash=revDict['hash'],
                    filesb=filesb, author_name=revDict.get('author_name', False))
            if 'parent_hashes' in revDict:
                properties['parent_hashes'] = map(str.strip, revDict['parent_hashes'].split())

            if revDict.get('committer_email') and revDict['committer_email'] != revDict['name']:
                # the openerp-server side will swap the fields, then
                properties['committer_email'] = revDict['committer_email']
                properties['committer_name'] = revDict.get('committer_name')

            if revDict.get('notes'):
                properties['notes'] = revDict['notes'] # any formatting?

            comments = revDict['subject'] + '\n\n' + revDict['body']
            d = self.master.addChange(
                    author=revDict['name'] or properties['author_name'],
                    revision=revDict['hash'],
                    files=[],
                    comments=comments,
                    when_timestamp=epoch2datetime(float(revDict['timestamp'])),
                    branch=branch,
                    category=self.category,
                    project=self.project,
                    repository=self.repourl,
                    properties=properties,
                    skip_build=historic)
            return d

        d = self._get_commit_files3(revDict['hash'])
        d.addCallback(_final_add)
        return d

    @defer.deferredGenerator
    def rescan_commits(self, branch, commSpecs, standalone=True):
        """ Rescan and register arbitrary commits from commSpecs

            @param branch the branch name, to satisfy buildbot's Change()
            @param commSpecs a list of 2-item tuples:
                (commit, props)
            @param standalone causes the algorithm to only list the
                specific commits. Otherwise, lists the full history of
                each commit since the known branches
        """
        log.msg("Processing %d commits" % len(commSpecs))
        if self.format_str is None:
            self.format_str = self._prepare_format_str()
            # would we ever need to change that dynamically?

        currentBranches = None
        if not standalone:
            currentBranches = [ '%s/%s' % (self.remoteName, branch) \
                                for branch, localBranch, p in self.branchSpecs ]
            # print "allHistory, already know:", currentBranches

        for commit, props in commSpecs:
            revListArgs = ['log',] + self.log_arguments + \
                    [ '--format=' + self.format_str,]
            if standalone:
                if '--first-parent' in revListArgs:
                    revListArgs.remove('--first-parent')
                revListArgs.append('--no-walk')
                revListArgs.append(commit)
            else: # not standalone
                # so, we need to scan the full history of that commit
                # We need a starting point, so we'll use the merge base of all other
                # branches to this
                if currentBranches:
                    if commit in currentBranches:
                        continue
                    d = utils.getProcessOutput(self.gitbin,
                                    ['merge-base', '--octopus', commit ] + currentBranches, path=self.workdir,
                                    env=dict(PATH=os.environ['PATH']), errortoo=False )
                    wfd = defer.waitForDeferred(d)
                    yield wfd
                    results = wfd.getResult()
                    assert results, "No merge-base result"
                    merge_base = results.strip()
                    if merge_base.startswith(commit):
                        revListArgs.append(commit)
                    else:
                        revListArgs.append('%s..%s' % (merge_base, commit))
                        currentBranches.append(merge_base)
                else:
                    # no other branch existed before this, so scan till the dawn of time
                    revListArgs.append(commit)
                currentBranches.append(commit) # mark its contents as known

            # hope it's not too much output ...
            # log.msg("gitpoller: revListArgs: %s" % ' '.join(revListArgs))
            d = utils.getProcessOutput(self.gitbin, revListArgs, path=self.workdir,
                                    env=dict(PATH=os.environ['PATH']), errortoo=False )

            def errb(res):
                log.err("Cannot scan commit %s: %s" %(commit, res))
                return None

            d.addErrback(errb)

            wfd = defer.waitForDeferred(d)
            yield wfd
            results = wfd.getResult()

            if not results:
                log.msg("No info for commit %s" % commit)
                # TODO mark the issue
                continue

            dl = self._parse_log_results(results, branch, localBranch='other', props=props, historic_mode=True)
            if dl is None:
                continue

            assert isinstance(dl, defer.Deferred), type(dl)
            wfd = defer.waitForDeferred(dl)
            yield wfd
            wfd.getResult()
        # end for

    def _process_changes_failure(self, f):
        log.err(f, 'gitpoller: repo poll failed')
        # eat the failure to continue along the defered chain - we still want to catch up
        self.master.db.sendMessage('Git poll:',
                        'Git poller for %s at %s cannot process changes.',
                        (self.repourl, self.workdir),
                        instance=f)

        return None


    def _catch_up_failure(self, f):
        log.err(f, 'gitpoller: please resolve issues in local repo: %s' % self.workdir)
        # this used to stop the service, but this is (a) unfriendly to tests and (b)
        # likely to leave the error message lost in a sea of other log messages
        self.master.db.sendMessage('Git catch up:',
                        'Git poller for %s at %s cannot catch up.',
                        (self.repourl, self.workdir),
                        instance=f)

    def _stop_on_failure(self, f, message=None):
        "utility method to stop the service when a failure occurs"
        self.master.db.sendMessage('Stopping gitpoller:',
                        '%s, git poller for %s had to stop. ',
                        (message or 'Error', self.repourl),
                        instance=f)
        if self.running:
            d = defer.maybeDeferred(lambda : self.stopService())
            d.addErrback(log.err, 'while stopping broken GitPoller service')
        return None

class GitMultiPoller_OE(GitPoller_OE):
    """ Enhanced subclass to fit OpenERP backend, record more data

    """
    def __init__(self, localBranch=None, allHistory=False, **kwargs):
        GitMultiPoller.__init__(self, allHistory=allHistory, **kwargs)
        # note: we *skip* GitPoller_OE.__init__ !
        self.branch_id = None
        self.log_fields.update(author_name='%an', author_timestamp='%at',
                parent_hashes='%P',committer_name='%cn', committer_email='%cE'
                # commit notes? Or isn't there a way to fetch them from remote anyway?
                )

class GitFactory(RepoFactory):
    @classmethod
    def createPoller(cls, poller_dict, conf, tmpconf):
        pbr = poller_dict
        p_interval = int(pbr.get('poll_interval', 600))
        # Early bail-out
        if p_interval <= 0:
            return

        kwargs = {'bare': True} # tmpconf['poller_kwargs'].copy()

        if 'remote_name' in pbr:
            kwargs['remoteName'] = pbr['remote_name']

        if 'workdir' in pbr:
            kwargs['workdir'] = os.path.expanduser(pbr['workdir'])

        pbr_mode = pbr.get('mode', 'branch')

        kwargs.update (repourl=pbr['repourl'],
                pollInterval = p_interval)

        if 'allHistory' in pbr:
            kwargs['allHistory'] = pbr['allHistory']

        category = '' # TODO: revise
        if 'group' in pbr:
            category = pbr['group'].replace('/','_').replace('\\','_') # etc.
            kwargs['category'] = pbr['group']

        def _create_singlebranch():
            kwargs.update( branch=pbr.get('branch_path', 'master'),
                            branch_id=pbr['branch_id'])
            if 'local_branch' in pbr:
                kwargs['localBranch'] = pbr['local_branch']

            conf['change_source'].append(GitPoller_OE(**kwargs))

        def _create_multibranch():
            kwargs['branchSpecs'] = []
            for bs in pbr['branch_specs']:
                branch = bs.get('branch_path', 'master')
                props = dict(branch_id=bs['branch_id'] )
                local_branch = bs.get('local_branch', branch)
                if bs.get('is_imported', False):
                    branch = False
                if 'last_head' in bs:
                    props['last_head'] = bs['last_head']
                t = ( branch, local_branch, props )
                kwargs['branchSpecs'].append(t)

            conf['change_source'].append(GitMultiPoller_OE(**kwargs))

        if  pbr_mode == 'branch':
            return _create_singlebranch()
        elif pbr_mode == 'multibranch':
            return _create_multibranch()
        else:
            raise ValueError("Cannot handle %s mode yet" % pbr['mode'])

repo_types = { 'git': GitFactory }
