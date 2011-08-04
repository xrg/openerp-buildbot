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
                if ret_id:
                    raise osv.orm.except_orm(_('Data error'), _('Multiple branch collections are mapped to repo %d') % repo_id)
                ret_id = br.branch_collection_id.id
            # and keep the loop

        return ret_id

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
            @param a map of mark:hash entries (ageinst the repository)
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

            TODO
        """
        pass
softdev_commit_mapping()

class software_dev_commit(osv.osv):
    _inherit = "software_dev.commit"

    _columns = {
        'commitmap_id': fields.many2one('software_dev.mirrors.commitmap',
                string="Mark",
                help="When this commit is exported/imported from other repos, link "
                    "to the other commits"),
        }

software_dev_commit()

#eof