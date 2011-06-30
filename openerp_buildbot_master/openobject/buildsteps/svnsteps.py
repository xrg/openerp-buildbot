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

from buildbot.steps.source import SVN
from buildbot.process.buildstep import LoggingBuildStep
# from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS, EXCEPTION, SKIPPED


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

exported_buildsteps = [OpenObjectSVN, ]

#eof
