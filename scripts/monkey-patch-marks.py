#!/usr/bin/python
# -*- encoding: utf-8 -*-
#
# Copyright P. Christeas <xrg@hellug.gr> 2010-2012
# Based on the git-bzr-verifymarks.py script of 'rebzr' era.
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsibility of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
###############################################################################
#


# import datetime
import logging
import optparse

from openerp_libclient import rpc
from openerp_libclient.extra import options

def custom_options(parser):
    assert isinstance(parser, optparse.OptionParser)

    pgroup = optparse.OptionGroup(parser, "Other options")
    pgroup.add_option('--limit', type=int,
                    help="Only attempt so many marks")
    pgroup.add_option('--active', dest="do_write",
                    action="store_true", default=False,
                    help="write back to the database"),
    pgroup.add_option('--repo-id', dest="repo_ids",
                    action="append", default=[],
                    help="Monkey-create fake marks for stray commits at repo ID"),
    parser.add_option_group(pgroup)

options.init(options_prepare=custom_options,
        config='~/.openerp/buildbot.conf',
        config_section=())
        # FIXME: move defaults here

log = logging.getLogger('main')
rpc.openSession(**options.connect_dsn)

if not rpc.login():
    raise Exception("Could not login!")

marks_obj = rpc.RpcProxy('software_dev.mirrors.commitmap')

commit_obj = rpc.RpcProxy('software_dev.commit')
branch_obj = rpc.RpcProxy('software_dev.branch')
repo_obj = rpc.RpcProxy('software_dev.repo')

known_marks = []
known_branches = {}

do_write = options.opts.do_write
repo_ids = map(int, options.opts.repo_ids)

def branch2repo(branch_id):
    if branch_id in known_branches:
        return known_branches[branch_id]
    res = repo_obj.search_read([('branch_ids.id', '=', branch_id)], fields=['fork_of_id'])
    if not res:
        raise ValueError("Cannot locate repo of branch %d" % branch_id)
    elif len(res) > 1:
        raise RuntimeError("Branch in multiple repos ?!?")
    if res[0]['fork_of_id']:
        ret = res[0]['fork_of_id'][0]
    else:
        ret = res[0]['id']
    known_branches[branch_id] = ret
    return ret

avail_marks = {}  # by collection
def get_next_mark(mstart, coll_id):
    """ Determine next available mark for collection.

        @param mstart the mark to start from
        @param coll_id the collection_id
    """
    global avail_marks

    if mstart[0] == ':':
        mstart = mstart[1:]

    istart = int(mstart)

    if not coll_id in avail_marks:
        avail_marks[coll_id] = { 'free': [], 'next': istart + 1 }

    if avail_marks[coll_id]['free']:
        return avail_marks[coll_id]['free'].pop(0)
    else:
        n = max(avail_marks[coll_id]['next'], istart + 1)
        while not avail_marks[coll_id]['free']:
            pros =  [':%d' % (x + n) for x in range(25) ]
            n += 25
            for r in marks_obj.search_read([('mark', 'in', pros)], fields=['mark']):
                pros.remove(r['mark'])
            if not pros:
                continue
            avail_marks[coll_id]['free'] = pros[1:]
            avail_marks[coll_id]['next'] = n
            return pros[0]

    raise RuntimeError("Why here?")

def main_loop(chashes):
    log = logging.getLogger('algo')
    if not chashes:
        raise ValueError("Must have some commit hashes to start with")
    pending_marks = marks_obj.search_read([('commit_ids.hash', 'in', chashes)])
    
    if not pending_marks:
        log.warning("No pending marks! Early exit.")
        return
    
    llimit = options.opts.limit
    lloop = 0
    num_issues = 0

    while pending_marks:
        if lloop >= llimit:
            break
        lloop += 1
        
        if lloop % 1000 == 0:
            log.info("At loop %d, done %d marks", lloop, len(known_marks))
        
        mark = pending_marks.pop(0)
        if mark['id'] in known_marks:
            log.debug("Skipping known mark #%d", mark['id'])
            continue

        log.debug("Processing %s mark #%d %s (%d)...", mark['verified'], mark['id'], mark['mark'], len(mark['commit_ids']))
        commits = commit_obj.read(mark['commit_ids'], ['hash', 'date', 'branch_id', 'ctype', 'parent_id', 'contained_commit_ids'])
        
        next_marks = []
        stray = []
        for com in commits:
            if com['ctype'] == 'incomplete':
                log.warning('Hit incomplete commit %d %s for branch %d %s', 
                        com['id'], com['hash'][:12], com['branch_id'][0], com['branch_id'][1])
                num_issues += 1
            else:
                r = branch2repo(com['branch_id'][0])
                if r not in repo_ids:
                    continue
                
                parents = []
                if com['parent_id']:
                    parents.append(com['parent_id'][0])
                if com['contained_commit_ids']:
                    parents += com['contained_commit_ids']
                for cmt in commit_obj.read(parents, ['hash', 'commitmap_id', 'date']):
                    if cmt['commitmap_id']:
                        next_marks.append(cmt['commitmap_id'][0])
                    else:
                        log.info("Located unmarked commit #%d %s", cmt['id'], cmt['hash'][:12])
                        stray.append((r, cmt['id'], cmt['date'], cmt['hash']))

        if stray and repo_ids:
            for p in stray:
                assert p[0] in repo_ids
                new_mark = get_next_mark(mark['mark'], mark['collection_id'][0])
                log.info("Stray commit #%d will be asigned fake mark %s.", p[1], new_mark)
                if do_write:
                    mid = marks_obj.create({'collection_id': mark['collection_id'][0],
                            'mark': new_mark, 'verified': 'bad-missing',
                            'commit_ids': [(6,0, [p[1],])] })
                    next_marks.append(mid)
                stray.remove(p)


        known_marks.append(mark['id'])

        next_marks = filter(lambda m: m not in known_marks, next_marks)
        pending_marks += marks_obj.read(next_marks)

        if stray:
            log.warning("Stray commits remaining: %r", stray)

        
        # continue loop
    
    log.info("Finished loop after %d calls", lloop)
    if pending_marks:
        log.info("Next stop: mark #%d %s", pending_marks[0]['id'], pending_marks[0]['mark'])
    # end def

if __name__ == "__main__":
    main_loop(options.args)
    log.info('Exiting')
#eof
