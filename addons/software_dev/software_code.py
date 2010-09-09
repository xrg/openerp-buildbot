# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2010 OpenERP SA. (http://www.openerp.com)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from tools.translate import _
from osv import fields, osv

repo_types = [('git', 'Git'), ('bzr', 'Bazaar'), ('hg', 'Mercurial'), 
        ('svn', 'Subversion')]

repo_families = [('github', 'Github'), ('lp', 'Launchpad'), ('gitweb', 'Git Web') ]

class software_repohost(osv.osv):
    """ A host can contain repositories
    
        We add it here, since the host may have users or special treatment
    """
    _name = 'software_dev.repohost'
    _description = 'Repository Host'
    _columns = {
        'name': fields.char('Name', required=True, size=64),
        'rtype': fields.selection(repo_types, 'Main Repo Type'),
        'base_url': fields.char('Location', size=1024),
        'browse_url': fields.char('Browse url', size=1024,
                help="The base url of web-browse service, if available"),
        'repo_ids': fields.one2many('software_dev.repo', 'host_id', 'Repositories'),
        'host_family': fields.selection(repo_families, 'Host type',
                help="A \"family\" of hosts this belongs to. The technology of the server." \
                    "Used to automatically compute urls and behaviour" ),
    }

    _defaults = {
    }
software_repohost()

class software_repo(osv.osv):
    _name = 'software_dev.repo'
    _description = 'Repository'
    _columns = {
        'name': fields.char('Name', required=True, size=64),
        'host_id': fields.many2one('software_dev.repohost', 'Host', required=True),
        'rtype': fields.selection(repo_types, 'Type', required=True),
        'base_url': fields.char('Location', size=1024),
        'proxy_location': fields.char('Proxy location', size=1024,
                help="A local path where this repository is replicated, for caching"),
        'slave_proxy_url': fields.char('Slave proxy url', size=1024,
                help="The url from which a slave bot can fetch the proxied repository content"),                
        'branch_ids': fields.one2many('software_dev.branch', 'repo_id', 'Branches'),
    }

    _defaults = {
    }

software_repo()

class software_branch(osv.osv):
    _name = 'software_dev.branch'
    _description = 'Code branch'
    
    def _get_fetch_url(self, cr, uid, ids, name, args, context=None):
        res = {}
        for b in self.browse(cr, uid, ids, context=context):
            family = b.repo_id.host_id.host_family
            url = None
            if family == 'github':
                url = "github..."
                # TODO
            elif family == 'lp':
                url = b.repo_id.host_id.base_url or 'lp:'
                if b.sub_url.startswith('~'):
                    url += b.sub_url
                else:
                    url += b.repo_id.base_url + '/'+ b.sub_url
            else:
                url = b.sub_url
            res[b.id] = url
        return res
    
    def _get_browse_url(self, cr, uid, ids, name, args, context=None):
        res = {}
        for b in self.browse(cr, uid, ids, context=context):
            family = b.repo_id.host_id.host_family
            if family == 'github':
                res[b.id] = "github..."
                # TODO
            else:
                res[b.id] = b.sub_url
        return res
    

    _columns = {
        'name': fields.char('Branch Name', required=True, size=64),
        'tech_code': fields.char('Tech name', size=128, select=1),
        'poll_interval': fields.integer('Poll interval',
                    help="Seconds interval to look for changes"),
        'repo_id': fields.many2one('software_dev.repo', 'Repository', required=True, select=1),
        'description': fields.text('Description'),
        'sub_url': fields.char('Branch URL', size=1024, required=True, 
                    help="Location of branch, sometimes relative to repository"),
        'fetch_url': fields.function(_get_fetch_url, string="Fetch URL",
                    type="char", method=True, readonly=True, size=1024,
                    help="The complete url used in the VCS to fetch that branch. For the master."),
        'browse_url': fields.function(_get_browse_url, string="Browse URL",
                    type="char", method=True, readonly=True, size=1024,
                    help="A http browse url, if available"),
    }

    _defaults = {
    }

software_branch()

class software_user(osv.osv):
    """ A VCS user is one identity that appears in VCS and we map to our users
    """
    _name = 'software_dev.vcs_user'
    _description = 'Developer in VCS'
    def _get_name(self, cr, uid, ids, name, args, context=None):
        res = {}
        for b in self.browse(cr, uid, ids, context=context):
            res[b.id] = (b.employee_id and b.employee_id.name) or b.userid
        return res


    _columns = {
        'name': fields.function(_get_name, string='Name', method=True, 
                    type='char', store=False, readonly=True),
        'host_id': fields.many2one('software_dev.repohost', 'Host', required=True,
                    select=1,
                    help="The host, aka. service where this user logs in"),
        'userid': fields.char('User identity', size=1024, required=True, select=1,
                    help="The unique identifier of the user in this host. " \
                        "Sometimes the email or login of the user in the host." ),
        'employee_id': fields.many2one('hr.employee', 'Employee'),
    }

    _defaults = {
    }
    
    _sql_constraints = [ ('host_user_uniq', 'UNIQUE(host_id, userid)', 'User id must be unique at host'), ]
   
software_user()

commit_types = [ ('reg', 'Regular'), ('merge', 'Merge'), ('single', 'Standalone'), 
            ]

class software_commit(osv.osv):
    """ An entry in the VCS
    """
    _name = 'software_dev.commit'
    _description = 'Code Commit'
    _columns = {
        'name': fields.char('Message', required=True, size=2048),
        'date': fields.datetime('Date', required=True),
        'branch_id': fields.many2one('software_dev.branch', 'Branch', required=True, select=1),
        'hash': fields.char('Hash', size=1024, select=1,
                help="In repos that support it, a unique hash of the commit"),
        'revno': fields.char('Revision', size=128, select=1,
                help="Sequential revision number, in repos that have one"),
        'tag_descr': fields.char('Tag name', size=256,
                help="In some repos, have tag name or description of commit relative to tag"),
        'ctype': fields.selection(commit_types, 'Commit type', required=True),
        'comitter_id': fields.many2one('software_dev.vcs_user', 'Committer', required=True),
        'author_ids': fields.many2many('software_dev.vcs_user', 
                'software_dev_commit_authors_rel', 'commit_id', 'author_id', 'Authors',
                help="Developers who have authored the code"),
        'change_ids': fields.one2many('software_dev.filechange', 'commit_id', 'Changes'),
        'parent_id': fields.many2one('software_dev.commit', 'Parent commit'),
        'contained_commit_ids': fields.many2many('software_dev.commit', 
            'software_dev_commit_cont_rel', 'end_commit_id', 'sub_commit_id',
            help="Commits that are contained in this, but not the parent commit"),
    }
    
    _sql_constraints = [ ('hash_uniq', 'UNIQUE(hash)', 'Hash must be unique.'),
                ('branch_revno_uniq', 'UNIQUE(branch_id, revno)', 'Revision no. must be unique in branch'),
                ]

    _defaults = {
        'ctype': 'reg',
    }

software_commit()

change_types = [ ('a', 'Add'), ('m', 'Modify'), ('d', 'Delete'), 
                ('c', 'Copy'), ('r', 'Rename') ]

class software_filechange(osv.osv):
    """ Detail of commit: change to a file
    """
    _name = 'software_dev.filechange'
    _description = 'Code File Change'
    _columns = {
        'commit_id': fields.many2one('software_dev.commit','Commit', required=True),
        'filename': fields.char('File Name', required=True, size=1024, select=1),
        'ctype': fields.selection(change_types, 'Change type', required=True,
                help="The type of change that occured to the file"),
        'lines_add': fields.integer('Lines added'),
        'lines_rem': fields.integer('Lines removed'),
    }
    _defaults = {
    }
    
    _sql_constraints = [( 'commit_file_uniq', 'UNIQUE(commit_id, filename)', 'Commit cannot contain same file twice'), ]

software_filechange()


class software_component2(osv.osv):
    """ Enhance the software component object with branch/commit fields
    """
    _inherit = "software_dev.component"
    
    _columns = {
        'branch_id': fields.many2one('software_dev.branch', 'Branch', required=True, select=1),
        'commit_id': fields.many2one('software_dev.commit','Commit',),
        'update_rev': fields.boolean('Update commit', required=True, 
                help="Auto update to the latest commit from branch, or else stay at the commit specified."),
    }
    
    _defaults = {
        'update_rev': True,
    }

software_component2()
#eof