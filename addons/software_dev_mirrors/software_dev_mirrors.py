# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Software Development Solution
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

class softdev_branch_collection(osv.osv):
    """ A branch collection defines the mirroring of one repo to another

        It should contain all branches of each repo to be exported, plus
        any number of "is_imported" branches of mirroring repos.

        As the branch collection is the container of unique marks, such
        a collection must only be used for equivalent repositories,
        for example "openobject-addons" in bzr, "addons" in git.

        The existence of "is_imported" branches is only necessary when one
        of the repos is /only/ used to import (has no exported branches).
    """
    _name = 'software_dev.mirrors.branch_collection'

    _columns = {
        'name': fields.char('Name', size=128, required=True, select=True),
        'buildbot_id': fields.many2one('software_dev.buildbot', 'Buildbot', required=True, select=True,
                            help="Buildbot master which will perform the mirroring operations"),
        'branch_ids': fields.one2many('software_dev.branch', 'branch_collection_id',
                string='Branches',
                help="All branches that participate in the sync. Their mapping "
                    "will also be based on each branch'es tech_code."),
        }

    def get_id_for_repo(self, cr, uid, repo_id, context=None):
        """ Return the branch_collection id that corresponds to some repo

            @return single collection id (integer) or None if not available.
                May raise exception if 2 collections are connected to one repo
        """

        repo_bro = self.pool.get('software_dev.repo').browse(cr, uid, repo_id, context=context)

        ret_id = None
        for br in repo_bro.branch_ids:
            if br.branch_collection_id:
                if ret_id and br.branch_collection_id.id != ret_id:
                    raise osv.orm.except_orm(_('Data error'), _('Multiple branch collections are mapped to repo %d') % repo_id)
                ret_id = br.branch_collection_id.id
            # and keep the loop

        return ret_id

    def get_builders(self, cr, uid, ids, context=None):
        """ Format list of dicts for builders to send to buildbot
        """
        ret = []
        for bcol in self.browse(cr, uid, ids, context=context):
            dir_name = 'Mirror-' + bcol.name
            dir_name = dir_name.replace(' ', '_').replace('/','_')
            #db_name = dir_name.replace('-','_') # FIXME unused

            bret = { 'name': 'Mirror-' + bcol.name,
                    'builddir': dir_name,
                    'steps': [],
                    'properties': { 'group': 'Mirroring' }, # 'sequence': bldr.sequence, },
                    'scheduler': 'none', # bldr.scheduler, *0*
                    # 'tstimer': None, # means one build per change
                    }

            bret['slavenames'] = [ sl.tech_code \
                    for sl in bcol.buildbot_id.slave_ids \
                    if sl.do_mirroring or not (sl.dedicated or sl.test_ids) ]

            # Steps for export-import
            # Step A: for every repository, update the marks file if needed
            repos_done = set()
            for bbra in bcol.branch_ids:
                if bbra.repo_id.id in repos_done:
                    continue

                rp = bbra.repo_id
                if rp.rtype == 'git':
                    stepname = 'ExportGitMarks'
                elif rp.rtype == 'bzr':
                    stepname = 'ExportBzrMarks'
                else:
                    continue
                sname = 'Download marks for %s' % rp.name
                bret['steps'].append((stepname, { 'name': sname, 'repo_id': rp.id, 'repo_dir': rp.proxy_location}))
                repos_done.add(rp.id)

            # Step B: for every exported branch, fast-export it to a bundle file
            for bbra in bcol.branch_ids:
                repos_done = set([bbra.repo_id.id,])
                if bbra.is_imported:
                    continue

                rp = bbra.repo_id
                if rp.rtype == 'git':
                    stepname = 'FastExportGit'
                elif rp.rtype == 'bzr':
                    stepname = 'FastExportBzr'
                else:
                    continue

                sname = 'Export %s branch %s' % (rp.rtype, bbra.name)
                branch_name = bbra.tech_code or \
                                (bbra.sub_url.replace('/','_').replace('~','').replace('@','_'))
                fi_file = 'import-%s.fi' % branch_name
                local_branch = False
                if rp.local_prefix:
                    local_branch = rp.local_prefix + \
                                bbra.sub_url.replace('/','_').replace('~','').replace('@','_')
                bret['steps'].append((stepname, { 'name': sname, 'repo_id': rp.id,
                            'repo_dir': rp.proxy_location,
                            'branch_name': branch_name,
                            'local_branch': local_branch,
                            'fi_file': fi_file,
                            }))

                # Step C.n for every remaining repo, fast-import that branch
                for tbra in bcol.branch_ids:
                    rp = tbra.repo_id
                    if rp.id in repos_done:
                        continue

                    if rp.rtype == 'git':
                        stepname = 'FastImportGit'
                    elif rp.rtype == 'bzr':
                        stepname = 'FastImportBzr'
                    else:
                        continue

                    sname = 'Import in %s' % rp.name
                    bret['steps'].append((stepname, { 'name': sname,
                            'repo_id': rp.id,
                            'repo_dir': rp.proxy_location,
                            'fi_file': fi_file, }))
                    repos_done.add(rp.id)

            # Step D: for every repository, read the marks file and update db
            repos_done = set()
            for bbra in bcol.branch_ids:
                if bbra.repo_id.id in repos_done:
                    continue

                rp = bbra.repo_id
                if rp.rtype == 'git':
                    stepname = 'ImportGitMarks'
                elif rp.rtype == 'bzr':
                    stepname = 'ImportBzrMarks'
                else:
                    continue
                sname = 'Upload marks for %s' % rp.name
                bret['steps'].append((stepname, {'name': sname, 'repo_id': rp.id, 'repo_dir': rp.proxy_location}))
                repos_done.add(rp.id)

            ret.append(bret)
        return ret

softdev_branch_collection()

class software_dev_branch(osv.osv):
    _inherit = "software_dev.branch"

    _columns = {
        'branch_collection_id': fields.many2one('software_dev.mirrors.branch_collection',
                string="Branch collection",
                help="If set, this branch will be mirrored to other repos through that collection. "
                    "Only one collection is allowed."),
        'is_imported': fields.boolean('Imported', required=True,
                help="If set, this branch will not be polled, but instead import commits "
                    "from the other branches of the collection"),
        }

    _defaults = {
        'is_imported': False,
    }

    def _fmt_branch(self, branch_bro, fixed_commit=False):
        res = super(software_dev_branch, self)._fmt_branch(branch_bro, fixed_commit=fixed_commit)
        # print "res:", res
        return res

software_dev_branch()

class software_dev_buildbot(osv.osv):
    _inherit = 'software_dev.buildbot'

    def _iter_polled_branches(self, cr, uid, ids, context=None):

        for ib in super(software_dev_buildbot, self).\
                _iter_polled_branches(cr, uid, ids, context=context):
            yield ib

        bcol_obj = self.pool.get('software_dev.mirrors.branch_collection')

        for bcol in bcol_obj.browse(cr, uid, [('buildbot_id', 'in', ids)], context=context):
            for ib in bcol.branch_ids:
                yield ib

    def get_builders(self, cr, uid, ids, context=None):
        ret = super(software_dev_buildbot, self).get_builders(cr, uid, ids, context=context)
        bs_obj = self.pool.get('software_dev.mirrors.branch_collection')
        for bid in bs_obj.browse(cr, uid, [('buildbot_id', 'in', ids)], context=context):
            r = bid.get_builders(context=context)
            ret += r
        return ret

software_dev_buildbot()

class softdev_commit_mapping(osv.osv):
    _name = "software_dev.mirrors.commitmap"
    _description = "Commit Map"
    _rec_name = 'mark'

    _columns = {
        'mark': fields.char('Mark', size=64, required=True,
                help="Fastexport mark, uniquely identifiesc commit in a branch collection"),
        'collection_id': fields.many2one('software_dev.mirrors.branch_collection',
                string="Branch Collection", required=True ),
        'commit_ids': fields.one2many('software_dev.commit', 'commitmap_id',
                string="Commits"),
        }

    _sql_constraints = [ ('unique_mark', 'UNIQUE(mark, collection_id)', "Marks must be unique per collection")]

    def feed_marks(self, cr, uid, repo_id, marks_map, context=None):
        """ Upload a set of marks for a given repo

            @param repo_id a repository these marks come from
            @param a map of mark:hash entries (against the repository)
        """

        commit_obj = self.pool.get('software_dev.commit')
        col_id = self.pool.get('software_dev.mirrors.branch_collection').\
                    get_id_for_repo(cr, uid, repo_id, context=context)
        if not col_id:
            raise osv.orm.except_orm(_('Setup Error'),
                _('There is no branch collection for any branch of repository %d') % repo_id)

        known_marks = {}
        for res in self.search_read(cr, uid, [('mark', 'in', marks_map.keys()), ('collection_id', '=', col_id)],
                    fields=['mark'], context=context):
            known_marks[res['mark']] = res['id']

        branch_rest_id = self.pool.get('software_dev.repo').\
                        get_rest_branch(cr, uid, repo_id, context=context)

        errors = {}
        processed = 0
        skipped = 0
        for mark, shash in marks_map.items():
            # Get the commit:
            new_commit_id = None
            commit_id = commit_obj.search_read(cr, uid,
                    [('hash', '=', shash),
                    ('branch_id', 'in', [('repo_id', '=', repo_id)])],
                    fields=['commitmap_id'],
                    context=context)
            if not commit_id:
                new_commit_id = commit_obj.create(cr, uid,
                        { 'hash': shash, 'ctype': 'incomplete',
                            'branch_id': branch_rest_id},
                        context=context)
            else:
                assert len(commit_id) == 1, "Got %d commits for unique hash!?" % len(commit_id)
            if mark in known_marks:
                if commit_id and commit_id[0]['commitmap_id']:
                    if commit_id[0]['commitmap_id'][0] == known_marks[mark]:
                        skipped += 1 # it's already there
                    else:
                        errors.setdefault('double-mapped',[]).append(shash)
                else:
                    # the hard part: make sure the mark is not already referencing
                    # any commit at the same repo
                    for cmt in self.browse(cr, uid, known_marks[mark], context=context).commit_ids:
                        if cmt.branch_id.repo_id.id == repo_id:
                            errors.setdefault('mark-conflict', []).append(mark)
                            break
                    else:
                        # we're clear: existing mark doesn't have commit of our
                        # repo, add it
                        if commit_id:
                            cmt_id = commit_id[0]['id']
                        else:
                            cmt_id = new_commit_id
                        commit_obj.write(cr, uid, [cmt_id], {'commitmap_id': known_marks[mark]}, context=context)
                        processed += 1
            else:
                # it's a new one
                if commit_id:
                    if commit_id[0]['commitmap_id']:
                        errors.setdefault('double-mapped',[]).append(shash)
                        continue
                    cmt_id = commit_id[0]['id']
                else:
                    cmt_id = new_commit_id

                self.create(cr, uid, {'mark': mark, 'collection_id': col_id,
                        'commit_ids': [(6,0, [cmt_id])] }, context=context)
                processed += 1

        return dict(processed=processed, skipped=skipped, errors=errors)

    def get_marks(self, cr, uid, repo_id, context=None):
        """ Retrieve the marks mapping for a repository
            @return a dict of mark:hash entries

            @note This call may return a large set of resutls. It would be
            a little dangerous not to export them all in one go.
        """
        col_id = self.pool.get('software_dev.mirrors.branch_collection').\
                    get_id_for_repo(cr, uid, repo_id, context=context)
        if not col_id:
            raise osv.orm.except_orm(_('Setup Error'),
                _('There is no branch collection for any branch of repository %d') % repo_id)

        res_marks = {}
        commit_obj = self.pool.get('software_dev.commit')
        for cres in commit_obj.search_read(cr, uid,
                    [   ('commitmap_id','in', [('collection_id', '=', col_id)]),
                        ('branch_id', 'in', [('repo_id', '=', repo_id)])
                    ],
                    fields=['hash', 'commitmap_id'],
                    context=context):
            res_marks[cres['commitmap_id'][1]] = cres['hash']

        return res_marks

softdev_commit_mapping()

class software_dev_commit(osv.osv):
    _inherit = "software_dev.commit"

    _columns = {
        'commitmap_id': fields.many2one('software_dev.mirrors.commitmap',
                string="Mark",
                select=True,
                help="When this commit is exported/imported from other repos, link "
                    "to the other commits"),
        }

software_dev_commit()

class software_dev_buildset(osv.osv):
    _inherit = "software_dev.buildset"

    _columns = {
        'commit_id': fields.inherit(required=False),
        }

    #def createBuildRequests(self, cr, uid, id, builderNames, context=None):
    # TODO

software_dev_buildset()

class software_dev_buildrequest(osv.osv):
    _inherit = "software_dev.buildrequest"

    def _get_buildername(self, cr, uid, ids, name, args, context=None):
        """ Get the string representation of the builder, from either buildseries or branch_collection
        """
        res = {}
        for b in self.browse(cr, uid, ids, context=context):
            if b.builder_id:
                res[b.id] = b.builder_id.buildername
            elif b.mirrorbuilder_id:
                res[b.id] = 'Mirror-%s' % b.mirrorbuilder_id.name
        return res

    def _get_buildbot(self, cr, uid, ids, name, args, context=None):
        """ Get the string representation of the builder, from either buildseries or branch_collection
        """
        res = {}
        for b in self.browse(cr, uid, ids, context=context):
            if b.builder_id:
                res[b.id] = b.builder_id.builder_id.id
            elif b.mirrorbuilder_id:
                res[b.id] = b.mirrorbuilder_id.buildbot_id.id
        return res

    _columns = {
        'builder_id': fields.inherit(required=False),
        'mirrorbuilder_id': fields.many2one('software_dev.mirrors.branch_collection', 'Collection Builder',
                help="This can be specified instead of the Builder, for buildsets of mirroring"),
        'buildername': fields.function(_get_buildername, method=True, type='char', size=256, readonly=True), # convert from related to function
        'buildbot_id': fields.function(_get_buildbot, method=True, type='many2one', obj='software_dev.buildbot', readonly=True),
    }

software_dev_buildrequest()

class software_dev_bbslave(osv.osv):
    _inherit = "software_dev.bbslave"
    _columns = {
        'do_mirroring': fields.boolean('Do mirroring'),
        }

    _defaults = {
        'do_mirroring': True,
    }

software_dev_bbslave()

#eof