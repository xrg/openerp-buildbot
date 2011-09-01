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
    
    def _get_repo_url(self, cr, uid, ids, name, args, context=None):
        """ Get a URL for accessing the repo (maybe pseydo)
        
            For git repositories, this is the real fetch URL. For bzr ones
            this /may/ be the repository (collection) one.
        """
        res = {}
        for b in self.browse(cr, uid, ids, context=context):
            family = b.host_id.host_family
            url = None
            if family == 'github':
                url = b.host_id.base_url or 'git://github.com'
                url += '/' + b.base_url
            elif family == 'gitweb':
                url = b.host_id.base_url
                url += '/' + b.base_url
            elif family == 'lp':
                url = b.host_id.base_url or 'lp:'
                if not (url.endswith(':') or url.endswith('/')):
                    url += '/'
                url += b.base_url
            elif b.rtype in ('git', 'bzr'):
                url = b.host_id.base_url
                url += '/' + b.base_url
            else:
                # FIXME!
                url = '#%s/%s' % (b.host_id.id, b.id)
            res[b.id] = url
        return res

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
        'repo_url': fields.function(_get_repo_url, string="Repo URL",
                    type="char", method=True, readonly=True, size=1024,
                    help="URL of the repository"),
    }

    _defaults = {
    }

    def get_rest_branch(self, cr, uid, ids, context=None):
        """ Get the branch which will hold "rest of" commits

            For some repositories, there can be commits that don't seem
            to belong to any of the known/polled branches. An example is
            with git repos and parent (incomplete, sometimes) commits
            of the ones that belong to our branch.

            A generic "rest" branch is the best way to keep the commit
            associated to the right repo. It will be an 'imported', never
            polled one and with a name that won't conflict with any
            possible existing branches.

            The name, so far, is '::rest' to make it distinct from any
            real ones.
        """
        if isinstance(ids, (int,long)):
            rid = ids
        elif isinstance(ids, list):
            assert len(ids) == 1, "Can only accept one id, not %r" % ids
            rid = ids[0]
        else:
            raise TypeError("ids must be int/list, not %s" % type(ids))
        branch_obj = self.pool.get('software_dev.branch')

        sids = branch_obj.search(cr, uid, [('repo_id', '=', rid),
                        ('sub_url', '=', '::rest')],
                        context=context)
        if sids:
            return sids[0]
        else:
            return branch_obj.create(cr, uid, {'repo_id': rid,
                    'name': '::rest', 'sub_url': '::rest', 'is_imported': True,
                    'poll_interval': -1}, context=context)

software_repo()

class software_branch(osv.osv):
    _name = 'software_dev.branch'
    _description = 'Code branch'

    def _get_fetch_url(self, cr, uid, ids, name, args, context=None):
        res = {}
        for b in self.browse(cr, uid, ids, context=context):
            family = b.repo_id.host_id.host_family
            url = None
            if family == 'lp':
                url = b.repo_id.host_id.base_url or 'lp:'
                if b.sub_url.startswith('~'):
                    url += b.sub_url
                elif '@' in b.sub_url:
                    luser, lurl = b.sub_url.split('@', 1)
                    url += '~%s/%s/%s'% (luser, b.repo_id.base_url, lurl)
                else:
                    url += b.repo_id.base_url + '/'+ b.sub_url
            elif b.repo_id.rtype == 'git':
                url = b.repo_id.repo_url
            else:
                url = b.repo_id.repo_url
                url += '/' + b.sub_url
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
            elif family == 'lp':
                url = b.repo_id.host_id.browse_url or 'http://bazaar.launchpad.net'
                if not url.endswith('/'):
                    url += '/'
                if b.sub_url.startswith('~'):
                    url += b.sub_url
                elif '@' in b.sub_url:
                    luser, lurl = b.sub_url.split('@', 1)
                    url += '~%s/%s/%s'% (luser, b.repo_id.base_url, lurl)
                else:
                    url += b.repo_id.base_url + '/'+ b.sub_url
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

    def _fmt_branch(self, branch_bro, fixed_commit=False):
        """Format the branch info into a dictionary
        
           Only meant to be used internally
        """
        dret = {}
        dret['branch_id'] = branch_bro.id
        dret['repo_id'] = branch_bro.repo_id.id
        dret['rtype'] = branch_bro.repo_id.rtype
        dret['branch_path'] = branch_bro.tech_code or \
                (branch_bro.sub_url.replace('/','_').replace('~','').replace('@','_'))
        dret['repourl'] = branch_bro.repo_id.repo_url
        dret['fetch_url'] = branch_bro.fetch_url
        dret['poll_interval'] = branch_bro.poll_interval

        dret['workdir'] = branch_bro.repo_id.proxy_location
        if branch_bro.repo_id.local_prefix:
            dret['local_branch'] = branch_bro.repo_id.local_prefix + \
                branch_bro.sub_url.replace('/','_').replace('~','').replace('@','_')
            dret['remote_name'] = branch_bro.repo_id.local_prefix.rstrip('-_./+')

        if branch_bro.repo_id.rtype == 'bzr':
            # Fetch last revision
            commit_obj = self.pool.get('software_dev.commit')
            cids = commit_obj.search_read(branch_bro._cr, branch_bro._uid, [('branch_id', '=', branch_bro.id)],
                    order='id desc', limit=1, fields=['revno'], context=branch_bro._context)
            if cids:
                dret['last_revision'] = int(cids[0]['revno'])
        return dret

software_branch()

class software_user(osv.osv):
    """ A VCS user is one identity that appears in VCS and we map to our users
    """
    _name = 'software_dev.vcs_user'
    _description = 'Developer in VCS'
    def _get_name(self, cr, uid, ids, name, args, context=None):
        res = {}
        for b in self.browse(cr, uid, ids, context=context):
            if b.employee_id:
                res[b.id] = b.employee_id.name
            elif b.partner_address_id:
                res[b.id] = b.partner_address_id.name
            else:
                res[b.id] = b.userid
        return res


    _columns = {
        'name': fields.function(_get_name, string='Name', method=True, size=256,
                    type='char', store=False, readonly=True),
        'host_id': fields.many2one('software_dev.repohost', 'Host', required=True,
                    select=1,
                    help="The host, aka. service where this user logs in"),
        'userid': fields.char('User identity', size=1024, required=True, select=1,
                    help="The unique identifier of the user in this host. " \
                        "Sometimes the email or login of the user in the host."),
        'employee_id': fields.many2one('hr.employee', 'Employee',
                    help="If the developer is an employee, connect to his record."),
        'partner_address_id': fields.many2one('res.partner.address', 'Partner Address',
                    help="For other developers, connect to known partners, "
                        "through an address record."),
        'temp_name': fields.char('Explicit Name', size=256,
                    help="Stores the name temporarily, until an employee or partner "
                        "is connected to this user"),
    }
    _defaults = {
    }

    def get_user(self, cr, uid, hostid, userid, temp_name=None, context=None):
        """Return the id of the user with that name, even create one
        """
        ud = self.search(cr, uid, [('host_id', '=', hostid),('userid', '=', userid)], context=context)
        if ud:
            return ud[0]
        else:
            return self.create(cr, uid, { 'host_id': hostid, 'userid': userid,
                    'temp_name': temp_name or False }, context=context)

    _sql_constraints = [ ('host_user_uniq', 'UNIQUE(host_id, userid)', 'User id must be unique at host'), 
            ('use_one_name', 'CHECK((employee_id IS NULL) OR (partner_address_id IS NULL))', 
                'You can only define either Employee or Partner for a user'),
        ]

    def connect_users(self, cr, uid, ids=None, auto_partners=False, context=None):
        """ Lookup and connect (map) VCS users to HR employees or partners
        """
        if ids is None or ids is False: # note we allow '[]'
            ids = [ ('employee_id', '=', False), ('partner_address_id', '=', False)]

        warnings = []
        ready_users = []
        for bro in self.browse(cr, uid, ids, context=context):
            user_rec = {}
            if bro.host_id.rtype in ('git', 'bzr', 'hg'):
                if '<' in bro.userid or '>' in bro.userid:
                    warnings.append( _("User id \"%s\" is full email, please split into name and email") % bro.userid)
                    continue
                user_rec['lookup_email'] = bro.userid
            if bro.temp_name:
                user_rec['name'] = bro.temp_name
            if user_rec:
                user_rec['id'] = bro.id
                user_rec['userid'] = bro.userid
                ready_users.append(user_rec)

        emails = {}
        for ru in ready_users:
            if 'lookup_email' in ru:
                emails[ru['lookup_email']] = None
        # first try, look them up on employees
        for hru in self.pool.get('hr.employee').\
                search_read(cr, uid, [('work_email', 'in', emails.keys())], \
                    fields=['work_email'], context=context):
            emails[hru['work_email']] = ('employee_id', hru['id'])

        # second try, lookup the rest in res.partner.address
        rest_emails = [ email for email, res in emails.items() if not res]
        if rest_emails:
            for rau in self.pool.get('res.partner.address').\
                    search_read(cr, uid, [('email', 'in', rest_emails)],
                                fields=['email'], context=context):
                emails[rau['email']] = ('address_id', rau['id'])

        # update them in ready_users
        for ru in ready_users:
            if not ru['lookup_email']:
                continue
            res = emails.get(ru['lookup_email'])
            if not res:
                continue
            ru[res[0]] = res[1]
            if len(res) > 2:
                ru[res[2]] = res[3]

        # now, an extra step: For those who have a partner_id, lookup if
        # that partner is connected to an employee
        for ru in ready_users:
            if ('employee_id' not in ru) and ru.get('address_id'):
                res = self.pool.get('hr.employee').search(cr,uid,
                        ['|', ('address_id', '=', ru['address_id']), 
                            ('address_home_id', '=', ru['address_id'])],
                        limit=1, context=context)
                if res:
                    ru['employee_id'] = res[0]

        # so, we should have all data in ready_users
        for ru in ready_users:
            if ru.get('employee_id'):
                self.write(cr, uid, [ru['id'],], {'employee_id': ru['employee_id'],
                        'partner_address_id': False, 'temp_name': False}, context=context)
            elif ru.get('address_id'):
                self.write(cr, uid, [ru['id'],], {'partner_address_id': ru['address_id'], 
                        'temp_name': False}, context=context)
            elif auto_partners:
                address_id = None
                if 'lookup_email' in ru:
                    if emails.get(ru['lookup_email']):
                        res = emails[ru['lookup_email']]
                        assert res[0] == 'address_id', "Where did %r happen?" % res
                        address_id = res[1]
                if not address_id:
                    # create a new address record
                    name = ru.get('name', False) or ru['userid'].split('@',1)[0]
                    address_id = self.pool.get('res.partner.address').\
                            create(cr,uid, {'name': name, 'type': 'contact',
                                    'email': ru.get('lookup_email', False)}, context=context)
                    # note that this may bork with 'base_contact' module
                if address_id:
                    self.write(cr, uid, [ru['id'],], {'partner_address_id': address_id,
                            'temp_name': False}, context=context)

        if warnings:
            return {'warning': '\n'.join(warnings)}

        return {}

software_user()

commit_types = [ ('reg', 'Regular'), ('merge', 'Merge'), ('single', 'Standalone'),
            ('incomplete', 'Incomplete')]

class software_commit(propertyMix, osv.osv):
    """ An entry in the VCS
    """
    _name = 'software_dev.commit'
    _description = 'Code Commit'
    _function_field_browse = True

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
        'branch_id': fields.many2one('software_dev.branch', 'Branch', select=1, required=True),
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
        branch_rest_id = None
        repo_bro = None
        if not branch_id:
            repo_id = extra.get('repo_id')
            if not repo_id:
                raise ValueError("No branch_id nor repo_id specified for commit")
            repo_bro = self.pool.get('software_dev.repo').browse(cr, uid, repo_id, context=context)
            branch_id = repo_bro.get_rest_branch(context=context)
            branch_rest_id = branch_id
        assert branch_id # or discover it from repository + branch

        cr.execute('LOCK TABLE "%s" IN SHARE ROW EXCLUSIVE MODE;' % self._table, debug=self._debug)
        cmts = self.search_read(cr, uid, [('hash','=', extra.get('hash', False))],
                        fields=['ctype', 'branch_id', 'hash'], context=context)
        if cmts:
            # This is the case where buildbot attempts to send us a commit
            # for a second time
            assert len(cmts) == 1
            for cmt in cmts:
                assert cmt['hash']
                if cmt['ctype'] == 'incomplete':
                    cid = cmt['id']
                    # and let code below fill the incomplete commit
                # TODO: what if it belongs to the 'rest' branch and we need to update?
                elif branch_id and cmt['branch_id'][0] != branch_id:
                    # we need the boolean result, no need to read()
                    brs = self.pool.get('software_dev.branch').search(cr, uid,
                                [('id','=', cmt['branch_id'][0]), ('sub_url', '=','::rest')],
                                context=context)
                    if brs:
                        # old was '::rest', new isn't. Update
                        self.write(cr, uid, cmt['id'], {'branch_id': branch_id}, context=context)
                    elif self._debug:
                        osv.orm._logger.debug('%s: submit_change() ' \
                                'not updating branch of commit %s, ' \
                                'because old #%d,%s branch is not the "rest" one',
                                self._name, cmt['id'], cmt['branch_id'][0], cmt['branch_id'][1])
                    return cmt['id']
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
            if not repo_bro:
                repo_bro = self.pool.get('software_dev.branch').browse(cr, uid, branch_id, context=context).repo_id
            repohost =  repo_bro.host_id.id
            comitter_id = None
            authors = []
            if 'committer_email' in extra:
                # we have both committer and author
                comitter_id = user_obj.get_user(cr, uid, repohost, 
                    extra['committer_email'], temp_name=extra.get('committer_name', False), context=context)
                authors.append(user_obj.get_user(cr, uid, repohost, 
                    cdict['author'], temp_name=extra.get('author_name', False), context=context))
            else:
                # the committer is the author
                comitter_id = user_obj.get_user(cr, uid, repohost, 
                    cdict['author'], temp_name=extra.get('author_name', False), context=context)
            if 'authors' in extra:
                authors += [ user_obj.get_user(cr, uid, repohost, usr, context=context)
                            for usr in extra.get('authors', []) ]

            new_vals = {
                'subject': subj,
                'description': descr,
                'comitter_id': comitter_id,
                'date': datetime.fromtimestamp(cdict['when']),
                'branch_id': branch_id,
                'hash': extra.get('hash', False),
                'ctype': 'single',
                'author_ids': [(6,0, authors)],
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
                    if not branch_rest_id:
                        branch_rest_id = repo_bro.get_rest_branch(context=context)
                    parent_hash2id[khash] = self.create(cr, uid, \
                        { 'hash': khash, 'ctype': 'incomplete', 'branch_id': branch_rest_id},
                        context=context)
                
                new_vals['parent_id'] = parent_hash2id[extra['parent_hashes'][0]]
                new_vals['ctype'] = 'reg'
                if len(extra['parent_hashes']) > 1:
                    extra_ids = set([ parent_hash2id[khash] for khash in extra['parent_hashes'][1:]])
                    new_vals['contained_commit_ids'] = [(6, 0, list(extra_ids) )]
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
                'lines_add': cstats.get('lines_add', False),
                'lines_rem': cstats.get('lines_rem', False),
                'merge_add': cstats.get('merge_add', False),
                'merge_rem': cstats.get('merge_rem', False),
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
                authors:    list of strings (deprecated)
                committer:  Name of committer
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
                'author': False,
                'when': tdate,
                'comments': cmt.subject,
                'links': [],
                'revlink': False, # TODO
                'revision': (cmt.branch_id.repo_id.rtype != 'git' and cmt.revno) or False,
                'branch': cmt.branch_id.get_local_url(context=context)[cmt.branch_id.id][1],
                'repository': cmt.branch_id.repo_id.repo_url,
                'project': False,
                'category': False,
                'extra': {},
                }

            if cmt.author_ids:
                cdict['author'] = cmt.author_ids[0].name
                cdict['extra']['committer'] = cmt.comitter_id.name
            else:
                cdict['author'] = cmt.comitter_id.name

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
                
            # TODO: other parents

            for cf in cmt.change_ids:
                props['filesb'].append( {
                        'filename': cf.filename,
                        'ctype': cf.ctype,
                        'lines_add': cf.lines_add,
                        'lines_rem': cf.lines_rem,
                        'merge_add': cf.merge_add,
                        'merge_rem': cf.merge_rem,
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
        'commit_id': fields.many2one('software_dev.commit','Commit', required=True, ondelete="cascade"),
        'filename': fields.char('File Name', required=True, size=1024, select=1),
        'ctype': fields.selection(change_types, 'Change type', required=True,
                help="The type of change that occured to the file"),
        'lines_add': fields.integer('Lines added'),
        'lines_rem': fields.integer('Lines removed'),
        'merge_add': fields.integer('Lines merged in'),
        'merge_rem': fields.integer('Lines merged out'),
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
        'merge_add': fields.integer('Lines merged in'),
        'merge_rem': fields.integer('Lines merged out'),
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
