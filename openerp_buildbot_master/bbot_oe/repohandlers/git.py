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
from twisted.internet import utils
from twisted.python import log
import os
from buildbot.util import epoch2datetime

class GitPoller_OE(GitMultiPoller):
    """ Enhanced subclass to fit OpenERP backend, record more data

    """
    log_arguments = ['--first-parent', '--name-status']
    def __init__(self, branch, localBranch=None, **kwargs):
        branch_id = kwargs.pop('branch_id') # mandatory
        bspecs = [(branch, localBranch or branch, {'branch_id': branch_id}),]
        GitMultiPoller.__init__(self, branchSpecs=bspecs, **kwargs)
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

    def _doAddChange(self, branch, revDict, props=None):
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
                    author=revDict['name'],
                    revision=revDict['hash'],
                    files=[],
                    comments=comments,
                    when_timestamp=epoch2datetime(float(revDict['timestamp'])),
                    branch=branch,
                    category=self.category,
                    project=self.project,
                    repository=self.repourl,
                    properties=properties)
            return d

        d = self._get_commit_files3(revDict['hash'])
        d.addCallback(_final_add)
        return d

class GitFactory(RepoFactory):
    @classmethod
    def createPoller(cls, poller_dict, conf, tmpconf):
        pbr = poller_dict
        if pbr.get('mode', 'branch') != 'branch':
            raise ValueError("Cannot handle %s mode yet" % pbr['mode'])
        fetch_url = pbr['fetch_url']
        p_interval = int(pbr.get('poll_interval', 600))
        # Early bail-out
        if p_interval <= 0:
            return

        kwargs = {'bare': True} # tmpconf['poller_kwargs'].copy()

        kwargs.update (repourl=fetch_url,
                pollInterval = p_interval,
                branch=pbr.get('branch_path', 'master'),
                branch_id=pbr['branch_id'],)

        if 'local_branch' in pbr:
            kwargs['localBranch'] = pbr['local_branch']

        if 'remote_name' in pbr:
            kwargs['remoteName'] = pbr['remote_name']

        if 'workdir' in pbr:
            kwargs['workdir'] = os.path.expanduser(pbr['workdir'])

        category = '' # TODO: revise
        if 'group' in pbr:
            category = pbr['group'].replace('/','_').replace('\\','_') # etc.
            kwargs['category'] = pbr['group']

        conf['change_source'].append(GitPoller_OE(**kwargs))


repo_types = { 'git': GitFactory }
