# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Portions Copyright Buildbot Team Members
# Portions Copyright Dan Radez <dradez+buildbot@redhat.com>
# Portions Copyright Steve 'Ashcrow' Milner <smilner+buildbot@redhat.com>
# Portions Copyright P. Christeas <xrg@linux.gr>

"""
    RPM Building steps.

    Git-Build variant: this is a fork of the upstream buildbot class,
    adapted to automated RPM building.
"""

from buildbot.steps.shell import ShellCommand
from buildbot.process.buildstep import RemoteShellCommand
from bbot_oe.step_iface import LoggedOEmixin
from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS #, EXCEPTION, SKIPPED


class RpmBuild2(LoggedOEmixin, ShellCommand):
    """ Build an RPM from a .spec file inside the repository
    
        This step is adapted to "git-build" procedure, as supported
        by the git-rpmscripts in:
        http://git.hellug.gr/?p=xrg/gitscripts
        
        However, there is no explicit dependency on them. Any package
        with an embedded .spec file can be built (as long as the environment
        at the buildslave is also ready) like that.
    """

    name = "rpmbuilder"
    haltOnFailure = 1
    flunkOnFailure = 1
    description = ["RPMBUILD"]
    descriptionDone = ["RPMBUILD"]
    known_strs = [  (r'Processing files: *(?P<fname>.+?) *$', SUCCESS,
                                {'module_persist': True, 'module_from_fname': True} ),
                    (r'Provides:  *(?P<msg>.+)$', SUCCESS, {'test_name': 'provides'}),
                    (r'Requires\([\w]+\): *(?P<msg>.+)$', SUCCESS, {'test_name': 'requires'}),
                    (r'Requires: *(?P<msg>.+)$', SUCCESS, {'test_name': 'requires'}),
                    (r'Obsoletes: *(?P<msg>.+)$', SUCCESS, {'test_name': 'obsoletes'}),
                    (r'Conflicts: *(?P<msg>.+)$', SUCCESS, {'test_name': 'conflicts'}),
                    (r'Checking for unpackaged', SUCCESS,{'test_name': 'post_check'}),
                    (r'Wrote: *(?P<msg>.+)$', SUCCESS, {'test_name': 'out_rpms'}),
                    (r'Executing\(%(?P<test_name>[^\)]+)', SUCCESS),
                    (r'RPM build errors: *(?P<msg>.+)$', FAILURE),
                    (r'Finding +Provides:', SUCCESS, {'test_name': 'rest'}),
                    (r'Finding +Requires:', SUCCESS, {'test_name': 'rest'}),
                    (r'warning: (?P<msg>.+)$', WARNINGS),
                    (r'error:(?:.*\:)?(?P<msg>.+)$', FAILURE ),
                    (r'.*', SUCCESS), # this will copy the rest of lines into modules like prep, build, clean..
                 ]

    def __init__(self, workdir=None, buildmode='ba', specfile=None,
                part_subs=None, keeper_conf=None, **kwargs):
        """
        @type specfile: str
        @param specfile: the name of the spec file for the rpmbuild
        @type kwargs: dict
        @param kwargs: All further keyword arguments.
        
        Note: since the spec file will most usually be per project, aka. per 'component',
        this class can read the spec file location of the /component parts/, from a
        part that will (strictly) substitute 'spec' and have the search regex be
        the path to the spec file *unmodified*.
        """
        # TODO extra arguments
        ShellCommand.__init__(self, workdir=workdir, **kwargs)
        LoggedOEmixin.__init__(self, workdir=workdir, part_subs=part_subs, keeper_conf=keeper_conf, **kwargs)
        if keeper_conf and not specfile:
            for comp, rege_str, subst in keeper_conf['builder'].get('component_parts',[]):
                if subst == 'spec':
                    specfile = rege_str
                    break
        self.remote_kwargs['workdir'] = self.workdir
        self.specfile = specfile
        self.buildmode = buildmode
        self.addFactoryArguments(specfile=specfile, workdir=self.workdir, buildmode=buildmode)

    def start(self):
        """
        Buildbot Calls Me when it's time to start
        """

        if self.remote_kwargs.get('workdir') is None:
            self.remote_kwargs['workdir'] = self.workdir

        self.command = ['rpmbuild', '-' + self.buildmode, self.specfile]

        # create the actual RemoteShellCommand instance now

        kwargs = self.remote_kwargs
        kwargs['command'] = self.command
        cmd = RemoteShellCommand(**kwargs)
        self.setupEnvironment(cmd)
        self.checkForOldSlaveAndLogfiles()
        self.startCommand(cmd)

exported_buildsteps = [RpmBuild2, ]
#eof
