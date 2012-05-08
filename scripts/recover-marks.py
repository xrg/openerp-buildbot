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


import os
import sys
import re
# import datetime
import logging
import optparse

from openerp_libclient import rpc
from openerp_libclient.extra import options


def custom_options(parser):
    assert isinstance(parser, optparse.OptionParser)

    pgroup = optparse.OptionGroup(parser, "Other options")
    #pgroup.add_option('-t', '--poll-interval', type=int,
    #                help="Polling Interval")
    pgroup.add_option('--collection', '-C', help="Collection id or name")
    pgroup.add_option('--limit', type=int, default=10, 
                    help="Only attempt so many bad marks")
    pgroup.add_option('-n', '--num-loops', type=int, default=1, 
                    help="repeat loop so many times")
    pgroup.add_option('--git-marks', help="Load additional git marks")
    pgroup.add_option('--bzr-marks', help="Load additional bzr marks")
    pgroup.add_option('--active', dest="do_write",
                    action="store_true", default=False,
                    help="write back to the database"),
    parser.add_option_group(pgroup)

options.init(options_prepare=custom_options,
        config='~/.openerp/buildbot.conf', have_args=False,
        config_section=())

log = logging.getLogger('main')
log.info("Init. Connecting...")

rpc.openSession(**options.connect_dsn)


if not rpc.login():
    raise Exception("Could not login!")
log.info("Connected.")

if not options.opts.collection:
    log.error("Must supply the collection to operate on")
    sys.exit(2)

if options.opts.collection.isdigit():
    coll_id = int(options.opts.collection)
else:
    cids = rpc.RpcProxy('software_dev.mirrors.branch_collection').\
            search([('name', '=', options.opts.collection)],)
    if not cids:
        log.error("Cannot locate collection \"%s\"", options.opts.collection)
        sys.exit(2)
    elif len(cids) > 1:
        log.error("Ambiguous collection specification")
        sys.exit(2)
    else:
        coll_id = cids[0]

marks_obj = rpc.RpcProxy('software_dev.mirrors.commitmap')

known_branches = {}
known_repos = {}
commit_obj = rpc.RpcProxy('software_dev.commit')
branch_obj = rpc.RpcProxy('software_dev.branch')
repo_obj = rpc.RpcProxy('software_dev.repo')

def get_commits(ids, fields=None):
    """ read a set of commit ids
        
        @return a dict like {id: ... }
    """
    
    if fields is None:
        fields = ['date', 'description', 'branch_id', 'hash',
                'commitmap_id', 'contained_commit_ids', 'ctype',
                'parent_id', 'subject', 'date']

    log.debug("Fetch commits: %r", ids)
    ret = {}
    fetch_branches = []
    for res in commit_obj.read(ids, fields=fields):
        
        parents = []
        if res.get('parent_id'):
            parents.append(res['parent_id'][0])
        if res.get('contained_commit_ids'):
            parents.extend(res['contained_commit_ids'])
        res['parents'] = parents
        ret[res['id']] = res
    
        if res['branch_id'][0] not in known_branches:
            fetch_branches.append(res['branch_id'][0])
        
    if fetch_branches:
        for fb in branch_obj.read(list(set(fetch_branches)), fields=['name', 'repo_id']):
            if fb['repo_id'][0] not in known_repos:
                known_repos[fb['repo_id'][0]] = repo_obj.read(fb['repo_id'][0], ['name', 'rtype'])
            fb['rtype'] = known_repos[fb['repo_id'][0]]['rtype']
            known_branches[fb['id']] = fb
    
    for cr in ret.values():
        cr['rtype'] = known_branches[cr['branch_id'][0]]['rtype']
    
    return ret

git_marks2 = {}
bzr_marks2 = {}

def git_marks_import(filename):
    """Read the mapping of marks to revision-ids from a file.

    :param filename: the file to read from
    :return: a dictionary with marks as keys and revision-ids
    """
    # Check that the file is readable and in the right format
    try:
        f = file(filename)
    except IOError:
        log.warning("Could not import marks file %s - not importing marks",
            filename)
        return None

    # Read the revision info
    for line in f:
        line = line.rstrip('\n')
        mark, revid = line.split(' ', 1)
        git_marks2.setdefault(revid,[]).append(mark)
    f.close()


def bzr_marks_import(filename):
    """Read the mapping of marks to revision-ids from a file.

    :param filename: the file to read from
    :return: None if an error is encountered or (revision_ids, branch_names)
      where
      * revision_ids is a dictionary with marks as keys and revision-ids
        as values
      * branch_names is a dictionary mapping branch names to some magic #
      
      Copyright (C) 2009 Canonical Ltd (GPL2)
    """
    # Check that the file is readable and in the right format
    try:
        f = file(filename)
    except IOError:
        log.warning("Could not import marks file %s - not importing marks",
            filename)
        return None
    firstline = f.readline()
    match = re.match(r'^format=(\d+)$', firstline)
    if not match:
        log.warning("%r doesn't look like a marks file - not importing marks",
            filename)
        return None
    elif match.group(1) != '1':
        log.warning('format version in marks file %s not supported - not importing'
            'marks', filename)
        return None

    # Read the branch info
    branch_names = {}
    for string in f.readline().rstrip('\n').split('\0'):
        if not string:
            continue
        name, integer = string.rsplit('.', 1)
        branch_names[name] = int(integer)
 
    # Read the revision info
    for line in f:
        line = line.rstrip('\n')
        mark, revid = line.split(' ', 1)
        bzr_marks2.setdefault(revid,[]).append(mark)
    f.close()

def main_loop():
    """ A processing loop, that may clear some marks
    """
  
    do_write = options.opts.do_write
    did_something = False
    skip_marks = []
    for bad_mark in marks_obj.search_read([('collection_id', '=', coll_id), ('verified', 'not in', ('ok', 'unknown', 'bad'))],
                fields=['mark', 'commit_ids', 'verified'],
                order='id', limit=options.opts.limit):
        log.debug("Found a %s mark: %s", bad_mark['verified'], bad_mark['mark'])
    
        if bad_mark['id'] in skip_marks:
            continue

        if bad_mark['verified'] == 'bad-missing':
            commits = get_commits(bad_mark['commit_ids'])
            if not len(commits):
                log.info("Mark %s must be deleted!")
            else:
                handled = False
                for c in commits.values():
                    if c['rtype'] == 'git':
                        alts = git_marks2.get(c['hash'], [])
                        if len(alts) > 1 and bad_mark['mark'] not in alts:
                            log.info("Located alternatives for %s: %r", bad_mark['mark'], alts)
                            handled = True
                        c['alt_marks'] = alts
                    elif c['rtype'] == 'bzr':
                        alts = bzr_marks2.get(c['hash'], [])
                        if len(alts) > 1 and bad_mark['mark'] not in alts:
                            log.info("Located alternatives for %s: %r", bad_mark['mark'], alts)
                            handled = True
                        c['alt_marks'] = alts
                    else:
                        log.warning("No rtype for commit %d !", c['id'])
                
                if not handled:
                    # second check: walk one child down and see if it is a leaf node
                    children = commit_obj.search_read(['|',('parent_id','in', bad_mark['commit_ids']),
                            ('contained_commit_ids', 'in', bad_mark['commit_ids']),
                            ('commitmap_id','!=', False)], 
                            fields=['commitmap_id', 'hash', 'branch_id', 'parent_id', 'contained_commit_ids'])
                    if not children:
                        log.info("Mark %s is a leaf, can be pruned!", bad_mark['mark'])
                        handled = True
                        if do_write:
                            marks_obj.unlink(bad_mark['id'])
                            did_something = True
                    else:
                        # Try to discover the corresponding
                        # go down one child, and then find if that child's parents
                        # point to a different mark..
                        # print "num children:", len(children)
                        replace_case = {}
                        for ch in children:
                            cmt = False
                            # locate which of our commits this does reference
                            if ch['parent_id'] and ch['parent_id'][0] in commits:
                                cmt = commits[ch['parent_id'][0]]
                            else:
                                for par in ch['contained_commit_ids']:
                                    if par in commits:
                                        cmt = commits[par]
                                        break
                            if not cmt:
                                log.warning("Cannot locate parent, strange! %s %r",
                                        ch['parent_id'], ch['contained_commit_ids'])
                                break
                            
                            # now, find the marks of those children, and jump to their
                            # parents back
                            alt_children = commit_obj.search_read([('commitmap_id', '=', ch['commitmap_id'][0]),
                                    ('branch_id', '!=', ch['branch_id'][0])], 
                                    fields=['parent_id', 'contained_commit_ids'])
                            # note: they would be mixed among 2nd, 3rd... repo
                            alt_parents = []
                            for ac in alt_children:
                                log.debug("alt_children: %r", alt_children)
                                if ac['parent_id']:
                                    alt_parents.append(ac['parent_id'][0])
                                if ac['contained_commit_ids']:
                                    alt_parents.extend(ac['contained_commit_ids'])
                            if alt_parents:
                                log.debug("alt parents: %r", alt_parents)
                                alt_commits = commit_obj.search_read([('id', 'in', alt_parents),
                                        ('date', '=', cmt['date']),('subject', '=', cmt['subject'])],
                                        fields=['branch_id', 'commitmap_id', 'hash'])
                                
                                if alt_commits:
                                    log.debug("Located alt commits for mark: %d %s %s", 
                                            bad_mark['id'], bad_mark['mark'], known_branches[cmt['branch_id'][0]]['rtype'])
                                    log.debug("Instead of %d %s: %s %s", cmt['id'], cmt['hash'], 
                                            cmt['commitmap_id'][1], cmt.get('alt_marks','-'))
                                    for atc in alt_commits:
                                        log.debug(" also have %d %s: %s", atc['id'], atc['hash'], atc['commitmap_id'])
                                
                                        if replace_case and ((not atc['commitmap_id']) \
                                                or replace_case['alt_mark'] != atc['commitmap_id'][0]):
                                            replace_case['borked'] = True
                                        elif atc['commitmap_id'] and not replace_case:
                                            replace_case = dict(orig_mark=bad_mark['id'],
                                                    orig_mark_s=bad_mark['mark'],
                                                    alt_mark=atc['commitmap_id'][0],
                                                    alt_mark_s=atc['commitmap_id'][1],
                                                    move_commits=[atc['id'],])
                                        elif replace_case:
                                            replace_case['move_commits'].append(atc['id'])
                
                        if replace_case:
                            if replace_case.get('borked', False):
                                log.warning("Cannot merge %s into %s", replace_case['alt_mark_s'], replace_case['orig_mark_s'])
                            else:
                                log.info("Will merge %s into %s (commits: %s)", 
                                        replace_case['alt_mark_s'], replace_case['orig_mark_s'], replace_case['move_commits'])
                                handled = True
                                skip_marks.append(replace_case['alt_mark'])
                                
                                if do_write:
                                    commit_obj.write(replace_case['move_commits'], {'commitmap_id': replace_case['orig_mark']})
                                    marks_obj.write(replace_case['orig_mark'], {'verified': 'unknown'})
                                    marks_obj.write(replace_case['alt_mark'], {'verified': 'bad'})
                                    did_something = True
                
        elif bad_mark['verified'] == 'bad-parents':
            commits = get_commits(bad_mark['commit_ids'])
            for cmt in commits.values():
                cmt['parent_marks'] = []
                for pv in commit_obj.read(cmt['parents'], fields=['commitmap_id']):
                    cmt['parent_marks'].append(pv['commitmap_id'])
            
                log.debug('Commit %d has parents: %r', cmt['id'], cmt['parent_marks'])
            
            first_commit = commits.pop(commits.keys()[0])
            common_marks = []
            for mark_id in first_commit['parent_marks']:
                for cmt in commits.values():
                    if mark_id not in cmt['parent_marks']:
                        break
                else:
                    common_marks.append(mark_id)
            
            diffs = {}
            for mark_id in first_commit['parent_marks']:
                if not mark_id:
                    diffs.setdefault(first_commit['id'],[]).append(False)
                elif mark_id not in common_marks:
                    diffs.setdefault(first_commit['id'],[]).append(mark_id[1])
            
            for cmt in commits.values():
                for mark_id in cmt['parent_marks']:
                    if not mark_id:
                        diffs.setdefault(cmt['id'],[]).append(False)
                    elif mark_id not in common_marks:
                        diffs.setdefault(cmt['id'],[]).append(mark_id[1])
            log.info("Mismatch of parents for %s : %r", bad_mark['mark'], diffs)
        
        elif bad_mark['verified'] == 'bad':
            pass
        else:
            log.warning("Cannot handle %s mark: %s!", bad_mark['verified'], bad_mark['mark'])

    return did_something

if __name__ == "__main__":
    if options.opts.git_marks:
        git_marks_import(options.opts.git_marks)
        log.info("loaded %d git marks", len(git_marks2))
    if options.opts.bzr_marks:
        bzr_marks_import(options.opts.bzr_marks)
        log.info("loaded %d bzr marks", len(bzr_marks2))

    npass = 0
    while npass < options.opts.num_loops:
        npass += 1
        log.info("Recover loop %d", npass)
        if not main_loop():
            break
        

    log.info('Exiting after %d loops', npass)
#eof
