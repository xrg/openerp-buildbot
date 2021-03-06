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
    
    def __init__(self, rolling=False, **kwargs):
        source.Git.__init__(self, **kwargs)
        self.addFactoryArguments(rolling=rolling)
        self.rolling = rolling
        
    def computeSourceRevision(self, changes):
        if not changes:
            return None
        rev = changes[-1].revision
        if (not rev) and 'hash' in changes[-1].properties:
            rev = changes[-1].properties['hash']
        return rev

    def startVC(self, branch, revision, patch):
        if not self.rolling:
            # Override behaviour of Source.startVC and always use our branch
            branch = self.branch
        return source.Git.startVC(self, branch, revision, patch)

exported_buildsteps = [GitStep, ]

#eof