# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2010 OpenERP SA. (http://www.openerp.com)
#    Copyright (C) 2011 P. Christeas <xrg@hellug.gr>
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
from datetime import datetime
import time
from properties import propertyMix

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
        'local_prefix': fields.char('Local prefix', size=64,
                help="If the local proxy is shared among repos, prefix branch names with this, to avoid conflicts"),
        'branch_ids': fields.one2many('software_dev.branch', 'repo_id', 'Branches'),
    }

    _defaults = {
    }
    
    def _get_unique_url(self, cr, uid, ids, context=None):
        """ Get a unique string representation of the repository
        """
        ret = {}
        for bro in self.browse(cr, uid, ids, context=context):
            if bro.base_url:
                s = ''
                if bro.host_id.base_url:
                    s = bro.host_id.base_url
                elif bro.host_id.host_family == 'lp':
                    s = 'lp:'
                s += bro.base_url
                ret[bro.id] = s
            else:
                # FIXME!
                ret[bro.id] = '#%s/%s' % (bro.host_id.id, bro.id)
        
        return ret

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
                url = b.repo_id.host_id.base_url or 'git://github.com'
                url += '/' + b.repo_id.base_url
            elif family == 'gitweb':
                url = b.repo_id.host_id.base_url
                url += '/' + b.repo_id.base_url
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
                url = b.repo_id.host_id.browse_url or 'https://github.com'
                url += '/' + b.repo_id.base_url
            elif family == 'gitweb':
                url = b.repo_id.host_id.browse_url
                url += '/?p=' + b.repo_id.base_url
            else:
                url = b.sub_url
            res[b.id] = url
        return res


    _columns = {
        'name': fields.char('Branch Name', required=True, size=64),
        'tech_code': fields.char('Tech name', size=128, select=1),
        'poll_interval': fields.integer('Poll interval',
                    help="Seconds interval to look for changes", required=True),
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
        'poll_interval': 1800,
    }

    def get_local_url(self, cr, uid, ids, context=None):
        """ URL for buildslaves, possibly from local proxy
        
            @return (url, branch_name) to fit git needs
        """
        res = {}
        for b in self.browse(cr, uid, ids, context=context):
            if not b.repo_id.slave_proxy_url:
                res[b.id] = (b.fetch_url, b.sub_url)
            else:
                res[b.id] = (b.repo_id.slave_proxy_url, (b.repo_id.local_prefix or '') + b.sub_url)
        return res

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

    def get_user(self, cr, uid, hostid, userid, context=None):
        """Return the id of the user with that name, even create one
        """
        ud = self.search(cr, uid, [('host_id', '=', hostid),('userid', '=', userid)], context=context)
        if ud:
            return ud[0]
        else:
            return self.create(cr, uid, { 'host_id': hostid, 'userid': userid }, context=context)

    _sql_constraints = [ ('host_user_uniq', 'UNIQUE(host_id, userid)', 'User id must be unique at host'), ]

software_user()

commit_types = [ ('reg', 'Regular'), ('merge', 'Merge'), ('single', 'Standalone'),
            ('incomplete', 'Incomplete')]

class software_commit(propertyMix, osv.osv):
    """ An entry in the VCS
    """
    _name = 'software_dev.commit'
    _description = 'Code Commit'
    _function_fields_browse = True

    def _get_name(self, cr, uid, ids, name, args, context=None):
        res = {}
        for b in self.browse(cr, uid, ids, context=context):
            name = ''
            if b.revno:
                name += '#%s ' % (b.revno[:8])
            elif b.hash:
                name += '%s ' % b.hash[:8]
            name += b.subject or _('Incomplete')
            res[b.id] = name
        return res

    def name_search(self, cr, uid, name='', args=None, operator='ilike',  context=None, limit=None):
        if args is None:
            args = []
        if operator in ('ilike', 'like'):
            op2 = '='
        elif operator in ('not ilike', 'not like'):
            op2 = '!='
        else:
            op2 = operator
        domain = args + ['|', '|', ('hash', operator, name), ('revno', op2, name),
                        ('subject', operator, name)]
        return super(software_commit, self).name_search(cr, uid, None, domain,
                        operator=operator, limit=limit, context=context)

    _columns = {
        'name': fields.function(_get_name, string='Name', size=512,
                method=True, type='char', readonly=True),
        'subject': fields.char('Subject', size=256),
        'description': fields.text('Description'),

        'date': fields.datetime('Date',),
        'branch_id': fields.many2one('software_dev.branch', 'Branch', select=1),
        'hash': fields.char('Hash', size=1024, select=1,
                help="In repos that support it, a unique hash of the commit"),
        'revno': fields.char('Revision', size=128, select=1,
                help="Sequential revision number, in repos that have one"),
        'tag_descr': fields.char('Tag name', size=256,
                help="In some repos, have tag name or description of commit relative to tag"),
        'ctype': fields.selection(commit_types, 'Commit type', required=True),
        'comitter_id': fields.many2one('software_dev.vcs_user', 'Committer'),
        'author_ids': fields.many2many('software_dev.vcs_user',
                'software_dev_commit_authors_rel', 'commit_id', 'author_id', 'Authors',
                help="Developers who have authored the code"),
        'change_ids': fields.one2many('software_dev.filechange', 'commit_id', 'Changes'),
        'stat_ids': fields.one2many('software_dev.changestats', 'commit_id', 'Statistics'),
        'parent_id': fields.many2one('software_dev.commit', 'Parent commit'),
        # 'merge_id': fields.many2one('software_dev.commit', 'Commit to merge',
        #            help='If set, this is the second parent, which is merged with "Parent Commit"'),
        'contained_commit_ids': fields.many2many('software_dev.commit',
            'software_dev_commit_cont_rel', 'end_commit_id', 'sub_commit_id',
            string="Contained commits",
            help="Commits that are contained in this, but not the parent commit. " \
                "Secondary parent(s) in a merge commit."),
    }

    _sql_constraints = [ ('hash_uniq', 'UNIQUE(hash)', 'Hash must be unique.'),
                ('branch_revno_uniq', 'UNIQUE(branch_id, revno)', 'Revision no. must be unique in branch'),
                ]

    _defaults = {
        'ctype': 'reg',
    }

    def submit_change(self, cr, uid, cdict, context=None):
        """ Submit full info for a commit, in a dictionary
        
        Incomplete commits are /not/ allowed through this function, yet
        """
        assert isinstance(cdict, dict)
        user_obj = self.pool.get('software_dev.vcs_user')
        fchange_obj = self.pool.get('software_dev.filechange')
        cid = None

        clines = cdict['comments'].split('\n',1)
        subj = clines[0]
        descr = '\n'.join(clines[1:]).strip()

        extra = cdict.pop('extra')
        branch_id = extra.get('branch_id')
        assert branch_id # or discover it from repository + branch

        cr.execute('LOCK TABLE "%s" IN SHARE ROW EXCLUSIVE MODE;' % self._table, debug=self._debug)
        cmts = self.search_read(cr, uid, [('hash','=', extra.get('hash', False))],
                        fields=['ctype', 'branch_id', 'hash'])
        if cmts:
            # This is the case where buildbot attempts to send us a commit
            # for a second time
            assert len(cmts) == 1
            for cmt in cmts:
                assert cmt['hash']
                if cmt['ctype'] == 'incomplete':
                    cid = cmt['id']
                    # and let code below fill the incomplete commit
                else:
                    if self._debug:
                        osv.orm._logger.debug('%s: submit_change() returning existing commit %s',
                                self._name, cmt['id'])
                    return cmt['id']

        if True:
            # Prepare data fields
            if self._debug:
                osv.orm._logger.debug('%s: cdict: %r', self._name, cdict)
                osv.orm._logger.debug('%s: extra: %r', self._name, extra)
            repo_bro = self.pool.get('software_dev.branch').browse(cr, uid, branch_id, context=context).repo_id
            repohost =  repo_bro.host_id.id
            new_vals = {
                'subject': subj,
                'description': descr,
                'comitter_id': user_obj.get_user(cr, uid, repohost, cdict['author'], context=context),
                'date': datetime.fromtimestamp(cdict['when']),
                'branch_id': branch_id,
                'hash': extra.get('hash', False),
                'ctype': 'single',
                'authors': [ user_obj.get_user(cr, uid, repohost, usr, context=context)
                                for usr in extra.get('authors', []) ],
                }
            if repo_bro.rtype != 'git':
                new_vals['revno'] = cdict['revision']
            else:
                assert cdict['revision'] == extra.get('hash', False)
            if ('parent_hashes' in extra) and extra['parent_hashes']:
                parent_cmts = self.search_read(cr, uid, [('hash', 'in', extra['parent_hashes'])],
                                fields=['hash'], context=context)
                
                parent_hash2id = dict.fromkeys(extra['parent_hashes'])
                if parent_cmts:
                    for pc in parent_cmts:
                        assert pc['hash'] in parent_hash2id
                        parent_hash2id[pc['hash']] = pc['id']
                    
                for khash in parent_hash2id:
                    if parent_hash2id[khash] is not None:
                        # note, this may change during this iteration, too
                        continue
                    parent_hash2id[khash] = self.create(cr, uid, \
                        { 'hash': khash, 'ctype': 'incomplete'}, context=context)
                
                new_vals['parent_id'] = parent_hash2id[extra['parent_hashes'][0]]
                new_vals['ctype'] = 'reg'
                if len(extra['parent_hashes']) > 1:
                    new_vals['contained_commit_ids'] = [(6, 0, \
                                [ parent_hash2id[khash] for khash in extra['parent_hashes'][1:]])]
                    new_vals['ctype'] = 'merge'
        if cid:
            self.write(cr, uid, [cid,], new_vals, context=context)
        else: # a new commit
            cid = self.create(cr, uid, new_vals, context=context)

        if 'filesb' in extra:
            # try to submit from the detailed files member
            for cf in extra['filesb']:
                fval = { 'commit_id': cid,
                    'filename': cf['filename'],
                    'ctype': cf.get('ctype', 'm'),
                    'lines_add': cf.get('lines_add', 0),
                    'lines_rem': cf.get('lines_rem', 0),
                    }
                fchange_obj.create(cr, uid, fval, context=context)

        elif 'files' in cdict: # use the compatible list, eg. when migrating
            for cf in cdict['files']:
                fval = { 'commit_id': cid,
                    'filename': cf['name'],
                    }
                fchange_obj.create(cr, uid, fval, context=context)

        return cid

    def saveCStats(self, cr, uid, id, cstats, context=None):
        """Save the commit statistics
        """
        assert isinstance(id, (int, long))
        assert isinstance(cstats, dict), "%r" % cstats

        user_obj = self.pool.get('software_dev.vcs_user')
        cstat_obj = self.pool.get('software_dev.changestats')

        if cstats:
            repohost = self.browse(cr, uid, id, context=context).branch_id.repo_id.host_id.id
            sval = { 'commit_id': id,
                'author_id': user_obj.get_user(cr, uid, repohost, cstats['author'], context=context),
                'commits': cstats.get('commits', 0),
                'count_files': cstats.get('count_files', 0),
                'lines_add': cstats.get('lines_add', 0),
                'lines_rem': cstats.get('lines_rem', 0),
                }
            cstat_obj.create(cr, uid, sval, context=context)

        return True


    def getChanges(self, cr, uid, ids, context=None):
        """ Format the commits into a dictionary
        
            Output keys:
            
                changeid:   our id
                author:     main author
                when:       commit datetime (string)
                comments:   commit description
                links:      list of urls for web-browsing the change
                revlink:    links[0]
                revision:   revision id or hash (string)
                branch:     branch the revision belongs to
                repository: repo the revision belongs to. The
                    (repository, branch, revision) should be the unique id
                project:    ?
                cateogry:   group?
                extra: other data. Includes 'hash', 'authors', 'branch_id', 'filesb'
                    Dict of key: (value, source)
                
            Extra Properties:
                
                filesb:     list of (file, ...)
                hash:       the repo hash (if different from 'revision')
                branch_id:  reference to the branch, helps avoid lookups
                authors:    list of strings
        """
        # TODO
        ret = []
        for cmt in self.browse(cr, uid, ids, context=context):
            if cmt.ctype == 'incomplete':
                osv.orm._logger.debug('%s: skipping incomplete commit %d', self._name, cmt.id)
                continue
            if isinstance(cmt.date, basestring):
                dt = cmt.date.rsplit('.',1)[0]
                tdate = time.mktime(time.strptime(dt, '%Y-%m-%d %H:%M:%S'))
            else:
                tdate = time.mktime(cmt.date)
            cdict = {
                'changeid': cmt.id,
                'author': cmt.comitter_id.userid,
                'when': tdate,
                'comments': cmt.subject,
                'links': [],
                'revlink': False, # TODO
                'revision': (cmt.branch_id.repo_id.rtype != 'git' and cmt.revno) or False,
                'branch': cmt.branch_id.sub_url,
                'repository': cmt.branch_id.repo_id._get_unique_url(context=context)[cmt.branch_id.repo_id.id],
                'project': False,
                'category': False,
                'extra': {},
                }
            
            if cmt.description:
                cdict['comments'] += '\n\n' + cmt.description
            props = cdict['extra']
            props.update({
                'branch_id': cmt.branch_id.id,
                'filesb': [],
                'hash': cmt.hash,
                })
            if cmt.parent_id:
                props['parent_id'] = cmt.parent_id.id
                props['parent_revno'] = cmt.parent_id.revno

            for cf in cmt.change_ids:
                props['filesb'].append( {
                        'filename': cf.filename,
                        'ctype': cf.ctype,
                        'lines_add': cf.lines_add,
                        'lines_rem': cf.lines_rem,
                        })

            ret.append(cdict)
        return ret

software_commit()

change_types = [ ('a', 'Add'), ('m', 'Modify'), ('d', 'Delete'),
                ('c', 'Copy'), ('r', 'Rename'), ('f', 'Merged'),
                ('?', 'Unknown') ]

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
        'ctype': 'm',
    }

    _sql_constraints = [( 'commit_file_uniq', 'UNIQUE(commit_id, filename)', 'Commit cannot contain same file twice'), ]

software_filechange()

class software_changestats(osv.osv):
    """ Statistics of a change
    A change may contain more than one stats lines, grouped by author.
    """
    _name = 'software_dev.changestats'
    _description = 'Code File Change'
    _columns = {
        'commit_id': fields.many2one('software_dev.commit','Commit',
                required=True, ondelete='cascade'),
        'author_id': fields.many2one('software_dev.vcs_user', 'Author', required=True),
        'commits': fields.integer('Number of commits', required=True),
        'count_files': fields.integer('Files changed', required=True),
        'lines_add': fields.integer('Lines added', required=True),
        'lines_rem': fields.integer('Lines removed', required=True ),
    }
    _defaults = {
        'commits': 0,
        'count_files': 0,
        'lines_add': 0,
        'lines_rem': 0,
    }

    _sql_constraints = [( 'commit_author_uniq', 'UNIQUE(commit_id, author_id)', 'Commit stats cannot contain same author twice'), ]

software_changestats()


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
