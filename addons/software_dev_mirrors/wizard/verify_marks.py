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

from osv import osv, fields
from tools.translate import _

class verify_marks(osv.osv_memory):
    """ Request buildbot to scan incomplete commits
    """

    _name = 'software_dev.mirrors.wizard.verify_marks'
    _description = 'Verify mirrored Marks'

    _columns = {
        'collection_id': fields.many2one('software_dev.mirrors.branch_collection',
                'Branch Collection', required=True),
        'limit': fields.integer('Limit',
                help='If set, only resolve up to that many marks'),
        }


    def verify_marks(self, cr, uid, ids, context=None):
        """ The actual algorithm. Scan all the marks of some collection.
        """
        cmtmap_obj = self.pool.get('software_dev.mirrors.commitmap')
        commit_obj = self.pool.get('software_dev.commit')
        bad_marks = []
        unlink_marks = []
        write_commits = []
        for sbro in self.browse(cr, uid, ids, context=context):
            repos = set([ b.repo_id.id for b in sbro.collection_id.branch_ids])
            remain = sbro.limit or None

            for cmmap in cmtmap_obj.browse(cr, uid, [('collection_id', '=', sbro.collection_id.id)], context=context):
                cdict = None
                if remain is not None and remain <= 0:
                    break

                if len(cmmap.commit_ids) == 0:
                    unlink_marks.append(cmmap.id)
                    continue
                if len(cmmap.commit_ids) == 1 and len(repos) > 1:
                    if not cmmap.mark.startswith(':'):
                        # a special fix case: if the mark is not prepended by colon
                        # and we can find the one prepended, update the commit
                        new_cmmaps = cmtmap_obj.search(cr, uid, \
                                [('collection_id', '=', sbro.collection_id.id),
                                ('mark', '=', ':' + cmmap.mark)], context=context)
                        if new_cmmaps:
                            write_commits.append( (cmmap.commit_ids[0].id, {'commitmap_id': new_cmmaps[0]}))
                            unlink_marks.append(cmmap.id)
                            continue

                if len(cmmap.commit_ids) < len(repos):
                    # this commit doesn't exist in all repos
                    # Try to locate the missing commits
                    if len(cmmap.commit_ids) >= 1:
                        srepos = repos.copy()
                        for cmt in cmmap.commit_ids:
                            srepos.remove(cmt.branch_id.repo_id.id)
                        commit0 = cmmap.commit_ids[0]
                        new_commits = commit_obj.search(cr, uid,\
                                    [('date','=', commit0.date), ('subject', '=', commit0.subject),
                                    ('comitter_id', 'in', [('userid', '=', commit0.comitter_id.userid)]),
                                    ('branch_id', 'in', [('repo_id', 'in', list(srepos))]),
                                    ('commitmap_id','=', False)],
                                    context=context)
                        del commit0
                        if new_commits:
                            for n in new_commits:
                                write_commits.append((n, {'commitmap_id': cmmap.id}))
                    bad_marks.append(cmmap.id)
                    continue

                repos_done = []
                for cmt in cmmap.commit_ids:
                    if remain is not None:
                        if remain <= 0:
                            break
                        remain -= 1
                    if cmt.ctype == 'incomplete':
                        continue
                    cmt_repo = cmt.branch_id.repo_id.id
                    if cmt_repo not in repos:
                        bad_marks.append(cmmap.id)
                        break
                    elif cmt_repo in repos_done:
                        bad_marks.append(cmmap.id)
                        break
                    repos_done.append(cmt_repo)
                    del cmt_repo

                    if not cdict:
                        # the first of the commits
                        cdict = dict(date=cmt.date, subject=cmt.subject)
                        continue

                    if cmt.date != cdict['date']:
                        bad_marks.append(cmmap.id)
                        break
                    elif cmt.subject.strip() != cdict['subject'].strip():
                        bad_marks.append(cmmap.id)
                        break

                    # TODO: compare authors, parent commits

                    #end for
                # end for

        if write_commits:
            for cid, vals in write_commits:
                commit_obj.write(cr, uid, [cid], vals, context=context)
        if unlink_marks:
            cmtmap_obj.unlink(cr, uid, unlink_marks, context=context)
        if bad_marks:
            #mod_obj = self.pool.get('ir.model.data')
            if context is None:
                context = {}
            #imd_views = mod_obj.search_read(cr, uid, [('model','=','ir.ui.view'),
            #        ('module','=', 'software_dev'),
            #        ('name','=','')], context=context)
            #resource_id = mod_obj.read(cr, uid, model_data_ids, fields=['res_id'], context=context)[0]['res_id']
            return {
                'name': _('Bad Marks'),
                'context': context,
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': 'software_dev.mirrors.commitmap',
                #'views': [(resource_id,'form')],
                'domain': [('id', 'in', bad_marks)],
                'type': 'ir.actions.act_window',
                #'target': 'new',
            }
        else:
            return {'warning':  { 'title': _("Verification passed"),
                                'message': _('No bad marks found!') },
                    'type': 'ir.actions.act_window_close'}
verify_marks()

#eof
