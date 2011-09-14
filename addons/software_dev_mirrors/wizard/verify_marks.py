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
import re

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
        repo_obj = self.pool.get('software_dev.repo')
        good_marks = []
        bad_marks = {}
        unlink_marks = []
        write_commits = []
        wspace_re = re.compile('\s+')
        def id_of(abro):
            if abro:
                return abro.id
            else:
                return False
        
        def root_repo_of(branch_bro):
            """ Returns the id of the topmost repo of branch
            
                Considers fork repositories.
            """
            r = branch_bro.repo_id
            if r.fork_of_id:
                return r.fork_of_id.id
            else:
                return r.id

        _logger = osv.orm._logger
        def debug(msg, *args):
            if not self._debug:
                return
            _logger.debug('verify_marks: '+msg, *args)

        for sbro in self.browse(cr, uid, ids, context=context):
            all_repos = repo_obj.get_all_forks(cr, uid, 
                    osv.orm.browse_record_list([ b.repo_id 
                                for b in sbro.collection_id.branch_ids], context=context),
                            context=context)
            repos = set([a[0] for a in all_repos.values()])
            remain = sbro.limit or None

            for cmmap in cmtmap_obj.browse(cr, uid, [('verified','=', 'unknown'),
                        ('collection_id', '=', sbro.collection_id.id)],
                    context=context):
                cdict = None
                if remain is not None and remain <= 0:
                    break

                if len(cmmap.commit_ids) == 0:
                    unlink_marks.append(cmmap.id)
                    debug("Unlink empty %d", cmmap.id)
                    remain -= 1
                    continue
                if len(cmmap.commit_ids) == 1 and len(repos) > 1:
                    if not cmmap.mark.startswith(':'):
                        remain -= 1
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
                            srepos.remove(root_repo_of(cmt.branch_id))
                        commit0 = cmmap.commit_ids[0]
                        other_repos = []
                        for sr in srepos:
                            if sr in srepos:
                                continue
                            other_repos += all_repos[sr]
                        new_commits = commit_obj.search(cr, uid,\
                                    [('date','=', commit0.date), ('subject', '=', commit0.subject),
                                    ('comitter_id', 'in', [('userid', '=', commit0.comitter_id.userid)]),
                                    ('branch_id', 'in', [('repo_id', 'in', other_repos)]),
                                    ('commitmap_id','=', False)],
                                    context=context)
                        del commit0
                        if new_commits:
                            for n in new_commits:
                                write_commits.append((n, {'commitmap_id': cmmap.id}))
                    bad_marks.setdefault('bad-missing',[]).append(cmmap.id)
                    debug("Mark #%d %s has too few commits", cmmap.id, cmmap.mark)
                    remain -= 1
                    continue

                repos_done = []
                for cmt in cmmap.commit_ids:
                    if remain is not None:
                        if remain <= 0:
                            break
                        remain -= 1
                    if cmt.ctype == 'incomplete':
                        continue
                    cmt_repo = root_repo_of(cmt.branch_id)
                    if cmt_repo not in repos:
                        bad_marks.setdefault('bad',[]).append(cmmap.id)
                        break
                    elif cmt_repo in repos_done:
                        bad_marks.setdefault('bad',[]).append(cmmap.id)
                        break
                    repos_done.append(cmt_repo)
                    del cmt_repo

                    if not cdict:
                        # the first of the commits
                        cdict = dict(date=cmt.date, subject=cmt.subject, 
                            description=cmt.description, parents=[],
                            comitter=(cmt.comitter_id.userid, 
                                    id_of(cmt.comitter_id.employee_id),
                                    id_of(cmt.comitter_id.partner_address_id)) )
                        if cmt.parent_id:
                            cdict['parents'].append(id_of(cmt.parent_id.commitmap_id))
                        for par in cmt.contained_commit_ids:
                            cdict['parents'].append(id_of(par.commitmap_id))
                        cdict['parents'].sort()
                        continue

                    if cmt.date != cdict['date']:
                        bad_marks.setdefault('bad-date',[]).append(cmmap.id)
                        debug("Mark #%d %s dates differ", cmmap.id, cmmap.mark)
                        break
                    elif cmt.subject.strip() != cdict['subject'].strip():
                        sub1 = cmt.subject.strip() + ' '+ cmt.description.strip()
                        sub2 = cdict['subject'].strip() + ' ' + cdict['description'].strip()
                        sub1 = wspace_re.sub(' ', sub1)
                        sub2 = wspace_re.sub(' ', sub2)
                        # Bzr has a bad habit of allowing ugly subjects. Try harder
                        # to match those against email-normalized Git ones
                        if sub1[:64] != sub2[:64]:
                            bad_marks.setdefault('bad-sub',[]).append(cmmap.id)
                            debug('Mark #%d %s subjects differ "%s" != "%s" ', 
                                    cmmap.id, cmmap.mark, sub1[:64], sub2[:64])
                            break
                    
                    if (cmt.comitter_id.userid != cdict['comitter'][0]) and \
                            (id_of(cmt.comitter_id.employee_id) != cdict['comitter'][1]) and \
                            (id_of(cmt.comitter_id.partner_address_id) != cdict['comitter'][2]):
                        bad_marks.setdefault('bad-author',[]).append(cmmap.id)
                        debug("Mark #%d %s authors differ", cmmap.id, cmmap.mark)
                        break
                    
                    parents = []
                    if cmt.parent_id:
                        parents.append(id_of(cmt.parent_id.commitmap_id))
                        for par in cmt.contained_commit_ids:
                            parents.append(id_of(par.commitmap_id))
                        parents.sort()
                    if parents != cdict['parents']:
                        bad_marks.setdefault('bad-parents',[]).append(cmmap.id)
                        debug("Mark #%d %s parents differ %r != %r", 
                                cmmap.id, cmmap.mark, parents, cdict['parents'])
                        break

                    #end for
                good_marks.append(cmmap.id)
                # end for

        _logger.debug('verify_marks: processed: %d good, %d bad', len(good_marks),
                    sum([len(bm) for bm in bad_marks.values()]))
        if write_commits:
            for cid, vals in write_commits:
                commit_obj.write(cr, uid, [cid], vals, context=context)
        if unlink_marks:
            cmtmap_obj.unlink(cr, uid, unlink_marks, context=context)
        if good_marks:
            cmtmap_obj.write(cr, uid, good_marks,{'verified': 'ok'}, context=context)
        if bad_marks:
            all_bad_marks = []
            for reason, cids in bad_marks.items():
                cmtmap_obj.write(cr, uid, cids,{'verified': reason}, context=context)
                all_bad_marks += cids
            if context is None:
                context = {}

            return {
                'name': _('Bad Marks'),
                'context': context,
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': 'software_dev.mirrors.commitmap',
                #'views': [(resource_id,'form')],
                'domain': [('id', 'in', all_bad_marks)],
                'type': 'ir.actions.act_window',
                #'target': 'new',
            }
        else:
            return {'warning':  { 'title': _("Verification passed"),
                                'message': _('No bad marks found!') },
                    'type': 'ir.actions.act_window_close'}
verify_marks()

#eof
