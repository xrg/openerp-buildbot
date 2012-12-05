#!/usr/bin/python
# -*- encoding: utf-8 -*-
#
# Copyright P. Christeas <xrg@hellug.gr> 2010-2012
# Based on the git-bzr-verifymarks.py script of 'rebzr' era.
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
    pgroup.add_option('--limit', type=int, default=10, 
                    help="Only attempt so many marks")
    #pgroup.add_option('--limit-issues', type=int, default=None, 
                    #help="Stop at that many issues")
    pgroup.add_option('--active', dest="do_write",
                    action="store_true", default=False,
                    help="write back to the database"),
    pgroup.add_option('--limit-up', type=int, default=None, 
                    help="Limit number of commits we go up from the given one")
    pgroup.add_option('--limit-down', type=int, default=None, 
                    help="Limit number of commits we prune down the chain")
    pgroup.add_option('--repo-id', '-R', type=int, default=None, 
                    help="Auto-detect branches on repository ID")
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

do_write = options.opts.do_write

def main_loop(args, opts, context):
    logger = logging.getLogger("algo")
    limit_down = opts.limit_down or 20
    if args:
        head_mark = marks_obj.search_read([('verified', '=', 'bad-missing'),
                ('commit_ids.hash', 'in', args)],
                order='id', fields=['mark', 'commit_ids'], context=context)
    else:
        head_mark = marks_obj.search_read([('verified', '=', 'bad-missing'),
                ('commit_ids.branch_id.repo_id', '=', opts.repo_id)],
                limit=opts.limit, order='id', fields=['mark', 'commit_ids'], context=context)
    known_multimarks = []
    marks_with_children = []
    pruned_marks = []
    pruned_commits = []
    checked = 0
    while head_mark:
        hm = head_mark.pop() # from end, since order is "id asc"
        checked += 1
        if len(hm['commit_ids']) > 1:
            known_multimarks.append(hm['mark'])
            continue
        this_cmt = commit_obj.read(hm['commit_ids'][0], fields=['parent_id', 'hash', 'contained_commit_ids', 'commitmap_id'], context=context)
        children = commit_obj.search_read([('id', 'not in', pruned_commits), '|', ('parent_id', '=', hm['commit_ids'][0]),
                ('contained_commit_ids', '=', hm['commit_ids'][0]),], fields=['commitmap_id', 'hash'], context=context)
        if children:
            logger.info("Commit %s #%d %.20s has children, cannot prune", hm['mark'], hm['commit_ids'][0], this_cmt['hash'])
            marks_with_children.append(hm['id'])
            for c in children:
                logger.debug("    child: #%d %s %s", c['id'], c['commitmap_id'] and c['commitmap_id'][1] or '', c['hash'])
            continue
        logger.info("Commit %s #%d %.20s is clear, can prune", hm['mark'], hm['commit_ids'][0], this_cmt['hash'])
        pruned_marks.append(hm['id'])
        pruned_commits.append(hm['commit_ids'][0])
        parent = False
        if limit_down and (not this_cmt['contained_commit_ids']) and (this_cmt['parent_id']):
            # if we are still away from limit_down, find parent commits to prune
            new_hms = marks_obj.search_read([('verified', '=', 'bad-missing'), 
                    ('commit_ids', '=', this_cmt['parent_id'][0]), ('mark', 'not in', known_multimarks),
                    ('id', 'not in', [h['id'] for h in head_mark])], fields=['mark', 'commit_ids'], context=context)
            if new_hms:
                limit_down -= len(new_hms)
                head_mark.extend(new_hms)
    if opts.do_write:
        if marks_with_children:
            marks_obj.write(marks_with_children, {'verified': 'bad'}, context=context)
        if pruned_marks:
            commit_obj.unlink(pruned_commits, context=context)
            marks_obj.unlink(pruned_marks, context=context)
    logger.info("Finish. Checked: %d , not pruned: %d , pruned %d", checked, 
                len(marks_with_children), len(pruned_marks))

if __name__ == "__main__":
    main_loop(options.args, options.opts, context={})
    log.info('Exiting')
#eof