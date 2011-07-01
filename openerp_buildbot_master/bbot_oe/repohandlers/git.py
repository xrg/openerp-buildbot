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
from buildbot.changes.gitpoller import GitPoller

class GitFactory(RepoFactory):
    @classmethod
    def createPoller(cls, poller_dict, conf, tmpconf):
        pbr = poller_dict
        if pbr.get('mode', 'branch') != 'branch':
            raise ValueError("Cannot handle %s mode yet" % pbr['mode'])
        fetch_url = pbr['fetch_url']
        p_interval = int(pbr.get('poll_interval', 600))
        kwargs = tmpconf['poller_kwargs'].copy()
        category = ''
        if 'group' in pbr:
            category = pbr['group'].replace('/','_').replace('\\','_') # etc.
            kwargs['category'] = pbr['group']

        if p_interval > 0:
            conf['change_source'].append(GitPoller(fetch_url,
                poll_interval = p_interval,
                branch_name=pbr.get('branch_name', None),
                branch_id=pbr['branch_id'],
                            **kwargs))


repo_types = { 'git': GitFactory }
