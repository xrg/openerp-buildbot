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

def _to_unicode(s):
    try:
        return s.decode('utf-8')
    except UnicodeError:
        try:
            return s.decode('latin')
        except UnicodeError:
            try:
                return s.encode('ascii')
            except UnicodeError:
                return s

def _to_decode(s):
    try:
        return s.encode('utf-8')
    except UnicodeError:
        try:
            return s.encode('latin')
        except UnicodeError:
            try:
                return s.decode('ascii')
            except UnicodeError:
                return s

ustr = _to_unicode

from threading import Condition

class Pool(object):
    """ A pool of resources, which can be requested one at-a-time
    """
    
    def __init__(self, iter_constr, check_fn=None):
        """ Init the pool
            @param iter_constr is an iterable, that can construct a new
                resource in the pool. It will be called lazily, when more
                resources are needed
            @param check_fn  A callable to use before borrow or after free,
                which will let discard "bad" resources. If check_fn(res)
                returns False, res will be removed from our lists.
        """
        self.__free_ones = []
        self.__used_ones = []
        self.__lock = Condition()
        self.__iterc = iter_constr
        assert self.__iterc
        self.__check_fn = check_fn
        
    def borrow(self, blocking=False):
        """Return the next free member of the pool
        """
        self.__lock.acquire()
        while(True):
            ret = None
            if len(self.__free_ones):
                ret = self.__free_ones.pop()
                if self.__check_fn is not None:
                    self.__lock.release()
                    if not self.__check_fn(ret):
                        ret = None
                    # An exception will also propagate from here,
                    # with the lock released
                    self.__lock.acquire()
                if ret is None:
                    continue # the while loop. Ret is at no list any more
                self.__used_ones.append(ret)
                self.__lock.release()
                return ret
            
            # no free one, try to construct a new one
            try:
                self.__lock.release()
                ret = self.__iterc.next()
                # the iterator may temporarily return None, which
                # means we should wait and retry the operation.
                self.__lock.acquire()
                if ret is not None:
                    self.__used_ones.append(ret)
                    self.__lock.release()
                    return ret
            except StopIteration:
                if not blocking:
                    raise ValueError("No free resource")
                # else pass

            if isinstance(blocking, (int, float)):
                twait = blocking
            else:
                twait = None
            if (not twait) and not len(self.__free_ones):
                twait = 10.0 # must continue cycle at some point!
            self.__lock.wait(twait) # As condition
            if not len(self.__free_ones):
                raise ValueError("Timed out waiting for a free resource")
            continue

        raise RuntimeError("Should never reach here")
        
    def free(self, res):
        self.__lock.acquire()
        try:
            self.__used_ones.remove(res)
        except ValueError:
            self.__lock.release()
            raise RuntimeError("Strange, freed pool item that was not in the list")
        if self.__check_fn is not None:
            self.__lock.release()
            if not self.__check_fn(res):
                res = None
                # not append to free ones, but issue notification
            # An exception will also propagate from here,
            # with the lock released
            self.__lock.acquire()
        if res is not None:
            self.__free_ones.append(res)
        self.__lock.notify_all()
        self.__lock.release()
        
    def __len__(self):
        return len(self.__free_ones) + len(self.__used_ones)

    def __nonzero__(self):
        return True

    def count_free(self):
        return len(self.__free_ones)

    def clear(self):
        """ Forgets about all resources.
        Warning: if you ever use this function, you must make sure that
        the iterable will catch up and restart iteration with more resources
        """
        self.__lock.acquire()
        self.__free_ones = []
        self.__used_ones = []
        self.__lock.notify_all() # Let them retry
        self.__lock.release()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
