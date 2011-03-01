Staging and merging
====================

We want a special, cross-builder, procedure to facilitate the merging of the
'green' branches into a "staging" one. Hopefully, this will be flexible to
setup, easy to work and well-tracked using the db..

Basic design:
-------------

At each branch to be staged, have an extra step at the end, the "ProposeMerge",
which will also reference an ID of the target branch (branch URL, better). 
There are 2 possible ways to convey the merge "proposal":
  1. through LP. Slow and will require authentication to LPlib.
  2. through the OpenERP db. Fast, better tracked, but requires an extra
     table and perhaps change of some semantics

There will be the "staging" branch, with several custom buildsteps:
  * Pull from LP branch: just in case it has changes there
  * Consider merge "proposals", merge them
  * Build
  * Finish commit
  * push to LP
  - or mark-bad revert

A special "changesource" must be configured so that merge proposals can trigger
"staging" builds.
