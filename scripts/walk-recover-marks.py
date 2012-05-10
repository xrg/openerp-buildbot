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
    pgroup.add_option('--limit', type=int, default=1000, 
                    help="Only attempt so many marks")
    pgroup.add_option('--limit-issues', type=int, default=None, 
                    help="Stop at that many issues")
    pgroup.add_option('--active', dest="do_write",
                    action="store_true", default=False,
                    help="write back to the database"),
    parser.add_option_group(pgroup)

options.init(options_prepare=custom_options,
        config='~/.openerp/buildbot.conf', have_args=True,
        config_section=())

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
    max_known_repos = 2
    num_issues = 0

    while pending_marks:
        if lloop >= llimit:
            break
        lloop += 1
        
        mark = pending_marks.pop(0)
        log.debug("Processing %s mark #%d %s (%d)...", mark['verified'], mark['id'], mark['mark'], len(mark['commit_ids']))
        if len(mark['commit_ids']) < max_known_repos:
            log.info("Mark #%d %s is missing commits!",  mark['id'], mark['mark'])

        commits = commit_obj.read(mark['commit_ids'], ['hash', 'date', 'branch_id', 'ctype', 'parent_id', 'contained_commit_ids'])
        mark2repos = {}
        stray = []
        got_repos = set()
        
        for com in commits:
            if com['ctype'] == 'incomplete':
                log.warning('Hit incomplete commit %d %s for branch %d %s', 
                        com['id'], com['hash'][:12], com['branch_id'][0], com['branch_id'][1])
                num_issues += 1
            else:
                r = branch2repo(com['branch_id'][0])
                if r in got_repos:
                    log.error('Mark #%d %s has multiple commits for repo %d', mark['id'], mark['mark'], r)
                    # TODO something
                    num_issues += 1
                got_repos.add(r)
                parents = []
                if com['parent_id']:
                    parents.append(com['parent_id'][0])
                if com['contained_commit_ids']:
                    parents += com['contained_commit_ids']
                for cmt in commit_obj.read(parents, ['hash', 'commitmap_id', 'date']):
                    if not cmt['commitmap_id']:
                        log.info("Located unmarked commit #%d %s", cmt['id'], cmt['hash'][:12])
                        stray.append((r, cmt['id'], cmt['date'], cmt['hash']))
                    else:
                        mark2repos.setdefault(cmt['commitmap_id'][0],[]).append((r, cmt['id'], cmt['date'], cmt['hash']))
        
        # try to cross check all commits by repo
        
        ms = []
        # read them now, then decide about excess commits
        for rmark in marks_obj.read(mark2repos.keys()):
            m = rmark['id']
            mrs = mark2repos[m]
            to_add = []
            write_vals = {}
            if len(mrs) != max_known_repos:
                log.info("Mark #%d has missing commits", m)
                num_issues += 1
                write_vals['verified'] = 'bad-missing'
                for rs in mrs:
                    for r, cmtid, cmtdate, cmthash in stray:
                        if r == rs[0]:
                            continue
                        if cmtdate != rs[2]:
                            continue
                        log.info("Commit #%d (= #%d) may belong to mark #%d. Hash: %s", cmtid, rs[1], m, cmthash)
                        to_add.append((r, cmtid, cmtdate, cmthash))
                        write_vals['verified'] = 'unknown'
            
            new_cmtids = [ r[1] for r in mrs]
            excess_cmtids = [ c for c in rmark['commit_ids'] if c not in new_cmtids]
            if excess_cmtids:
                log.info("Excess commits %r must be removed from mark #%d", excess_cmtids, m)
                rmark['commit_ids'] = new_cmtids
                write_vals.setdefault('commit_ids', []).extend([(3, x) for x in excess_cmtids])
    
            if to_add:
                stray = filter(lambda s: s not in to_add, stray)
                write_vals.setdefault('commit_ids', []).extend([(4, x[1]) for x in to_add])
                rmark['commit_ids'] += [ c[1] for c in to_add]

            if do_write and write_vals:
                write_vals.setdefault('verified', 'unknown')
                marks_obj.write(rmark['id'], write_vals)
            if m not in known_marks:
                ms.append(rmark)
            else:
                # TODO read it, check ...
                pass

        if stray:
            log.warning("Must associate stray commits: %r", stray)
            # FIXME
            num_issues += 1

        if ms:
            # replace with corrected commits
            pending_marks.extend(ms)
        known_marks.append(mark['id'])
        
        if options.opts.limit_issues and num_issues >= options.opts.limit_issues:
            break
        # continue loop
    
    log.info("Finished loop after %d calls", lloop)
    # end def

if __name__ == "__main__":
    main_loop(options.args)
    log.info('Exiting')
#eof
