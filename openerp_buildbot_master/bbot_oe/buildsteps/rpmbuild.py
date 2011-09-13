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
from buildbot.process.properties import WithProperties
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

    def _wrote_rpm(self, line, module, mgroupdict, fdict):
        """ Called to register an RPM written

            Conforms to the special API of LoggedOEmixin.createSummary()
        """
        rpm_key = fdict.get('rpm_key', 'RPMs')
        current_rpms = []
        if self.build.hasProperty(rpm_key):
            current_rpms = self.build.getProperty(rpm_key)

        current_rpms.append(mgroupdict['msg'].strip())
        self.build.setProperty(rpm_key, source=self.name, value=current_rpms)

    known_strs = [  (r'Processing files: *(?P<fname>.+?) *$', SUCCESS,
                                {'module_persist': True, 'module_from_fname': True} ),
                    (r'Provides:  *(?P<msg>.+)$', SUCCESS, {'test_name': 'provides'}),
                    (r'Requires\([\w]+\): *(?P<msg>.+)$', SUCCESS, {'test_name': 'requires'}),
                    (r'Requires: *(?P<msg>.+)$', SUCCESS, {'test_name': 'requires'}),
                    (r'Obsoletes: *(?P<msg>.+)$', SUCCESS, {'test_name': 'obsoletes'}),
                    (r'Conflicts: *(?P<msg>.+)$', SUCCESS, {'test_name': 'conflicts'}),
                    (r'Checking for unpackaged', SUCCESS,{'test_name': 'post_check'}),
                    (r'Wrote: *(?P<msg>.+)$', SUCCESS, {'test_name': 'out_rpms',
                                                        'call': _wrote_rpm}),
                    (r'Executing\(%(?P<test_name>[^\)]+)', SUCCESS),
                    (r'RPM build errors: *(?P<msg>.+)$', FAILURE, {'test_name': 'rest'}),
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

class RpmLint2(LoggedOEmixin, ShellCommand):
    name = "RPM Lint Test"
    description = ["Checking for RPM/SPEC issues"]
    descriptionDone = ["Finished checking RPM/SPEC issues"]
    haltOnFailure = False
    warnOnFailure = True

    renderables = [ 'specfile' ]
    _command = ['/usr/bin/rpmlint' ]

    known_strs = [  (r'(?P<fname>.+?): W: spelling-error (?P<msg>.+)$', WARNINGS,
                            {'module_from_fname': True, 'short': True, 'test_name': 'rpm spelling' }),
                    (r'(?P<fname>.+?): W: (?P<msg>.+)$', WARNINGS,
                            {'module_from_fname': True, 'short': True, 'test_name': 'rpmlint' }),
                    (r'(?P<fname>.+?): E: (?P<msg>.+)$', FAILURE,
                            {'module_from_fname': True, 'short': True, 'test_name': 'rpmlint' }),
                    (r'.*', SUCCESS),
                 ]

    def __init__(self,  workdir=None, specfile=None, rpmfiles='RPMs',
                part_subs=None, keeper_conf=None, command=_command, **kwargs):
        """ performs an RPM Lint check at specfile + rpmfiles

            @param rpmfiles the key to the RPMs property, will be looked up
                in self.build.properties
            @param specfile is a single filename
        """
        kwargs.setdefault('logEnviron', False)
        ShellCommand.__init__(self, command=command, workdir=workdir, **kwargs)
        LoggedOEmixin.__init__(self, workdir=workdir, part_subs=part_subs, keeper_conf=keeper_conf, **kwargs)
        self.remote_kwargs['workdir'] = self.workdir
        self.specfile = specfile
        self.rpmfiles = rpmfiles
        self.addFactoryArguments(specfile=specfile, workdir=self.workdir, rpmfiles=rpmfiles)

    def start(self):
        if self.specfile:
            self.command.append(self.specfile)

        if self.remote_kwargs.get('workdir') is None:
            self.remote_kwargs['workdir'] = self.workdir

        if self.rpmfiles and self.build.hasProperty(self.rpmfiles):
            self.command += self.build.getProperty(self.rpmfiles)

        return ShellCommand.start(self)

exported_buildsteps = [RpmBuild2, RpmLint2 ]
#eof
