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

from buildbot.steps import source

class GitStep(source.Git):
    def startVC(self, branch, revision, patch):
        # Override behaviour of Source.startVC and always use our branch
        # That's because Sourcestamp/Change will know the 'remote' branch name
        # while we need to issue a command for the local proxied one.
        return source.Git.startVC(self, self.branch, revision, patch)

exported_buildsteps = [GitStep, ]

#eof