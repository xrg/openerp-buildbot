# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>). All Rights Reserved
#    $Id$
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

'''
  A bzr plugin that generate a list of fixed bugs and improvements
    
'''

import bzrlib.log
import string

class unique_list(list):
    def append(self, o):
        if o and o not in self:
            super(unique_list, self).append(o)
            
    def insert(self, p, o):
        if o and o not in self:
            super(unique_list, self).insert(p, o)
        
class OOLogFormatter(bzrlib.log.LogFormatter):
    supports_merge_revisions = True
    preferred_levels = 0
    supports_delta = True
    supports_tags = True
    supports_diff = True

    def __init__(self, *args, **kwargs):
        super(OOLogFormatter, self).__init__(*args, **kwargs)
        self._bugs = {}
        self._fixes = unique_list()
        self._imps = unique_list()
        self._tags = {}
        self._bugs1 = {}
        self._fixes1 = unique_list()
        self._imps1 = unique_list()
    
    def log_revision(self, revision):
        rev = revision.rev
        
        def push_message(msg, prefixs, storage):
            if msg:
                for line in msg.splitlines():
                    l = line.strip()
                    if not prefixs:
                        storage.append(l)
                    else:
                        for prefix in prefixs:
                            if l.upper().startswith(prefix.upper()):
                                l = l[len(prefix):].lstrip(string.whitespace + ':')
                                storage.append(l)

        
        has_bugs = False
        if revision.tags:
            self._tags[revision.tags[0]]=[self._bugs, self._fixes, self._imps]
            self._bugs = {}
            self._fixes = unique_list()
            self._imps = unique_list()
                
        for bug in rev.properties.get('bugs', '').split('\n'):
            if bug:
                has_bugs = True
                url, status = bug.split(' ')
                push_message(rev.message, ['[FIX]'], self._bugs.setdefault(url, unique_list()))
                push_message(rev.message, ['[FIX]'], self._bugs1.setdefault(url, unique_list()))
        
        if not has_bugs:
            push_message(rev.message, ['[FIX]'], self._fixes)
            push_message(rev.message, ['[FIX]'], self._fixes1)

        push_message(rev.message, ['[IMP]', '[ADD]'], self._imps)
        push_message(rev.message, ['[IMP]', '[ADD]'], self._imps1)
    
    def show_advice(self):
        if self._tags:
            for tag, values in self._tags.iteritems():
                    self.to_file.write("============================ Tag %s ============================\n\n"%(tag))
                    if values[0] or values[1]:
                        self.to_file.write('Bugfixes\n')
                        self.to_file.write('--------\n')
                        if values[1]:
                            self.to_file.write(' * Not linked to a bug report:\n')
                            for fix in values[1]:
                                self.to_file.write('   * %s\n' % fix)

                        for bug in values[0]:
                            self.to_file.write(' * %s\n' % bug)
                            for msg in values[0][bug]:
                                self.to_file.write('   * %s\n' % msg)
                        self.to_file.write('\n\n')
            
                    if values[2]:
                        self.to_file.write('Improvements\n')
                        self.to_file.write('------------\n')
                        for imp in values[2]:
                            self.to_file.write(' * %s\n' % imp)
                        self.to_file.write('\n\n')
        
                

if __name__ == '__main__':
    import optparse
    parser = optparse.OptionParser(version='0.1')
    parser.add_option('-i', '--install', dest='install', default=False, action="store_true", help="install the plugin")
    parser.add_option('-f', '--force', dest='force', default=False, action="store_true", help="force installation")
    parser.add_option('-u', '--uninstall', dest='uninstall', default=False, action="store_true", help="uninstall the plugin")
    opt, args = parser.parse_args()
    if opt.force and not opt.install:
        parser.exit(1, 'option -f can only be used with -i option\n')
    
    if not (opt.install ^ opt.uninstall):
        parser.error('please use option -i or -u')

    import os, sys
    dest_dir = os.path.expanduser('~/.bazaar/plugins')
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
    
    dest = os.path.join(dest_dir, os.path.basename(__file__))
    
    if opt.uninstall or opt.force:
        if os.path.exists(dest):
            os.remove(dest)
    
    if opt.install:
        if os.path.exists(dest):
            parser.exit(1, 'Plugin already installed\n')
        os.symlink(os.path.realpath(__file__), dest)

else:
    bzrlib.log.log_formatter_registry.register('openobject', OOLogFormatter, 
                                           'For generate OpenObject Changelog')

