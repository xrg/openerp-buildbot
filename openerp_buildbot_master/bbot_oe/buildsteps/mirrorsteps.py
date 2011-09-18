# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
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

from buildbot.process.buildstep import BuildStep
from buildbot.steps.master import MasterShellCommand
# from bbot_oe.step_iface import LoggedOEmixin, StepOE
from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS #, EXCEPTION, SKIPPED
import os
from openerp_libclient import rpc
from twisted.internet import defer, threads
import marks_file

class _MarksProcessor:
    """ common class for marks import/export operations
    """
    haltOnFailure = True
    flunkOnFailure = True

    def __init__(self, repo_dir, repo_id, **kwargs):
        """
            @param repo_dir the working dir of the git repository
            @param repo_id the id of the repo in the db
            @param overwrite clobber and overwrite the marks file
        """
        if 'repo_dir' not in self.__class__.parms:
            self.__class__.parms = self.__class__.parms + ['repo_dir', 'repo_id', 'marks_file']
        self.marks_file = kwargs.get('marks_file', "fastexport.marks")

    def _set_fname(self):
        raise NotImplementedError

class _GitMarksProcessor(_MarksProcessor):

    def _set_fname(self):
        self.repo_dir = os.path.expanduser(self.repo_dir)
        if os.path.isdir(os.path.join(self.repo_dir,'.git')):
            self.marks_fname = os.path.join(self.repo_dir, '.git', self.marks_file)
        else:
            self.marks_fname = os.path.join(self.repo_dir, self.marks_file)

class ExportGitMarks(_GitMarksProcessor, BuildStep):
    """ Fetch fastexport marks and save them into repo dir. Git format
    """

    name = 'export-gitmarks'

    def __init__(self,overwrite=False, **kwargs):
        _GitMarksProcessor.__init__(self, **kwargs)
        BuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(overwrite=overwrite)
        self.overwrite = overwrite

    def start(self):
        self._set_fname()
        if (not self.overwrite) and os.path.isfile(self.marks_fname):
            self.step_status.setText(["No need to export git marks"])
            self.finished(SUCCESS)
            return
        d = threads.deferToThread(self._do_export)
        self.step_status.setText(["export git marks", self.marks_fname])
        return d

    def _do_export(self):
        cmap_proxy = rpc.RpcProxy('software_dev.mirrors.commitmap')
        try:
            marks_map = cmap_proxy.get_marks(self.repo_id)
            f = file(self.marks_fname, 'wb')
            for mark, revid in marks_map.iteritems():
                f.write('%s %s\n' % (mark, revid))
            f.close()
            self.step_status.setText(["exported git marks", self.marks_fname])
            self.finished(SUCCESS)
        except Exception, e:
            self.description = 'Failed to export marks'
            self.step_status.setText(['failed export' + str(e)])
            self.finished(FAILURE)

class _ImportMarksMixin:
    def _do_feed_marks(self, marks):
        cmap_proxy = rpc.RpcProxy('software_dev.mirrors.commitmap')
        res = cmap_proxy.feed_marks(self.repo_id, marks)

        if not res:
            print "No result from feed_marks()"
            return

        stext = ["Marks imported:",
                "%s processed / %s skipped" % \
                        (res.get('processed', 0), res.get('skipped', 0))
                ]

        if res.get('errors'):
            stext.append("Some errors reported: %s" % ', '.join(res['errors'].keys()))

            slog = ["Errors:" ]
            for e, r in res['errors'].items():
                slog.append("%s: %r" % (e, r))
            self.addCompleteLog('errors', '\n'.join(slog))
            self.finished(WARNINGS)
        else:
            self.finished(SUCCESS)

        self.step_status.setText(stext)

class ImportGitMarks(_GitMarksProcessor, _ImportMarksMixin, BuildStep):
    """ Load fastexport marks from repo dir into database. Git format
    """

    name = 'import-gitmarks'

    def __init__(self, **kwargs):
        _GitMarksProcessor.__init__(self, **kwargs)
        BuildStep.__init__(self, **kwargs)

    def start(self):
        self._set_fname()
        d = threads.deferToThread(self._do_import)
        self.step_status.setText(["importing git marks", self.marks_fname])
        return d

    def _do_import(self):
        try:
            f = file(self.marks_fname)

            # Read the marks
            marks = {}
            for line in f:
                line = line.rstrip('\n')
                mark, revid = line.split(' ', 1)
                marks[mark] = revid
            f.close()
            self._do_feed_marks(marks)

        except Exception, e:
            self.description = 'Failed to import marks'
            self.step_status.setText(['failed import' + str(e)])
            self.finished(FAILURE)

class FastExportGit(_GitMarksProcessor, MasterShellCommand):
    def __init__(self, branch_name=None, local_branch=None, fi_file=None, **kwargs):
        _GitMarksProcessor.__init__(self, **kwargs)
        kwargs.pop('command', None)
        if not kwargs.get('path'):
            kwargs['path'] = os.path.expanduser(kwargs.get('repo_dir') or '')
        MasterShellCommand.__init__(self, command=None, **kwargs)
        self.addFactoryArguments(branch_name=branch_name, local_branch=local_branch, fi_file=fi_file)
        self.branch_name = branch_name
        self.local_branch = local_branch
        self.fi_file = fi_file

    def start(self):
        self._set_fname()
        fi_file = os.path.join(self.step_status.build.builder.basedir, self.fi_file)
        self.command = [ 'git-fast-export.sh', self.branch_name, self.marks_fname, fi_file ]
        MasterShellCommand.start(self)

class FastImportGit(_GitMarksProcessor, MasterShellCommand):

    def __init__(self, fi_file=None, **kwargs):
        _GitMarksProcessor.__init__(self, **kwargs)
        kwargs.pop('command', None)
        if not kwargs.get('path'):
            kwargs['path'] = os.path.expanduser(kwargs.get('repo_dir'))
        MasterShellCommand.__init__(self, command=None, **kwargs)
        self.addFactoryArguments(fi_file=fi_file)
        self.fi_file = fi_file

    def start(self):
        self._set_fname()
        fi_file = os.path.join(self.step_status.build.builder.basedir, self.fi_file)
        self.command = [ 'git-fast-import.sh', self.marks_fname, fi_file ]
        MasterShellCommand.start(self)

# Bzr support classes:

class _BzrMarksProcessor(_MarksProcessor):

    def _set_fname(self):
        self.repo_dir = os.path.expanduser(self.repo_dir)
        self.marks_fname = os.path.join(self.repo_dir,
                '.bzr', 'repository',
                self.marks_file)

class ExportBzrMarks(_BzrMarksProcessor, BuildStep):
    """ Fetch fastexport marks and save them into repo dir. Git format
    """

    name = 'export-bzrmarks'

    def __init__(self, overwrite=False, **kwargs):
        _BzrMarksProcessor.__init__(self, **kwargs)
        BuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(overwrite=overwrite)
        self.overwrite = overwrite

    def start(self):
        self._set_fname()
        if (not self.overwrite) and os.path.isfile(self.marks_fname):
            self.step_status.setText(["No need to export bzr marks"])
            self.finished(SUCCESS)
            return
        d = threads.deferToThread(self._do_export)
        self.step_status.setText(["export bzr marks", self.marks_fname])
        return d

    def _do_export(self):
        cmap_proxy = rpc.RpcProxy('software_dev.mirrors.commitmap')
        try:
            marks_map = cmap_proxy.get_marks(self.repo_id)
            marks_file.export_marks(self.marks_fname, marks_map, {}) # TODO
            self.step_status.setText(["exported bzr marks", self.marks_fname])
            self.finished(SUCCESS)
        except Exception, e:
            self.description = 'Failed to export marks'
            self.step_status.setText(['failed export' + str(e)])
            self.finished(FAILURE)

class ImportBzrMarks(_BzrMarksProcessor, _ImportMarksMixin, BuildStep):
    """ Load fastexport marks from repo dir into database. Bzr format
    """

    name = 'import-bzrmarks'

    def __init__(self, **kwargs):
        _BzrMarksProcessor.__init__(self, **kwargs)
        BuildStep.__init__(self, **kwargs)

    def start(self):
        self._set_fname()
        d = threads.deferToThread(self._do_import)
        self.step_status.setText(["importing bzr marks", self.marks_fname])
        return d

    def _do_import(self):
        try:
            marks = marks_file.import_marks(self.marks_fname)[0]
            bad_marks = []
            for m in marks:
                if not m.startswith(':'):
                    if (':'+m) in marks:
                        print "Invalid mark %s" % m
                        bad_marks.append(m)
                    else:
                        marks[':'+m] = marks.pop(m)
            if bad_marks:
                raise Exception("Bad marks found")
            self._do_feed_marks(marks)

        except Exception, e:
            self.description = 'Failed to import marks'
            self.step_status.setText(['failed import:' + str(e)])
            self.finished(FAILURE)

class FastExportBzr(_BzrMarksProcessor, MasterShellCommand):

    def __init__(self, branch_name=None, local_branch=None, fi_file=None, **kwargs):
        _BzrMarksProcessor.__init__(self, **kwargs)
        kwargs.pop('command', None)
        if not kwargs.get('path'):
            kwargs['path'] = os.path.expanduser(kwargs.get('repo_dir'))
        MasterShellCommand.__init__(self, command=None, **kwargs)
        self.addFactoryArguments(branch_name=branch_name, local_branch=local_branch, fi_file=fi_file)
        self.branch_name = branch_name
        self.local_branch=local_branch
        self.fi_file=fi_file

    def start(self):
        self._set_fname()
        fi_file = os.path.join(self.step_status.build.builder.basedir, self.fi_file)
        self.command = [ 'bzr', 'fast-export',
                '--import-marks='+ self.marks_fname, '--export-marks='+ self.marks_fname,
                '--single-author', '-b', self.branch_name, '--no-tags',
                self.local_branch or self.branch_name,  fi_file ]
        MasterShellCommand.start(self)

class FastImportBzr(_BzrMarksProcessor, MasterShellCommand):

    def __init__(self, fi_file=None, **kwargs):
        _BzrMarksProcessor.__init__(self, **kwargs)
        kwargs.pop('command', None)
        if not kwargs.get('path'):
            kwargs['path'] = os.path.expanduser(kwargs.get('repo_dir'))
        MasterShellCommand.__init__(self, command=None, **kwargs)
        self.addFactoryArguments(fi_file=fi_file)
        self.fi_file=fi_file

    def start(self):
        self._set_fname()
        fi_file = os.path.join(self.step_status.build.builder.basedir, self.fi_file)
        self.command = [ 'bzr','fast-import',
                '--import-marks='+ self.marks_fname, '--export-marks='+ self.marks_fname,
                fi_file ]
        MasterShellCommand.start(self)

exported_buildsteps = [
        ExportGitMarks, ExportBzrMarks,
        ImportGitMarks, ImportBzrMarks,
        FastExportGit, FastExportBzr,
        FastImportGit, FastImportBzr,
        ]

#eof
