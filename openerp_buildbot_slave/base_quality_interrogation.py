#!/usr/bin/python
# -*- coding: utf-8 -*-
##############################################################################
#    
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>).
#    Copyright (C) 2010-2011 OpenERP SA. (http://www.openerp.com)
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

import xmlrpclib
from ConfigParser import SafeConfigParser, NoSectionError
import optparse
import sys
import logging
import logging.handlers
import threading
import os
from fnmatch import fnmatch
import signal
import time
import glob
import base64
# import socket
import subprocess
import select
import string
import random
import re
import zipfile

try:
    import json
    __hush_pyflakes = [json,]
except ImportError:
    json = None

try:
    from cStringIO import StringIO
    __hush_pyflakes = [StringIO,]
except ImportError:
    from StringIO import StringIO

# will be imported later:
client_session = None
client_kwargs = {}

def to_decode(s):
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

def pretty_repr(val):
    if json is not None:
        res = json.dumps(val, skipkeys=True, ensure_ascii=True, indent=4)
    elif isinstance(val, (list, tuple)):
        res = ''
        for v in val:
            res += '    %r,\n' % v
        res =  '  [ ' + res[4:] +'  ]'
    elif isinstance(val, dict):
        res = ''
        for k, v in val.items():
            res += '    %r: %r,\n' %(k, v)
        res = '  { ' + res[4:] +  '  }'
    else:
        res = repr(val)
    return res

class ClientException(Exception):
    """Define our own exception, to avoid traceback
    """
    pass

class ServerException(Exception):
    pass

class __RpcException(Exception):
    # Placeholder class, to use instead of openerp_libclient's
    pass

# we don't care if they point to the same class
RpcException = __RpcException
RpcServerException = __RpcException

# --- cut here
import logging
# import types

def xmlescape(sstr):
    return sstr.replace('<','&lt;').replace('>','&gt;').replace('&','&amp;')

class XMLStreamHandler(logging.FileHandler):
    """ An xml-like logging handler, writting stream into a file.
    
    Note that we don't use any xml dom class here, because we want
    our output to be immediately streamed into a file. Upon any 
    crash of the script, the partial xml will be useful.
    """
    def __init__(self, filename, encoding='UTF-8'):
        logging.FileHandler.__init__(self, filename, mode='w', 
                encoding=encoding, delay=False)
        # now, open the file and write xml prolog
        self.formatter = XMLFormatter()
        self.stream.write('<?xml version="1.0", encoding="%s" ?>\n<log>' % encoding)
        
    def close(self):
        # write xml epilogue
        self.stream.write('</log>\n')
        logging.FileHandler.close(self)

    # Note: we need not re-implement emit, because a special formatter
    # will be used

class XMLFormatter(logging.Formatter):
    """ A special formatter that will output all fields in an xml-like
    struct """
    
    def format(self, record):
        """ Put everything in xml format """
        
        s = '<rec name="%s" level="%s" time="%s" >' % \
            (record.name, record.levelno, record.created)

        if False and (record.filename or record.module or record.lineno):
            s += '<code filename="%s" module="%s" line="%s" />' % \
                    (record.filename, record.module, record.lineno)


        if record.exc_info and not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)

        if record.exc_text:
            s+= '<exception>%s</exception>' % xmlescape(record.exc_text)

        s+= xmlescape(record.getMessage())
        s+= '</rec>'

        return s.decode('utf-8')

# --- cut here

class MachineFormatter(logging.Formatter):
    """ Machine-parseable log output, in plain text stream.
    
    In order to have parsers analyze the output of the logs, have
    the following format:
        logger[|level]> msg...
        + msg after newline
        :@ First exception line
        :+ second exception line ...
    
    It should be simple and well defined for the other side.
    """
    
    def format(self, record):
        """ Format to stream """
        
        levelstr = ''
        if record.levelno != logging.INFO:
            levelstr = '|%d' % record.levelno

        try:
            msgtxt = record.getMessage().replace('\n','\n+ ')
        except TypeError:
            print "Message:", record.msg
            msgtxt = record.msg

        s = "%s%s> %s" % ( record.name, levelstr, msgtxt)

        if record.exc_info and not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)

        if record.exc_text:
            s+= '\n:@ %s' % record.exc_text.replace('\n','\n:+ ')

        # return s.decode('utf-8')
        return s

logging.DEBUG_RPC = logging.DEBUG - 2
logging.addLevelName(logging.DEBUG_RPC, 'DEBUG_RPC')
logging.DEBUG_SQL = logging.DEBUG_RPC - 2
logging.addLevelName(logging.DEBUG_SQL, 'DEBUG_SQL')

logging.TEST = logging.INFO - 5
logging.addLevelName(logging.TEST, 'TEST')

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, _NOTHING, DEFAULT = range(10)
#The background is set with 40 plus the number of the color, and the foreground with 30
#These are the sequences need to get colored ouput
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[%dm"
BOLD_COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"
COLOR_PATTERN = "%s%s%%s%s" % (COLOR_SEQ, COLOR_SEQ, RESET_SEQ)
BOLD_COLOR_PATTERN = "%s%s%%s%s" % (BOLD_COLOR_SEQ, BOLD_COLOR_SEQ, RESET_SEQ)

COLOR_MAPPING = {
    'stdout.DEBUG_SQL': (WHITE, MAGENTA, True),
    'stdout.DEBUG_RPC': (BLUE, WHITE, True),
    'stdout.DEBUG': (BLUE, DEFAULT, True),
    'stdout.INFO': (GREEN, DEFAULT, True),
    'stdout.TEST': (WHITE, BLUE, True),
    'stdout.WARNING': (YELLOW, DEFAULT, True),
    'stdout.ERROR': (RED, DEFAULT, True),
    'stdout.CRITICAL': (WHITE, RED, True),
    'server.stderr': (BLUE, _NOTHING, False),
    'bqi': (DEFAULT, WHITE, False),
    'bqi.blame': (RED, DEFAULT, True),
    'bqi.DEBUG': (CYAN, _NOTHING, False),
    'bqi.WARNING': (YELLOW, WHITE, False),
    'bqi.ERROR': (RED, WHITE, False),
    'bqi.client': (DEFAULT, WHITE, False),
    'bqi.client.ERROR': (RED, WHITE, False),
    'bqi.client.DEBUG': (CYAN, _NOTHING, False),
    'bqi.cli.ERROR': (RED, WHITE, True),
    'bqi.state': (BLACK,WHITE, False),
    'srv.thread': (DEFAULT, WHITE, False),
    'srv.thread.WARNING': (YELLOW, _NOTHING, False),
    'srv.thread.DEBUG': (CYAN, _NOTHING, False),
    'RPC.Transport': (DEFAULT, WHITE, False),
    'RPC.Transport.WARNING': (YELLOW, _NOTHING, False),
    'RPC.Transport.DEBUG': (CYAN, _NOTHING, False),
    'RPC.Connection': (DEFAULT, WHITE, False),
    'RPC.Connection.ERROR': (RED, DEFAULT, False),
    'RPC.Connection.WARNING': (YELLOW, _NOTHING, False),
    'RPC.Connection.DEBUG': (CYAN, _NOTHING, False),
    'RPC.Session': (DEFAULT, WHITE, False),
    'RPC.Session.WARNING': (YELLOW, _NOTHING, False),
    'RPC.Session.DEBUG': (CYAN, _NOTHING, False),
    'RPC.WARNING': (YELLOW, DEFAULT, True),
    'RPC.ERROR': (RED, DEFAULT, True),
    'RPC.CRITICAL': (WHITE, RED, True),
}

class ColoredFormatter(logging.Formatter):
    linere = re.compile(r'\[(.*)\] ([A-Z_]+):([\w\.-]+):(.*)$', re.DOTALL)
    def format(self, record):
        res = logging.Formatter.format(self, record)
        if record.name == 'server.stdout':
            # parse and format only the level name, just like the server itself
            m = self.linere.match(res)
            if m:
                ln = COLOR_MAPPING.get('stdout.' + m.group(2), False)
                
                if ln:
                    fg_color, bg_color, bold = ln
                    if bold:
                        lname = BOLD_COLOR_PATTERN % (30 + fg_color, 40 + bg_color, m.group(2))
                    else:
                        lname = COLOR_PATTERN % (30 + fg_color, 40 + bg_color, m.group(2))
                    res = "[%s] %s:%s:%s" % (m.group(1), lname, m.group(3), m.group(4))
        else:
            # By default, format the whole line per logger's name
            rn = record.name
            if record.levelno != logging.INFO:
                rn += '.' + record.levelname
            if rn in COLOR_MAPPING:
                fg_color, bg_color, bold = COLOR_MAPPING[rn]
                if bold:
                    res = BOLD_COLOR_PATTERN % (30 + fg_color, 40 + bg_color, res)
                else:
                    res = COLOR_PATTERN % (30 + fg_color, 40 + bg_color, res)
            else:
                # print "Oops, you missed color for %s" % rn
                pass
        return res

def print_sql_stats(stats):
    """ Print the result of get_sql_stats
    """
    
    columns = []
    col_vals = {}
    all_sum = 0
    for lkey, line in stats.items():
        for col in line:
            if col not in columns:
                col_vals[col] = 0
                columns.append(col[:8])
    print " " * 26,
    for col in columns:
        print "%8s" % col[:8],
    print " Total"
    for lkey, line in stats.items():
        print "%24s :" % lkey[:24],
        line_sum = 0
        for col in columns:
            cval = line.get(col,[False,])[0]
            if cval is not False:
                line_sum += cval
                print " %6s " % cval ,
                col_vals[col] += cval
            else:
                print "      - ",
        print " %d" % line_sum
    
    print "                   Total :",
    all_sum = 0 
    for col in columns:
        print " %6d " % col_vals[col],
        all_sum +=  col_vals[col]
    print " %d" % all_sum

def splitval(val, cw, do_pad=True):
    """ Split some column data at cw, respecting whitespace or newline

        @return val, remain  the two strings
    """
    if do_pad and len(val) < cw:
        pad = ' ' *(cw - len(val))
        return val.replace('\n', ' ') + pad, None
    elif len(val) <= cw:
        return val.replace('\n', ' '), None

    s = 0
    for splt in ('\n', ' ', ':', '.', ','):
        s = val.rfind(splt, 3, cw-1)
        if s > 3:
            s += 1
            break
    if s <= 0:
        s = cw
    pad = ''
    if do_pad and s < cw:
        pad = ' ' * (cw - s)
    return val[:s].replace('\n',' ') + pad, val[s:]

def print_table(res, columns=None, max_width=True, wrap=True):
    """ Print some result table (from orm.read() eg.)

        res must be in the [ { col: val, col2: val2}, {...}, ...] format

        @param max_width Maximum width of any column, or True for 30, auto-formatting
                of last column
        @param wrap Do wrap column data if they don't fit their column width
    """
    global opt

    columns_auto = False
    col_width = {}
    auto_width_last = False

    if max_width is True:
        max_width = 30
        auto_width_last = True
        if columns and (len(columns) > opt.console_width / 30):
            max_width = (opt.console_width / len(columns)) -1
    if columns is None:
        columns = []
        columns_auto = True
    else:
        for c in columns:
            col_width[c] = min(len(c), max_width)

    # First pass, compute column widths
    for rec in res:
        for col, val in rec.items():
            if col not in columns:
                if columns_auto:
                    col_width[col] = min( max(len(col), len('%s' % (val,))), max_width)
                    columns.append(col)
            else:
                col_width[col] = max(col_width[col], min(len('%s' % (val,)), max_width))

    if auto_width_last:
        first_width = sum([col_width[col] for col in columns[:-1]]) + len(columns) - 2

        if first_width + 5 < opt.console_width:
            col_width[columns[-1]] = opt.console_width - first_width
        else:
            # Wide format, turn off wrapping.
            wrap = False
        # print "column widths:", first_width ,col_width

    col_strs = {}
    for c in columns:
        col_strs[c] = '%-' + str(col_width[c]) +'s'

    print '|'.join([ c[:max_width].center(col_width[c]) for c in columns])
    print '-' * (sum(col_width.values()) + len(columns) - 1)

    for rec in res:
        lin = []
        nline = {} # wrap values for next line
        for c in columns:
            val = col_strs[c] % (rec.get(c, ''),)
            val, nval = splitval(val, col_width[c])
            if nval:
                nline[c] = nval
            lin.append(val)

        print '|'.join(lin)
        if not wrap:
            continue
        ncount = 0
        while nline:
            lin = []
            ncount += 1
            if ncount > 50:
                break
            for c in columns:
                if c in nline:
                    val, nval = splitval(nline[c], col_width[c]-2)
                    lin.append('+ '+val)
                    if nval:
                        nline[c] = nval
                    else:
                        del nline[c]
                else:
                    # pad with blanks
                    lin.append(col_strs[c] % '')
            print '|'.join(lin)

def print_centered(sstr):
    """Print a string, centered at the middle of the console width
    """
    global opt

    if len(sstr) >= opt.console_width:
        print sstr
    else:
        pad = (opt.console_width - len(sstr)) / 2
        print ' '* pad, sstr

def print_lexicon(kdic, title=None, sort_fn=None, indent=4):
    """ Print a dictionary as a lexicon definition

    That is, in the format:
        key1    Description that
                has several lines
        key2    next description
    ...

    @param title  A heading line to be printed before the lexicon
    @param sort_fn function that sorts the dictionary
    @param indent  how many chars the key will be indented
    """

    if title:
        print title

    if sort_fn is None:
        sort_fn = lambda x: x

    keylen = 6
    for k in kdic:
        l = len('%s' % (k,))
        if  l > keylen and l < 30:
            keylen = l

    for k, v in sort_fn(kdic.items()):
        kstr = '%s' % (k,)
        if not isinstance(v, basestring):
            v = '%s' % (v,)
        if len(kstr)  < keylen:
            kstr += ' ' * (keylen - len(kstr))
        lin = (' ' * indent) + kstr + ' '

        if len(lin) > opt.console_width:
            val, nval = '', v
        else:
            val, nval = splitval(v, opt.console_width - len(lin), do_pad=False)

        print lin + val
        cw = opt.console_width - (indent + keylen +1)
        pad = ' ' * (indent + keylen +1)
        while nval:
            val, nval = splitval(nval, cw, do_pad=False)
            print pad + val

    return None

class server_thread(threading.Thread):
    
    def regparser(self, section, regex, funct, multiline=False):
        """ Register a parser for server's output.
        @param section the name of the logger that we try to match, can be *
        @param regex A regular expression to match, or a plain string
        @param funct A callable to execute on match, or a string to log, or
                    a tuple(bqi-class, log_level, string ) to log.
        @param multiline If true, this output can span multiple lines
        """
        self._parsers.setdefault(section, []).append( (regex, funct, multiline) )

    def regparser_exc(self, etype, erege, funct):
        self._exc_parsers.append( (etype, erege, funct))

    def setRunning(self, section, level, line):
        self.log.info("Server is ready!")
        self.is_ready = True

    def setClearContext(self, section, level, line):
        self.clear_context()

    def setListening(self, section, level, mobj):
        self.log.info("Server listens %s at %s:%s" % mobj.group(1, 2, 3))
        self._lports[mobj.group(1)] = mobj.group(3)

    def clear_context(self):
        if self.state_dict.get('context', False) != False:
            self.log_state.info("clear context")
            self.state_dict['context'] = False
        for key in ('module-phase', 'module', 'module-file', 'severity'):
            self.state_dict[key] = None

    def _set_log_context(self, ctx):
        if ctx != self.state_dict.get('context', False):
            self.log_state.info("set context %s", ctx)
            self.state_dict['context'] = ctx

    def setModuleLoading(self, section, level, mobj):
        self.state_dict['module'] = mobj.group(1)
        self.state_dict['module-phase'] = 'init'
        self._set_log_context("%s.%s" % (mobj.group(1),
                            self.state_dict['module-mode']))
        self.state_dict['module-file'] = None
    
    def setModuleLoading2(self, section, level, mobj):
        self.state_dict['module'] = mobj.group(1)
        
        # By the 'registering objects' message we just know that the
        # module is present in the server.
        # So, reset state, mark module as present
        self.state_dict['module-phase'] = 'reg'
        self.state_dict['module-file'] = None
        self.state_dict.setdefault('regd-modules',[]).append(mobj.group(1))
        
        #self._set_log_context("%s.%s" % (mobj.group(1),
        #                    self.state_dict['module-mode']))
    
    def setModuleFile(self, section, level, mobj):
        if mobj.group(2) == 'objects':
            return
        self.state_dict['module'] = mobj.group(1)
        self.state_dict['module-phase'] = 'file'
        self._set_log_context("%s.%s" % (mobj.group(1),
                            self.state_dict['module-mode']))
        self.state_dict['module-file'] = mobj.group(2)
        self.log.debug("We are processing: %s/%s", self.state_dict['module'],
                self.state_dict['module-file'])
    
    def setTestContext(self, section, level, mobj):
        self.state_dict['module'] = section.split('.',1)[1]
        # self.state_dict['module-mode'] = 'test' # no, leave it
        self._set_log_context("%s.test" % (self.state_dict['module']))

        if level == 'ERROR':
            self.dump_blame(ekeys={ 'Exception': mobj.group(0).split('\n')[0]})
        elif level == 'WARNING':
            sdic = { 'severity': 'warning', 
                    'Message': mobj.group(0).replace('\n',' '),
                   }
            self.dump_blame(ekeys=sdic)

    def unsetTestContext(self, section, level, mobj):
        """ After a testing context, we should clear it and reset, if
            we see an "init" line
        """
        if self.state_dict.get('context',False) and \
                self.state_dict['context'].endswith('.test'):
            self.clear_context()

    def reportExcept(self, section, level, mobj):
        if level not in ('ERROR', 'WARNING'):
            return
        try:
            lines = map(reduce_homedir, mobj.group(1).split('\n'))
            if len(lines) > 2 and 'Traceback' in lines[1]:
                exc_desc = lines[0]
                exc_type, exc_msg = lines[-1].split(':',1)
                traceb = lines[1:-1]
                sdic = { 'Exception type': exc_type, 'Exception': exc_msg,
                        'Traceback': '\n'.join(traceb) }
                if exc_desc.startswith('report exception: '):
                    exc_desc = exc_desc[18:]
                sdic['Message'] = "%s: %s for %s" % (exc_type, exc_msg, exc_desc)
                self._decode_tb(traceb, sdic)
                self.dump_blame(ekeys=sdic)
            else:
                self.dump_blame(ekeys={ 'severity': 'warning', 'Message': lines[0] })
        except Exception:
            self.log.debug("Cannot decode report exception", exc_info=True)
            pass

    def cursorHanging(self, section, level, mobj):
        self.dump_blame(ekeys={ 'severity': 'warning', 
                    'module-file': reduce_homedir(mobj.group(1)),
                    'module-line': mobj.group(2),
                    'Message': 'Cursor not explicitly closed'})

    def __init__(self):
        threading.Thread.__init__(self)
        self.is_running = False
        self.is_ready = False
        # Will hold info about current op. of the server
        self.state_dict = {'module-mode': 'startup'}
        self.log = logging.getLogger('srv.thread')
        self.log_state = logging.getLogger('bqi.state') # will receive command-like messages
        logging.getLogger('RPC.Remote').setLevel(1000) # we don't want that, we debug anyway
        self._parsers = {}
        self._exc_parsers = []
        self._lports = {}

    def _init_parsers(self):
        self.regparser('web-services', 
                'the server is running, waiting for connections...', 
                self.setRunning)
        self.regparser('server', 
                'OpenERP server is running, waiting for connections...', 
                self.setRunning)
        self.regparser('web-services',
                re.compile(r'starting (.+) service at ([0-9a-f\.\:\[\]]+) port ([0-9]+)'),
                self.setListening)
        self.regparser('init',re.compile(r'module (.+):'), self.unsetTestContext)
        
        self.regparser('init',re.compile(r'module (.+): creating or updating database tables'),
                self.setModuleLoading)
        self.regparser('init', re.compile(r'module (.+): loading objects$'),
                self.setClearContext)
        self.regparser('init', 'updating modules list', self.setClearContext)
        self.regparser('init', re.compile(r'.*\: Assertions report:$', re.DOTALL),
                self.setClearContext)

        self.regparser('init', re.compile(r'module (.+): registering objects$'),
                self.setModuleLoading2)
        self.regparser('init',re.compile(r'module (.+): loading (.+)$'),
                self.setModuleFile)
        self.regparser('tests.*', re.compile(r'.*', re.DOTALL), self.setTestContext, multiline=True)
        self.regparser('report', re.compile(r'rml_except: (.+)', re.DOTALL), self.reportExcept, multiline=True)
        self.regparser('report', re.compile(r'Exception at: (.+)', re.DOTALL), self.reportExcept, multiline=True)
        self.regparser('db.cursor', re.compile(r'Cursor not closed explicitly.*Cursor was created at (.+.py):([0-9]+)$', re.DOTALL), self.cursorHanging, multiline=True)
        
        self.regparser_exc('XMLSyntaxError', re.compile(r'line ([0-9]+), column ([0-9]+)'),
                            lambda etype, ematch: { 'file-line': ematch.group(1), 'file-col': ematch.group(2)} )

    def dump_blame(self, exc=None, ekeys=None):
        """Dump blame information for sth that went wrong
        
        @param exc the exception object, if available
        @param ekeys extra blame keys to dump
        """
        blog = logging.getLogger('bqi.blame')
        
        
        sdict = self.state_dict.copy()
        
        if exc:
            emsg = ''
            if isinstance(exc, xmlrpclib.Fault):
                # faultCode from openerp is string, but standard is int
                if isinstance(exc.faultCode, int):
                    emsg = exc.faultString.strip()
                else:
                    emsg = "%s" % exc.faultCode
                # try to get the server-side exception
                # Note that exc is /not/ the exception object of the server
                # itself, but the one that was transformed into an xmlrpc
                # fault and sent to us. So, we can only do string processing
                # on it.
                try:
                    faultLines = exc.faultString.rstrip().split('\n')
                    lfl = len(faultLines)-1
                    
                    while lfl > 0:
                        if not faultLines[lfl]:
                            lfl -= 1
                            continue
                        if ':' not in faultLines[lfl][:20]:
                            lfl -= 1
                            continue
                        break

                    if lfl < 0:
                        stype = ''
                        sstr = '\n'.join(faultLines[-2])
                    else:
                        ses = faultLines[lfl]
                        stype, sstr = ses.split(':',1)
                        if '--' in sstr:
                            stype = 'osv.%s' % (sstr.split('--')[1].strip())
                            emsg = ' '.join(faultLines[lfl+1:])
                    
                    if stype:
                        sdict['Exception type'] = stype
                    
                    # now, use the parsers to get even more useful information
                    # from the exception string. They should return a dict
                    # of keys to append to our blame info.
                    # First parser to match wins, others will be skipped.
                    for etype, erege, funct in self._exc_parsers:
                        if etype == None or etype == stype:
                            mm = None
                            if isinstance(erege, basestring):
                                mm = (sstr == erege)
                            else:
                                mm = erege.search(sstr)
                            if not mm:
                                continue
                        
                            # we have a match here
                            red = funct(etype, mm)
                            if isinstance(red, dict):
                                sdict.update(red)
                            else:
                                self.log.debug("why did parser %r return %r?", funct, red)
                            break # don't process other handlers
                    else:
                        self.log.debug("No exception parser for %s: %s", stype, sstr)
                
                except Exception:
                    self.log.debug("Cannot parse xmlrpc exception: %s" % exc.faultString, exc_info=True)
            elif isinstance(exc, RpcServerException):
                try:
                    emsg = "%s" % exc.code
                    faultLines = exc.backtrace.split('\n')
                    lfl = len(faultLines)-1
                    
                    while lfl > 0:
                        if not faultLines[lfl]:
                            lfl -= 1
                            continue
                        if ':' not in faultLines[lfl][:20]:
                            lfl -= 1
                            continue
                        break
                    
                    if lfl < 0:
                        stype = ''
                        sstr = '\n'.join(faultLines[-2])
                    else:
                        ses = faultLines[lfl]
                        stype, sstr = ses.split(':',1)
                        if '--' in sstr:
                            stype = 'osv.%s' % (sstr.split('--')[1].strip())
                            emsg = ' '.join(faultLines[lfl+1:])
                    
                    sdict['Exception type'] = stype or exc.type
                    
                    # now, use the parsers to get even more useful information
                    # from the exception string. They should return a dict
                    # of keys to append to our blame info.
                    # First parser to match wins, others will be skipped.
                    for etype, erege, funct in self._exc_parsers:
                        if etype == None or etype == stype:
                            mm = None
                            if isinstance(erege, basestring):
                                mm = (sstr == erege)
                            else:
                                mm = erege.search(sstr)
                            if not mm:
                                continue
                        
                            # we have a match here
                            red = funct(etype, mm)
                            if isinstance(red, dict):
                                sdict.update(red)
                            else:
                                self.log.debug("why did parser %r return %r?", funct, red)
                            break # don't process other handlers
                    else:
                        self.log.debug("No exception parser for %s: %s", stype, sstr)
                
                except Exception:
                    self.log.debug("Cannot parse rpc exception: %s" % exc, exc_info=True)
            elif len(exc.args):
                emsg = "%s" % exc.args[0]
                sdict["Exception type"] = "%s.%s" % (exc.__class__.__module__ or '', exc.__class__.__name__)
            else:
                emsg = "%s" % exc # better than str(), works with unicode
                sdict["Exception type"] = "%s.%s" % (exc.__class__.__module__ or '', exc.__class__.__name__)

            emsg = reduce_homedir(emsg)
            sdict["Exception"] = emsg.replace('\n', ' ')

        if ekeys:
            sdict.update(ekeys)
        s = ''
        # Format all the blame dict into a string
        for key, val in sdict.items():
            if val:
                s += "%s: %s\n" % (key, val)

        blog.info(s.rstrip())

    def start_full(self):
        """ start and wait until server is up, ready to serve
        """
        self.state_dict['severity'] = 'blocking'
        self.start()
        time.sleep(2.0)
        t = 0
        while not self.is_ready:
            if not self.is_running:
                raise ServerException("Server cannot start")
            if t > 120:
                self.stop()
                raise ServerException("Server took too long to start")
            time.sleep(1)
            t += 1
        if self._lports.get('HTTP') != str(self.port) \
                and (self._lports.get('HTTP6') != str(self.port)):
            self.log.warning("server does not listen HTTP at port %s" % self.port)
        return True

class local_server_thread(server_thread):
    def __init__(self, root_path, port, netport, addons_path, dbname, pyver=None, 
                srv_mode='v600', timed=False, debug=False, do_warnings=False,
                ftp_port=None, defines=False, pyargs=False,
                config=None):
        server_thread.__init__(self)
        self.root_path = root_path
        if srv_mode == 'srv-lib':
            self.root_path = os.path.join(self.root_path, 'openerp')
        self.port = port
        # self.addons_path = addons_path
        self.args = [ 'python%s' %(pyver or ''),]
        if opt.profiled:
            import imp
            self.args.append(imp.find_module('cProfile')[1])
            #self.args.append('-o')
            #self.args.append('profile.dat')
            self.args.append('-s')
            self.args.append('cumulative')
        if do_warnings:
            self.args.append('-Wall')
        if pyargs:
            for pa in pyargs:
                self.args.append('-'+pa)
        self.args += ['%sopenerp-server.py' % root_path,]
        if addons_path:
            self.args += [ '--addons-path=%s' % addons_path ]
        if opt.debug_sql:
            self.args += [ '--log-level=debug_sql' ]
        elif debug:
            self.args += [ '--log-level=debug' ]
        else:
            self.args += [ '--log-level=test' ]
            
        if config:
            self.args += [ '-c', config ]

        # TODO: secure transport, persistent ones.
        http_if = opt.http_interface or '127.0.0.1'
        if srv_mode in ('v600', 'srv-lib'):
            self.args.append('--xmlrpc-interface=%s' % http_if)
            self.args.append('--xmlrpc-port=%s' % port )
            self.args.append('--no-xmlrpcs')
            # self.args.append('--no-database-list') No, it cannot work!
            # We need to be able to list db's for the drop-db and create-db actions. :S
            # FIXME: server doesn't support this!
            #if ftp_port:
            #    self.args.append('--ftp_server_port=%d' % int(ftp_port))
        elif srv_mode == 'pg84':
            self.args.append('--httpd-interface=%s' % http_if )
            self.args.append('--httpd-port=%s' % port )
            self.args.append('--no-httpds')
            self.args.append('-Dtests.nonfatal=True')
            self.args.append('-Ddatabases.allowed=%s' % dbname)
            if ftp_port:
                self.args.append('-Dftp.port=%s' % ftp_port)
            if defines:
                for d in defines:
                    self.args.append('-D%s' % d)
        else:
            raise RuntimeError("Invalid server mode %s" % srv_mode)

        if netport:
            self.args.append('--netrpc-port=%s' % netport)
        else:
            self.args.append('--no-netrpc')

        if timed:
            self.args.insert(0, 'time')
        if opt.smtp_maildir:
            self.args.append('--smtp=maildir:%s' % os.path.abspath(os.path.expanduser(opt.smtp_maildir)))
            self.args.append('--smtp-user=user')
        self.proc = None
        self._io_bufs = {} # Buffers for stdin, stdio processing

        # Regular expressions:
        self.linere = re.compile(r'\[(.*)\] ([A-Z_]+):([\w\.-]+):(.*)$', re.DOTALL)
        self.linewere = re.compile(r'(.*\.py):([0-9]+): ([A-Za-z]*Warning): (.*)$', re.DOTALL)
        
        self.log_sout = logging.getLogger('server.stdout')
        self.log_serr = logging.getLogger('server.stderr')

        self._init_parsers()

    def _io_flush(self):
        """ Process any remaining data in _io_bufs
        """

        for fd in self._io_bufs.keys():
            r = self._io_bufs[fd]
        
            r = r.rstrip("\n")

            if not r:
                continue

            m = em = None
            if fd == self.proc.stderr.fileno():
                em = self.linewere.match(r)
            else:
                m = self.linere.match(r)
            if m:
                self._io_process(fd, m, False)
            elif em:
                self._io_err_process(fd, em, False)
            elif r.startswith("Traceback (most recent call last):") \
                    and fd is self.proc.stderr.fileno():
                # Stray, fatal exception may appear on stderr
                try:
                    traceb, excs = r.rsplit('\n',1)
                    exc_type, exc_msg = excs.split(':',1)
                    exc_msg = reduce_homedir(exc_msg)
                    traceb = reduce_homedir(traceb)
                    sdic = { 'Exception type': exc_type, 'Exception': exc_msg,
                            'Traceback': traceb }
                    self._decode_tb(traceb, sdic)
                    self.dump_blame(ekeys=sdic)
                except Exception:
                    self.log.debug("Cannot decode stderr", exc_info=True)
                    pass

            # now, print the line at stdout
            if fd is self.proc.stdout.fileno():
                olog = self.log_sout
            else:
                olog = self.log_serr
            if m and m.group(2) in ('DEBUG', 'DEBUG_RPC', 'DEBUG_SQL', 
                                'DEBUG_RPC_ANSWER'):
                olog.debug(r)
            else:
                olog.info(r)

            # Reset the buffer
            self._io_bufs[fd] = ''

        return # end of _io_flush()
        
    def _io_read(self, fd, fd_obj):
        """ Read data from fd_obj into _io_bufs[fd] and process
        """
        rl = fd_obj.readline()
        if not rl:
            return
        
        mmatch = ematch = None
        if fd_obj is self.proc.stderr:
            ematch = self.linewere.match(rl)
        else:
            mmatch = self.linere.match(rl)
        if mmatch:
            # we don't append this line, but process the previous
            # data.
            self._io_flush()
            if self._io_process(fd, mmatch, True):
                # It is a single line message that was processed.
                if fd_obj is self.proc.stdout:
                    olog = self.log_sout
                else:
                    olog = self.log_serr
                # Log and go, don't buffer
                if rl.endswith('\n'):
                    rl = rl[:-1]
                if mmatch.group(2) in ('DEBUG', 'DEBUG_RPC', 'DEBUG_SQL'):
                    olog.debug(rl)
                else:
                    olog.info(rl)
                return
        elif ematch:
            self._io_flush()
            self._io_err_process(fd, ematch, True)
        
        self._io_bufs[fd] += rl # with trailing newline

    def _io_process(self, fd, mmatch, first_try):
        """Process an input log line mmatch, from fd 
        
            @return if the line has been processed.
        """
        
        may_process = False # Need to process now.
        parsers = []
        pkeys = ['*', mmatch.group(3) ]
        if '.' in mmatch.group(3):
            pkeys.append( mmatch.group(3).split('.', 1)[0]+'.*')
        for pk in pkeys:
            parsers.extend(self._parsers.get(pk,[]))
        
        pmatches = [] # we will put all matched parsers here.
        for regex, funct, multiline in parsers:
            if isinstance(regex, basestring):
                if regex == mmatch.group(4).rstrip():
                    if (not first_try) or (not multiline):
                        may_process = True
                    pmatches.append((regex, funct, None) )
            else:  # elif isinstance(regex, re.RegexObject):
                mm = regex.match(mmatch.group(4).rstrip())
                if mm:
                    if (not first_try) or (not multiline):
                        may_process = True
                    pmatches.append((regex, funct, mm) )

        # Finished matching here.
        
        if (not pmatches) or not may_process:
            return False
        
        # When just one of the parsers is positive, we have to
        # process all of them now, because won't buffer for multiline.
        
        for regex, funct, mm in pmatches:
            if callable(funct):
                funct(mmatch.group(3), mmatch.group(2), mm or mmatch.group(4))
            elif isinstance(funct, tuple):
                logger = logging.getLogger('bqi.'+ funct[0])
                level = funct[1]
                if mm:
                    log_args = mm.groups('')
                else:
                    log_args = []
                logger.log(level, funct[2], *log_args)
            else:
                if mm:
                    log_args = mm.groups('')
                else:
                    log_args = []

                self.log.info(funct, *log_args)

        return True

    def _io_err_process(self, fd, ematch, first_try):
        """Process a stderr log line ematch, from fd == stderr
        
            @return if the line has been processed.
        """
        if (not first_try):
            return False
  
        logger = logging.getLogger('bqi.blame')
        elines = ematch.group(4).split('\n')
        if len(elines) > 1 and elines[1:]:
            csnip = "\nCodeSnip:%s" % ' '.join(elines[1:])
        else:
            csnip = ''
        filename = reduce_homedir(ematch.group(1))
        logger.warning("Message: %s\nseverity: pywarn\nmodule-file: %s\nfile-line: %s\nException Type: %s%s",
                    elines[0], filename, ematch.group(2), 
                    ematch.group(3), csnip)

        return True

    def _decode_tb(self, traceb, sdic):
        """ Decode a traceback and store info in sdic
        """
        tbre= re.compile(r'File "(.+)", line ([0-9]+)')
        blines = []
        if not traceb:
            return
        if isinstance(traceb, basestring):
            blines = traceb.split('\n')
        else:
            blines = list(traceb[:])
        blines.reverse()
        for line in blines:
            line = line.strip()
            if line == '^':
                continue
            tm = tbre.match(line)
            if tm:
                sdic['module-file'] = tm.group(1)
                sdic['file-line'] = tm.group(2)
                break
        return

    def stop(self):
        if (not self.is_running) and (not self.proc):
            time.sleep(2)

        if not self.proc :
            self.log.error("Program has not started")
        elif self.proc.returncode is not None:
            self.log.warning("Program is not running")
        else:
            self.log.info("Terminating..")
            if not hasattr(self.proc,'terminate'):
                os.kill(self.proc.pid, signal.SIGTERM)
            else:
                self.proc.terminate()
            
            i = 0
            while self.proc.returncode is None:
                i += 1
                if i == 0:
                    pass
                elif opt.profiled:
                    # wait for profile indefinitely
                    pass
                elif i == 2:
                    self.log.warning("Server didn't die, sending second term signal..")
                    os.kill(self.proc.pid, signal.SIGTERM)
                elif i > 3:
                    self.log.warning("Server didn't die, sending a kill signal..")
                    os.kill(self.proc.pid, signal.SIGKILL)
                else:
                    self.log.info("Waiting the server to terminate for %s sec..", (i*5))
                time.sleep(5)

            self.log.info('Terminated.')

        
    def run(self):
        try:
            self.log.info("will run: %s", ' '.join(self.args))
            self.proc = subprocess.Popen(self.args, shell=False, cwd=None, 
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.is_running = True
            self.log.info("server running at pid: %d", self.proc.pid)
            pob = select.poll()
            pob.register(self.proc.stdout)
            pob.register(self.proc.stderr)
            fdd = { self.proc.stdout.fileno(): self.proc.stdout ,
                    self.proc.stderr.fileno(): self.proc.stderr }
                    
            self._io_bufs = { self.proc.stdout.fileno(): '',
                    self.proc.stderr.fileno(): '' }
        
            while True:
                self.proc.poll()
                if self.proc.returncode is not None:
                    break
                # Now, see if we have output:
                p = pob.poll(10000)
                for fd, event in p:
                    if event == select.POLLIN:
                        self._io_read(fd, fdd[fd])
        
            self._io_flush()
            self.is_ready = False
            self.log.info("Finished server with: %d", self.proc.returncode)
        finally:
            self.is_running = False

class RemLogHandler(object):
    def __init__(self, parent):
        self.parent = parent
        self.log_sout = logging.getLogger('server.stdout')
    
    def handle(self, rec):
        parsers = []
        pkeys = ['*', rec.name ]
        if '.' in rec.name:
            pkeys.append( rec.name.split('.', 1)[0]+'.*')
        for pk in pkeys:
            parsers.extend(self.parent._parsers.get(pk,[]))
        
        pmatches = [] # we will put all matched parsers here.
        for regex, funct, multiline in parsers:
            if isinstance(regex, basestring):
                if regex == rec.msg.rstrip():
                    pmatches.append((regex, funct, None) )
            else:  # elif isinstance(regex, re.RegexObject):
                mm = regex.match(rec.msg.rstrip())
                if mm:
                    pmatches.append((regex, funct, mm) )

        # Finished matching here.
        
        for regex, funct, mm in pmatches:
            if callable(funct):
                funct(rec.name, rec.levelname, mm or rec.msg)
            elif isinstance(funct, tuple):
                logger = logging.getLogger('bqi.'+ funct[0])
                level = funct[1]
                if mm:
                    log_args = mm.groups('')
                else:
                    log_args = []
                logger.log(level, funct[2], *log_args)
            else:
                if mm:
                    log_args = mm.groups('')
                else:
                    log_args = []

                self.log.info(funct, *log_args)
        
        tf = time.strftime('%Y-%m-%d %H:%M:%S')
        if rec.level > logging.DEBUG:
            self.log_sout.info('[%s] %s:%s:%s', tf, rec.levelname, rec.name, rec.msg)
        else:
            self.log_sout.debug('[%s] %s:%s:%s', tf, rec.levelname, rec.name, rec.msg)

class remote_server_thread(server_thread):
    def __init__(self, **kwargs):
        server_thread.__init__(self)
        global opt
        self._must_stop = False
        self.session = None
        self.port = opt.port
        self._init_parsers()
    
    def run(self):
        self.log.info("Run")
        self.is_running = True
        global opt, connect_dsn

        try:
            # we open an independent connection to the server
            if opt.url:
                self.session = client_session(**client_kwargs)
            else:
                self.session = xml_session()

            self.session.open(**connect_dsn)
            # when open suceeds, it means the server is running and reachable
            self.setup_remote_logs(connect_dsn)
            self.is_ready = True
            self._lports['HTTP'] = self.port # fool self.start_full()

            while not self._must_stop:
                self.session.loop_once()
                time.sleep(5)

            # TODO: connect to remote-enabled loggers, if any
            self.is_ready = False
            self.log.info("Stopped watching server")
        except RpcException, e:
            self.log.error("Remote connection failed with %s: %s", e.__class__.__name__, e.info)
        finally:
            self.is_running = False

    def stop(self):
        self.log.info("Disconnecting from server")
        # session close? TODO
        if self.session:
            self.session.logout()
        self._must_stop = True
        pass
    
    def _io_flush(self):
        pass
    
    def setup_remote_logs(self, dsn):
        def _loop_get_logs(trans):
            try:
                while not self._must_stop:
                    trans.process_next_logs()
            except Exception:
                self.log.warning("Remote logging stopped:", exc_info=True)
        try:
            handler = RemLogHandler(self)
            trans = getTransportFromDSN(dsn, handler=handler)
            thr = threading.Thread(name='remote_log_watcher',
                    target=_loop_get_logs,  args=(trans,))
            # fire and forget
            thr.daemon = True
            thr.start()
            self.log.info("Remote log watcher established for server")
        except Exception:
            self.log.warning("Cannot establish remote log watching:", exc_info=True)

class xml_session(object):
    """ This class resembles the openerp_libclient.session, using xmlrpclib
    """
    def __init__(self):
        self.uid = None
        self.passwd = None
        self.super_passwd = None
        self.dbname = None
        self.uri = None
    
    def open(self, proto, **kwargs):
        assert proto == 'http', "Built-in client cannot handle %s protocol" % proto
        global logger
        
        self.uri = 'http://%s:%s' % (kwargs['host'], kwargs['port'])
        self.user = kwargs['user']
        self.passwd = kwargs['passwd']
        self.dbname = kwargs['dbname']
        self.super_passwd = kwargs.get('superpass', 'admin')
        
        # do a trivial connectivity check:
        try:
            conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/db')
            sv = conn.server_version()
            # TODO: parse, remember sv
        except xmlrpclib.Fault, e:
            logger.error("Cannot connect to server: %s", e)
            logger.debug("Cannot connect:", exc_info=True)
            raise ClientException(e.faultString)
        
    def login(self):
        conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/common')
        uid = conn.login(self.dbname, self.user, self.passwd)
        self.uid = uid
        return uid

    def call(self, obj, method, args, auth_level='db', notify=True):
        conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/' + obj)
        if auth_level == 'pub':
            pass
        elif auth_level == 'root':
            args= (self.super_passwd,) + args
        elif auth_level == 'db':
            if not self.uid:
                raise Exception("Session not open!")
            args = (self.dbname, self.uid, self.passwd,) + args
        else:
            raise RuntimeError("Incorrect level %s" % auth_level)
        res = getattr(conn,method)(*args)
        return res

    def logged(self):
        return self.uid is not None

    def loop_once(self):
        pass

    def logout(self):
        self.uri = None #let all further attempts fail

class bqi_RPCProxy(object):
    def __init__(self, session, resource):
        self.resource = resource
        self.session = session

    def __getattr__(self, name):
        return bqi_RPCFunction(self.session, self.resource, name)

class bqi_RPCFunction(object):
    def __init__(self, session, obj, func_name):
        self.obj = obj
        self.func = func_name
        self.session = session

    def __call__(self, *args):
        return self.session.call('/object', method='execute', args=(self.obj, self.func)+args)

class client_worker(object):
    """ This object will connect to a server and perform the various tests.
    
        It holds some common options.
    """
    
    def __init__(self, uri, options):
        global server
        global opt
        self.log = logging.getLogger('bqi.client')
        if not server.is_ready:
            self.log.error("Server not ready, cannot work client")
            raise RuntimeError()
        self.uri = uri
        
        self.dbname = options['dbname']
        self.super_passwd = options['super_passwd']
        self.series = options['server_series']
        self.do_demo = not opt.no_demo
        self.has_os_times = self.series in ('pg84', 'v600', 'srv-lib') #TODO
        if opt.url:
            self._session_class = client_session
        else:
            self._session_class = xml_session
            self._session_kwargs = {}
        
        self.session = self._session_class(**client_kwargs)
        self.session.open(**connect_dsn)

    def try_login(self):
        if not self.session.logged():
            self.session.login()

    def orm_proxy(self, model):
        """ Return ORM proxy object, like client lib
        """
        self.try_login()
        return bqi_RPCProxy(self.session, model)
        
    def _execute(self, connector, method, *args):
        raise RuntimeError()
    
    def rpc_call(self, obj, method, *args, **kwargs):
        auth_level = kwargs.pop('auth_level', 'db')
        notify = kwargs.pop('notify', True)
        if kwargs:
            raise RuntimeError("Invalid kwargs: %r" % kwargs)
        if auth_level == 'db':
            self.try_login()
        self.log.debug("Sending command '%s' to server", method)
        res = self.session.call(obj, method=method, args=args, auth_level=auth_level, notify=notify)
        self.log.debug("Command '%s' returned from server", method)
        return res
    
    def execute_common(self, level, func, *args):
        server.state_dict['severity'] = 'warning'
        print "execute: %r %r" % (func, args)
        return self.rpc_call('/common', func, *args, auth_level=level)

    def _login(self, user=None, passwd=''):
        global connect_dsn
        if user is None:
            # use the existing session
            session = self.session
        else:
            session = self._session_class(**client_kwargs)
            session.open(**connect_dsn)
        
        uid = session.login()
        if uid:
            if session is not self.session:
                self.log.info("User changed to %s@%s" %(user, self.dbname))
                self.session = session
        else:
            self.log.error("Cannot login as %s@%s" %(user, self.dbname))
            if session is not self.session:
                self.log.info("Falling back to previous session")
        return uid

    def import_translate(self, translate_in):
        # TODO !
        server.state_dict['module-mode'] = 'translate'
        self.log.debug("Executing module.lang.import %s", translate_in)
        wiz_id = self.rpc_call('/wizard', 'create', 'module.lang.import')
        if not wiz_id:
            raise ServerException("The language import wizard doesn't exist")
        for trans_in in translate_in:
            lang,ext = os.path.splitext(trans_in.split('/')[-1])
            state = 'init'
            datas = {'form':{}}
            while state!='end':
                res = self.rpc_call('/wizard','execute', wiz_id, datas, state, {})
                if 'datas' in res:
                    datas['form'].update( res['datas'].get('form',{}) )
                if res['type']=='form':
                    for field in res['fields'].keys():
                        datas['form'][field] = res['fields'][field].get('value', False)
                    state = res['state'][-1][0]
                    trans_obj = open(trans_in)
                    datas['form'].update({
                        'name': lang,
                        'code': lang,
                        'data' : base64.encodestring(trans_obj.read())
                    })
                    trans_obj.close()
                elif res['type']=='action':
                    state = res['state']
        return True

    def check_quality(self, modules, quality_logs):
        quality_logs += 'quality-logs'
        qual_obj = self.orm_proxy('module.quality.check')
        final = {}
        qlog = logging.getLogger('bqi.qlogs')
        
        self.log.debug("Checking quality of modules %s", ', '.join(modules))
        for module in modules:
            qualityresult = {}
            test_detail = {}
            server.state_dict['module-mode'] = 'quality'
            try:
                quality_result = qual_obj.check_quality(module)
                # self.log.debug("Quality result: %r", quality_result)
                detail_html = ''
                html = '''<html><body><a name="TOP"></a>'''
                html +="<h1> Module: %s </h1>"%(quality_result['name'])
                html += "<h2> Final score: %s</h2>"%(quality_result['final_score'])
                html += "<div id='tabs'>"
                html += "<ul>"
                for x,y,detail in quality_result['check_detail_ids']:
                    test = detail.get('name')
                    msg = detail.get('message','')
                    score = round(float(detail.get('score',0)),2)
                    html += "<li><a href=\"#%s\">%s</a></li>"%(test.replace(' ','-'),test)
                    detail_html +='''<div id=\"%s\"><h3>%s (Score : %s)</h3><font color=red><h5>%s</h5></font>%s</div>'''%(test.replace(' ', '-'), test, score, msg, detail.get('detail', ''))
                    test_detail[test] = (score,msg,detail.get('detail',''))
                html += "</ul>"
                html += "%s"%(detail_html)
                html += "</div></body></html>"
                
                qlog.info('Module: "%s", score: %s\n%s', quality_result['name'], 
                        quality_result['final_score'], html)
            except xmlrpclib.Fault, e:
                self.log.error('xmlrpc exception: %s', reduce_homedir(e.faultCode.strip()))
                self.log.error('xmlrpc +: %s', reduce_homedir(e.faultString.rstrip()))
                server.dump_blame(e, ekeys={ 'context': '%s.qlog' % module,
                            'module': module, 'severity': 'warning'})
            except RpcException, e:
                server.dump_blame(e, ekeys={ 'context': '%s.qlog' % module,
                            'module': module, 'severity': 'warning'})
            # and continue with other modules..
        return True

    def get_ostimes(self, prev=None):
        if not self.has_os_times:
            self.log.debug("Using client-side os.times()")
            ost = list(os.times())
            if prev is not None:
                ost = ost + ost
                if len(prev) > 5:
                    prev = prev[5:]
                for i in range(0,5):
                    ost[i] -= prev[i]
            return ost
        try:
            ost = self.rpc_call('/common','get_os_time', auth_level='root')
            ost = list(ost)
            if prev is not None:
                ost = ost + ost
                if len(prev) > 5:
                    prev = prev[5:]
                for i in range(0,5):
                    ost[i] -= prev[i]
            return ost
        except Exception:
            self.log.debug("Get os times", exc_info=True)
            self.has_os_times = False
            return ( 0.0, 0.0, 0.0, 0.0, 0.0 )


    def wait(self, id, timeout=600.0):
        progress=0.0
        expire = time.time() + timeout
        while not progress==1.0:
            if time.time() >= expire:
                raise ClientException("Timed out creating the database")
            time.sleep(2.0)
            progress,users = self.rpc_call('/db','get_progress', id, auth_level='root')
            self.log.debug("Progress: %s", progress)
        return True

    def list_db(self):
        return self.rpc_call('/db', 'list', auth_level='pub')

    def create_db(self, lang='en_US'):
        server.state_dict['severity'] = 'blocking'
        db_list = self.list_db()
        if self.dbname in db_list:
            raise ClientException("Database already exists, drop it first!")
        id = self.rpc_call('/db','create', self.dbname, self.do_demo, lang, auth_level='root')
        self.wait(id)
        server.clear_context()
        if not self.install_module(['base_module_quality',]):
            self.log.warning("Could not install 'base_module_quality' module.")
            # but overall pass
        server.clear_context()
        self.log.info("Successful create of db: %s", self.dbname)
        return True

    def drop_db(self):
        db_list = self.list_db()
        if self.dbname in db_list:
            self.log.info("Going to drop db: %s", self.dbname)
            self.rpc_call('/db', 'drop', self.dbname, auth_level='root')
            self.log.info("Dropped db: %s", self.dbname)
            return True
        else:
            self.log.warning("Not dropping db '%s' because it doesn't exist", self.dbname)
            return False

    def install_module(self, modules):
        # what buttons to press at each state:
        self.log.debug("Installing modules: %s", ', '.join(modules))
        server.state_dict['module-mode'] = 'install'
        module_obj = self.orm_proxy('ir.module.module')
        
        bad_mids = module_obj.search([('name','in',modules), ('state','=','uninstallable')])
        module_ids = module_obj.search([('name','in',modules)])
        if not module_ids:
            self.log.error("Cannot find any of [%s] modules to install!",
                            ', '.join(modules))
            return False
        
        # Read the names of modules, so that we can identify them.
        mod_names_res = module_obj.read(module_ids, ['name'])
        mod_names = {}
        for mr in mod_names_res:
            mod_names[mr['id']] = mr['name']

        # self.log.debug("Module names: %r", mod_names)
        
        if bad_mids:
            bad_names = ', '.join([ mod_names[id] for id in bad_mids])
            self.log.warning("Following modules are not installable: %s", bad_names)

        if True: # just for the block
            missing_mos = []
            for mo in modules:
                if mo not in mod_names.values():
                    missing_mos.append(mo)
            if missing_mos:
                server.dump_blame(ekeys= { 'context': 'bqi.rest', 'severity': 'warning',
                        'module-phase': False, 'module': False,
                        'Message': 'The following modules are not found: %s' % \
                            ', '.join(missing_mos)
                        })
        
        for mid in module_ids:
            if mid in bad_mids:
                continue
            try:
                # We have to try one-by-one, because we want to be able to
                # recover from an exception.
                module_obj.button_install([mid,])
            except xmlrpclib.Fault, e:
                logger.error('xmlrpc exception: %s', reduce_homedir(e.faultCode.strip()))
                logger.error('xmlrpc +: %s', reduce_homedir(e.faultString.rstrip()))
                server.dump_blame(e, ekeys={ 'context': '%s.install' % mod_names[mid],
                            'module': mod_names[mid], 'severity': 'error'})
            except RpcException, e:
                server.dump_blame(e, ekeys={ 'context': '%s.install' % mod_names[mid],
                            'module': mod_names[mid], 'severity': 'error'})

        server.state_dict['severity'] = 'blocking'
        ret = self._modules_upgrade()
        server.clear_context()
        return ret

        
    def _modules_upgrade(self):
        """ Perform the modules upgrade wizard, for ones previously selected
        """
        wiz_id = False
        ret = False
        try:
            form_presses = { 'init': 'start', 'next': 'start',  'config': 'end',  'start': 'end'}
            wiz_id = self.rpc_call('/wizard', 'create', 'module.upgrade.simple', notify=False)
            datas = {}
            if wiz_id:
                ret = self.run_wizard(wiz_id, form_presses, datas, notify=False)
            return True
        except xmlrpclib.Fault, e:
            if e.faultCode == 'wizard.module.upgrade.simple':
                self.log.debug("Could not find the old-style wizard for module upgrade, trying the new one")
                wiz_id = False
            else:
                raise
        except RpcException, e:
            if e.args[0] == 'wizard.module.upgrade.simple':
                self.log.debug("Could not find the old-style wizard for module upgrade, trying the new one")
                wiz_id = False
            else:
                raise

        try:
            wiz_obj = self.orm_proxy('base.module.upgrade')
            wiz_id = wiz_obj.create({})
        except (xmlrpclib.Fault, RpcException), e:
            raise ServerException("No usable wizard for module upgrade found, cannot continue")

        ret = wiz_obj.upgrade_module([wiz_id,], {})
        self.log.debug("Upgrade wizard returned: %r", ret)
        
        assert ret, "The upgrade wizard must return some dict, like redirect to the config view"
        return True

    def run_wizard(self, wiz_id, form_presses, datas, notify=False):
        """ Simple Execute of a wizard, press form_presses until end.
        
            This tries to go through a wizard, by trying the states found
            in form_presses. If form_presses = { 'start': 'foo', 'foo': 'end'}
            then the 'foo' button(=state) will be pressed at 'start', then
            the 'end' button at state 'foo'.
            If it sucessfully reaches the 'end', then the wizard will have
            passed.
        """
        
        state = 'init'
        log = logging.getLogger("bqi.wizard") #have a separate one.
        i = 0
        good_state = True
        while state!='end':
            res = self.rpc_call('/wizard', 'execute', wiz_id, datas, state, {}, notify=notify)
            i += 1
            if i > 100:
                log.error("Wizard abort after %d steps", i)
                raise RuntimeError("Too many wizard steps")
            
            next_state = 'end'
            if res['type'] == 'form':
                if state in form_presses:
                    next_state = form_presses[state]
                pos_states = [ x[0] for x in res['state'] ]
                if next_state in pos_states:
                    log.debug("Pressing button for %s state", next_state)
                    state = next_state
                else:
                    log.warning("State %s not found in %s, forcing end", next_state, pos_states)
                    state = 'end'
                    good_state = False
            elif res['type'] == 'action':
                if state in form_presses:
                    next_state = form_presses[state]
                if res['state'] in pos_states:
                    log.debug("Pressing button for %s state", next_state)
                    state = next_state
                else:
                    log.warning("State %s not found in %s, forcing end", next_state, pos_states)
                    state = 'end'
                    good_state = False
            else:
                log.debug("State: %s, res: %r", state, res)
        log.info("Wizard ended in %d steps", i)
        return good_state

    def upgrade_module(self, modules):
        server.state_dict['module-mode'] = 'upgrade'
        module_obj = self.orm_proxy('ir.module.module')
        module_ids = module_obj.search([('name','in',modules)])
        module_obj.button_upgrade(module_ids)
        
        server.state_dict['severity'] = 'blocking'
        ret = self._modules_upgrade()
        server.clear_context()
        return ret

    def uninstall_module(self, modules):
        server.state_dict['module-mode'] = 'uninstall'
        module_obj = self.orm_proxy('ir.module.module')
        module_ids = module_obj.search([('name','in',modules)])
        module_obj.button_uninstall(module_ids)
        
        server.state_dict['severity'] = 'warning'
        ret = self._modules_upgrade()
        server.clear_context()
        return ret

    def fields_view_get(self):
        """ This test tries to retrieve fields of all the pooler (orm) objects.
        
        It checks the orm.fields_view_get() of each orm, because that function
        involves an important part of the ORM logic.
        """
        server.clear_context()
        server.state_dict['severity'] = 'error'
        ost_start = self.get_ostimes()
        ost_self_start = os.times()
        
        if self.series in ('v600', 'srv-lib'):
            # the obj_list is broken in XML-RPC1 for v600
            obj_list = [] # = self._execute(obj_conn, 'obj_list', self.dbname, uid, self.pwd)
        elif self.series == 'pg84':
            obj_list = self.rpc_call('/object', 'obj_list', auth_level='root')
            self.log.debug("Got these %d objects: %r ...", len(obj_list), obj_list[:20])
        
        # Get the models from the ir.model object
        ir_model_obj = self.orm_proxy('ir.model')
        ir_model_ids = ir_model_obj.search([])
        
        # also, look for model references in ir.model.data
        imd_obj = self.orm_proxy('ir.model.data')
        imd_ids = imd_obj.search([('model','=','ir.model')])
        imd_res = imd_obj.read(imd_ids, ['module', 'name', 'res_id'])
        
        model_tbl = {}
        for it in imd_res:
            if it['res_id'] not in ir_model_ids:
                server.dump_blame(None, ekeys={ 'context': '%s.check' % it['module'],
                            'module': it['module'], 'severity': 'error', 
                            'Exception': 'Model %s.%s referenced in ir.model.data but %s not exist in ir.model!' % \
                                    (it['module'], it['name'], it['res_id'])})
                continue
            model_tbl[it['res_id']] = (it['module'], it['name'])
        
        model_res = ir_model_obj.read(ir_model_ids, ['name', 'model'])
        ost_for = self.get_ostimes(ost_start)
        self.log.debug("Resolved the list of models in User: %.3f, Sys: %.3f, Real: %.3f",
                                    ost_for[0], ost_for[1], ost_for[4])
        ost = ost_for

        for mod in model_res:
            module = model_tbl.get(mod['id'],(None,False))[0]
            self.log.debug("Testing %s.%s", module or '<root>', mod['model'])
            try:
                # We are using direct rpc calls, rather than ORM proxies, because we
                # want to be low level.
                fvg = self.rpc_call('/object','execute',
                                mod['model'], 'fields_view_get', False, 'form', {}, True)
                ost = self.get_ostimes(ost)
                if not fvg:
                    server.dump_blame(None, {'context': '%s.check' % (module or 'custom'),
                            'module': module or '', 'severity': 'error', 
                            'Message': 'No form view for model %s' % mod['model'] })
                else:
                    if ((ost[4] or 0.0) > 1.5 or (ost[0] or 0.0) > 0.6) and self.has_os_times:
                        server.dump_blame(None, {'context': '%s.check' % (module or 'custom'),
                            'module': module or '', 'severity': 'warning', 
                            'Message': 'Form view model %s is slow (u%.3f, r%.3f), please optimize' % \
                                        (mod['model'], ost[0], ost[4] )})
                    else:
                        self.log.debug("Got view for %s in u%.3f, r%.3f",
                                        mod['model'], ost[0], ost[4])
            except xmlrpclib.Fault, e:
                logger.error('xmlrpc exception: %s', reduce_homedir(str(e.faultCode)))
                logger.error('xmlrpc +: %s', reduce_homedir(e.faultString.rstrip()))
                server.dump_blame(e, ekeys={ 'context': '%s.check' % (module or 'custom'),
                            'module': module or '', 'severity': 'error',
                            'Message': '%s.fields_view_get() is broken' % mod['model'] })
            except RpcException, e:
                server.dump_blame(e, ekeys={ 'context': '%s.check' % (module or 'custom'),
                            'module': module or '', 'severity': 'error',
                            'Message': '%s.fields_view_get() is broken' % mod['model'] })
        
        # Statistics:
        ost = self.get_ostimes(ost_for)
        self.log.info("Got %d views in u%.3f, r%.3f", len(model_res), ost[0], ost[4])
        ost_end = os.times()
        self.log.info("Self times: u%.3f, r%.3f",
            ost_end[0] - ost_self_start[0], ost_end[4] - ost_self_start[4])
        server.clear_context()
        return True

    def get_orm_names(self):
        """ Retrieve the list of loaded OSV objects
        """
        server.clear_context()
        server.state_dict['severity'] = 'warning'

        # Get the models from the ir.model object
        ir_model_obj = self.orm_proxy('ir.model')
        ir_model_ids = ir_model_obj.search([])

        model_res = ir_model_obj.read(ir_model_ids, ['model'])

        return [ mod['model'] for mod in model_res]
        
    def get_orm_keys(self, model):
        server.clear_context()
        
        model_obj = self.orm_proxy(model)
        server.state_dict['severity'] = 'warning'
        fks = model_obj.fields_get_keys()
        return fks

    def update_modules_list(self):
        """ Re-scan the modules list
        """
        server.clear_context()
        server.state_dict['severity'] = 'warning'

        wiz_id = False
        ret = False
        
        # If we want to support v5, ever, we shall put the clasic wizard code here
        
        try:
            upd_wiz = self.orm_proxy('base.module.update')
            wiz_id = upd_wiz.create({})
        except (xmlrpclib.Fault, RpcException):
            raise ServerException("No usable wizard for module update found, cannot continue")

        upd_wiz.update_module([wiz_id,], {})
        
        ret = upd_wiz.read([wiz_id,])

        if ret:
            self.log.info("Module update is %s: Added %d, Updated %d modules" % \
                    (ret[0].get('state','?'), ret[0].get('add', 0), ret[0].get('update',0)))
        else:
            self.log.warning("Module update must have failed")
        return True

    def import_trans(self, *args):
        raise NotImplementedError # TODO

    def export_trans(self, *args):
        """Export translations"""
        
        import tarfile
        lang = False
        out_fname = None
        all_modules = False
        format = False
        sourcedirs = False
        dest_dir = '.'
        just_print = False
        addon_paths = []
        while args:
            if args[0] == '-l':
                lang = args[1]
                args = args[2:]
            elif args[0] == '-o':
                out_fname = args[1]
                args = args[2:]
            elif args[0] == '--all':
                all_modules = True
                args = args[1:]
            elif args[0] == '--sourcedirs':
                sourcedirs = True
                args = args[1:]
            elif args[0] == '-n':
                just_print = True
                args = args[1:]
            elif args[0] == '-C':
                dest_dir = args[1]
                args = args[2:]
            elif args[0] == '-F':
                format = args[1]
                args = args[2:]
            else:
                break
        
        if not (out_fname or sourcedirs or dest_dir or just_print):
            self.log.error("Must specify either an output filename or sourcedirs mode")
            return False
        if not (all_modules or args):
            self.log.error("Must specify some modules")
            return False
        if not format:
            if sourcedirs:
                format = 'tgz'
            elif out_fname and (out_fname.endswith('.tar.gz')
                    or out_fname.endswith('.tgz')):
                format = 'tgz'
            elif out_fname and out_fname.endswith('.csv'):
                format = 'csv'
            else:
                format = 'po'
                
        if all_modules:
            mod_domain = [('state', '=','installed'),]
        else:
            mod_domain = [('name', 'in', args[:]), ('state', '=','installed')]
            
        server.clear_context()
        server.state_dict['severity'] = 'warning'
        server.state_dict['context'] = 'i18n.export'

        module_obj = self.orm_proxy('ir.module.module')
        mod_ids = module_obj.search(mod_domain)
        if not mod_ids:
            self.log.error("No modules could be located")
            return False

        wiz_id = False
        self.log.info("Exporting %s translations, %d modules", 
                        lang or 'template', len(mod_ids))
            #server.state_dict['context'] = 'i18n.load.%s' % lang
        ble_obj = self.orm_proxy('base.language.export')
        wiz_id = ble_obj.create( {'lang': lang, 'format': format,
                     'modules': [(6,0, mod_ids)] })
        ble_obj.act_getfile([wiz_id,])
        ret = ble_obj.read([wiz_id,], ['data','name'], {'bin_size':False})
        if not ret:
            self.log.error("Export of translations has failed, no data")
            return False

        if opt.addons_path:
            addon_paths = [os.path.join(opt.root_path,'addons'),] + \
                            opt.addons_path.split(',')
            addon_paths = map(os.path.expanduser, map(str.strip, addon_paths))

        if format == 'tgz' and not out_fname:
            buf = StringIO(base64.decodestring(ret[0]['data']))
            buf.seek(0)
            tarf = tarfile.open(mode='r:gz', fileobj=buf)
            for t in tarf:
                if t.isdir():
                    continue
                if not t.isfile():
                    self.log.warning("Tar exported from server contained %s of type %s",
                            t.name, t.type)
                    continue
                ddir = dest_dir
                newdir = False
                if sourcedirs:
                    bdir, bname = os.path.split(t.name)
                    moddir = bdir.split(os.sep, 1)[0]
                    for ap in addon_paths:
                        if os.path.exists(os.path.join(ap, moddir)):
                            ddir = ap
                            newdir = os.path.join(ap, bdir)
                            break
                if just_print:
                    self.log.info("Exporting %s: %s/%s (dry run)" % ( lang or 'pot', reduce_homedir(ddir), t.name))
                    continue
                self.log.info("Exporting %s: %s/%s" % ( lang or 'pot', reduce_homedir(ddir), t.name))
                #if newdir and not os.path.isdir(newdir):
                #    self.log.debug("Creating directory %s", newdir)
                #    os.makedirs(newdir)
                tarf.extract(t, ddir)
            tarf.close()
            buf.close()
        elif format == 'tgz' and out_fname:
            if dest_dir != '.' and not os.path.isabs(out_fname):
                out_fname = os.path.join(dest_dir, out_fname)
            fd = open(out_fname,'wb')
            fd.write(base64.decodestring(ret[0]['data']))
            self.log.info("Wrote exported file to %s", out_fname)
            fd.close()
        elif format == 'po':
            if dest_dir != '.' and not os.path.isabs(out_fname):
                out_fname = os.path.join(dest_dir, out_fname) #FIXME
            if just_print:
                self.log.info("Would export to %s", out_fname)
            else:
                fd = open(out_fname,'wb')
                fd.write(base64.decodestring(ret[0]['data']))
                self.log.info("Wrote exported file to %s", out_fname)
                fd.close()
        elif format == 'csv':
            if dest_dir != '.' and not os.path.isabs(out_fname):
                out_fname = os.path.join(dest_dir, out_fname)
            if just_print:
                self.log.info("Would export to %s", out_fname)
            else:
                fd = open(out_fname,'wb')
                fd.write(base64.decodestring(ret[0]['data']))
                self.log.info("Wrote exported file to %s", out_fname)
                fd.close()
        else:
            self.log.warning("Ignored exported translation in %s format", format)

        server.clear_context()
        return True

    def load_trans(self, *args):
        """Call the 'Load official translations' wizard for the languages
        """
        server.clear_context()
        server.state_dict['severity'] = 'warning'
        server.state_dict['context'] = 'i18n.load'
        
        overwrite = True
        if args:
            if args[0] == '-f':
                pass
            elif args[0] == '-N':
                overwrite = False

        # TODO all langs
        for l in args:
            if l.startswith('-'):
                raise ValueError("Syntax error in arguments")

        wiz_id = False
        ret = False
        
        # If we want to support v5, ever, we shall put the clasic wizard code here
        
        bli_obj = self.orm_proxy('base.language.install')
        for lang in args:
            self.log.info("Loading translation for %s", lang)
            server.state_dict['context'] = 'i18n.load.%s' % lang
            wiz_id = bli_obj.create({'lang': lang, 'overwrite': overwrite})
            bli_obj.lang_install([wiz_id,])
            
        server.clear_context()
        return True

    def sync_trans(self, *args):
        """Call the 'Language terms synchronize' wizard for the languages
        """
        server.clear_context()
        server.state_dict['severity'] = 'warning'
        server.state_dict['context'] = 'i18n.sync'
        
        for l in args:
            if l.startswith('-'):
                raise ValueError("Syntax error in arguments")

        wiz_id = False
        ret = False
        
        # If we want to support v5, ever, we shall put the clasic wizard code here
        
        but_obj = self.orm_proxy('base.update.translations')
        for lang in args:
            self.log.info("Syncing translation terms for %s", lang)
            server.state_dict['context'] = 'i18n.sync.%s' % lang
            wiz_id = but_obj.create({'lang': lang})
            but_obj.act_update([wiz_id,])
            
        server.clear_context()
        return True

    def import_data_file(self, *args):
        """ Import an arbitrary data file

        :*args: is a cmdline-like string of options, last of which is the
        path of the data file itself

        See _cmd_import for details.
        """

        server.clear_context()
        module = None
        ltype = None
        test_mode = False
        noupdate = False
        model = None

        while args:
            if args[0] == '-l':
                ltype = args[1]
                args = args[2:]
            elif args[0] == '-m':
                module = args[1]
                args = args[2:]
            elif args[0] == '-U':
                noupdate = True
                args = args[1:]
            elif args[0] == '-t':
                test_mode = True
                args = args[1:]
            elif args[0] == '-d':
                model = args[1]
                args = args[2:]
            else:
                break

        if len(args) < 1:
            raise ClientException("Must specify one datafile")

        server.state_dict['severity'] = 'error'
        ost_start = self.get_ostimes()

        addon_paths = [os.path.join(opt.root_path,'addons'),]
        if opt.addons_path:
             addon_paths += opt.addons_path.split(',')
        addon_paths = map(os.path.expanduser, map(str.strip, addon_paths))

        for fname in args:
            module2 = module
            ltype2 = ltype
            model2 = model

            barefile = fname # non-expanded
            datfile = os.path.abspath(os.path.expanduser(args[0]))

            if not module2:
                for adp in addon_paths:
                    if datfile.startswith(adp):
                        barefile = datfile[len(adp):]
                        if barefile[0] == os.sep:
                            barefile = barefile[1:]
                paths = barefile.split(os.sep)
                if len(paths) >= 2:
                    module2 = paths[0]

            if not ltype2:
                paths = args[0].split(os.sep)
                ext = False
                if '.' in paths[-1]:
                    ext = paths[-1].rsplit('.',1)[1].lower()
                    if ext == 'yml':
                        ext = 'yaml'
                if ext not in ('xml', 'csv', 'yaml'):
                    raise ClientException("File type cannot be determined from extension")
                ltype2 = ext

            if ltype2 == 'csv' and not model2:
                paths = args[0].split(os.sep)
                bname = paths[-1].rsplit('.',1)[0] # strip the extension from last path
                model2 = bname

            ost = self.get_ostimes()
            module_obj = self.orm_proxy('ir.module.module')
            module_ids = module_obj.search([('name','=', module2)])
            if not module_ids:
                raise ClientException("Cannot locate module %s for import!" % module2)

            if model:
                model_obj = self.orm_proxy('ir.model')
                ir_model_ids = model_obj.search([('model','=', model2)])
                if not ir_model_ids:
                    raise ClientException("Cannot locate ORM model %s for import!" % model2)

            self.log.info("Trying to import %s as %s for %s %s%s", reduce_homedir(datfile),
                        ltype2, module2, (test_mode and 'in test mode ') or '',
                        (model2 and 'model ' + model2) or '')

            if test_mode:
                server.state_dict['severity'] = 'test'
            else:
                server.state_dict['severity'] = 'warning'
            server.state_dict['context'] = '%s.import' % (module2)
            server.state_dict['module-mode'] = 'import'
            server.state_dict['module-phase'] = 'file'
            server.state_dict['module'] = module2
            server.state_dict['module-file'] = barefile

            if not os.path.isfile(fname):
                raise ClientException('File "%s" doesn\'t exist.' % fname)
            fd = open(fname, 'rb')
            data = fd.read()
            fd.close()

            bmi_obj = self.orm_proxy('base_module_record.import')
            wiz_id = bmi_obj.create( {'module_id': module_ids[0], 
                     'format': ltype2,
                     'mode': (test_mode and 'test') or 'init',
                     'model_id': (model and ir_model_ids[0]) or False,
                     'mdata': data,
                     'noupdate': noupdate
                    })
            try:
                res = bmi_obj.action_import([wiz_id,])
            except xmlrpclib.Fault, e:
                e_fc = str(e.faultCode).split('\n',1)[0]
                if e_fc in ('warning -- Assertion report',):
                    self.log.info(e.faultCode.rstrip().split('\n',1)[1].strip())
                else:
                    raise
            except RpcServerException, e:
                if e.type == 'warning' and e.code == 'Assertion report':
                    self.log.info(e.args[1])
                else:
                    raise

        ost = self.get_ostimes(ost)
        self.log.info("Data file imported at: User: %.3f, Sys: %.3f, Real: %.3f" % \
                        (ost[0], ost[1], ost[4]))

        server.clear_context()

    def gen_account_moves(self, howmany):
        """Generate a (large) number of account moves.
        
        Original by Borja López Soilán (Pexego), 2009
        
        Small OpenERP function that will create lots of account moves
        on the selected database, that can later be used for
        testing the renumber wizard.
        Note: The database must have demo data, and a fiscal year created
        """
        move_ids = []
        howmany = int(howmany)
        assert howmany > 0, "Must give a positive number"
        
        server.clear_context()
        server.state_dict['severity'] = 'warning'
        journal_obj = self.orm_proxy('account.journal')
        journal_ret = journal_obj.search([('type', '=', 'sale')])
        if not journal_ret:
            raise ClientException("Must have one journal of type 'sale' to use")
        
        journal_id = journal_ret[0]
        
        account_obj = self.orm_proxy('account.account')
        account_move_obj = self.orm_proxy('account.move')
        
        acc_1 = account_obj.search([('name', 'ilike', 'Cash')])
        acc_2 = account_obj.search([('name', 'ilike', 'Expenses')])
        if not (acc_1 and acc_2):
            raise ClientException("Must have one cash and one Expenses account")
        acc_1 = acc_1[0]
        acc_2 = acc_2[0]

        ost = self.get_ostimes()
        self.log.debug("Going to generate %d account moves", howmany)

        for i in range(1, howmany):
            amount = random.randint(1, 200000) * 0.25
            move_id = account_move_obj.create(
                    { 'ref': 'Test%s' % i,
                    'type': 'journal_voucher',
                    'journal_id': journal_id ,
                    'company_id': 1,
                    'line_id': [
                        (0, 0, {
                            #'analytic_account_id': False, 'currency_id': False,
                            # 'tax_amount': False,
                            'account_id': acc_1,
                            # 'partner_id': False, 'tax_code_id': False,
                            'credit': amount ,
                            'date_maturity': False,
                            'debit': False,
                            'amount_currency': False,
                            'ref': 'tst%4s' % i,
                            'name': 'Test_l1'
                        }),
                        (0, 0, {
                            'account_id': acc_2,
                            'debit': amount,
                            'name': 'Test_l2'})
                        ],
                        # 'period_id': 1 ?,
                        'date': '2009-01-%s' % ((i % 31) or 1),
                        'partner_id': False,
                        'to_check': 0
                    }, {})
            move_ids.append(move_id)

        ost = self.get_ostimes(ost)
        self.log.info("Moves generated at: User: %.3f, Sys: %.3f, Real: %.3f %.3f/entry" % \
                        (ost[0], ost[1], ost[4], ost[0] / howmany))
        # Validate all the moves
        account_move_obj.button_validate(move_ids, {})
        
        ost = self.get_ostimes(ost)
        self.log.info("Moves validated at: User: %.3f, Sys: %.3f, Real: %.3f" % (ost[0], ost[1], ost[4]))
        return True

class CmdPrompt(object):
    """ A command prompt for interactive use of the OpenERP server
    """

    def _complete_module_cmd(self, text, state):
        sub_cmds = ['info', 'list', 'install', 'upgrade', 'uninstall', 'refresh-list', ]
        pos = []
        first = text and text.split(' ',1)[0]
        if (not text) or first not in sub_cmds:
            for s in sub_cmds:
                if s.startswith(text or ''):
                    pos.append(s)
        elif ' ' in text:
            args = text.split(' ')
            if args[0] in ('info', 'upgrade', 'uninstall'):
                for mod in server.state_dict.get('regd-modules',[]):
                    if mod.startswith(args[-1]):
                        pos.append((' '.join(args[:-1])) + ' '+ mod)
        return pos

    def _complete_orm_cmd(self, text, state):
        if not self._orm_cache:
            self.fetch_orm_names()
        pos = []
        for obj in self._orm_cache:
            if obj.startswith(text):
                pos.append(obj)
        return pos
        
    def _complete_describe_cmd(self, text, state):
        if not self.cur_orm:
            return self._complete_orm_cmd(text, state)
        else:
            return []

    def _complete_print(self, text, state):
        pos = []
        if self._last_res:
            if 'this'.startswith(text):
                pos.append('this')
            if isinstance(self._last_res, dict):
                for k in self._last_res.keys():
                    if k.startswith(text):
                        pos.append(k)
            if (not text) and isinstance(self._last_res, (list, tuple)):
                pos.append('@')

            if text.startswith('@') and isinstance(self._last_res, (list, tuple)):
                txt2 = text[1:]
                for i in range(len(self._last_res)):
                    if txt2.startswith(str(i)):
                        pos.append('@%d' % i)

        if self._eloc:
            for k in self._eloc.keys():
                if k.startswith('_'):
                    continue
                if k.startswith(text):
                    pos.append(k)
        return pos

    def _complete_import(self, text, state):
        pos = []
        # print "complete", repr(text), state
        args = text.split(' ')
        def __complete_list(li):
            rprev = ''
            if len(args) > 1:
                rprev = ' '.join(args[:-1]) 
            if rprev and rprev[-1] != ' ':
                rprev += ' '
            for l in li:
                pos.append(rprev+ l)

        parargs = [ '-m ', '-l ', '-d ', '-U ', '-t ' ]
        filearg = ''
        if not args:
            if state == 0:
                pos += parargs
        elif args[-1].startswith('-'):
            if len(args[-1]) == 1:
                __complete_list(parargs)
            elif len(args[-1]) == 2:
                pos.append(text+' ')
            return pos
        else:
            filearg = args[-1]

        if len(args) > 1 and (args[-2].startswith('-')):
            prev = args[-2]
            if prev == '-l':
                __complete_list(['xml', 'csv', 'yaml'])
                return pos
            elif prev == '-m':
                mods = self._complete_module_cmd('upgrade '+args[-1], state)
                __complete_list([ m[8:] for m in mods])
                return pos
            elif prev == '-d':
                __complete_list(self._complete_orm_cmd(args[-1], state))
                return pos

        pos2 = []
        for path in glob.iglob(os.path.expanduser(filearg+'*')):
            if os.path.isdir(path):
                pos2.append(path + os.sep)
            else:
                pos2.append(path)
        __complete_list(pos2)

        return pos

    avail_cmds = { 0: [ 'help', 'debug', 'quit', 'db', 'console',
                        'orm', 'module', 'translation', 'server', 'test',
                        'import', 'login', 'describe' ],
                'orm': ['help', 'obj_info', 'describe',
                        'do', 'res_id',
                        'print', 'with',
                        'table',
                        'debug', 'exit',  ],
                'orm_id': [ 'help', 'do', 'print', 'describe', 'with', 'debug', 'exit', ]
                }
    cmd_levelprompts = { 0: 'BQI', 'db': 'BQI DB', 'orm': 'BQI %(cur_orm)s',
                        'orm_id': 'BQI %(cur_orm)s#%(cur_res_id)d', }
    sub_commands = { 'debug': ['on', 'off', 'server on', 'server off', 
                                'console on', 'console off', 'console silent',
                                'object on', 'object off',],
                    'db': ['load', 'list', 'create', 'drop' ],
                    'console': ['width',],
                    'module': _complete_module_cmd,
                    'orm': _complete_orm_cmd,
                    'describe': _complete_describe_cmd,
                    'do': [],
                    'table': [], # TODO
                    'print': _complete_print,
                    'with': _complete_print,
                    'import': _complete_import,
                    'help': [],
                    'server': [ 'set loglevel', 'set loggerlevel', 
                                'set pgmode',
                                'get loglevel', 'get log-levels',
                                'get info', 'get about',
                                'get login-message', 'get timezone',
                                'get options', 'get os-time', 'get http-services',
                                'get environment', 'get pgmode', 'get sqlcount',
                                'get garbage-stats',
                                'get sqlstats', 'reset sqlstats',
                                'stats', 'check',
                                #'restart',
                                ],
                    'test': ['account-moves',],
                    'translation': ['import', 'export', 'load', 'sync' ],
                    }

    help = '''
     OpenERP interactive client.

     Available Commands:
'''

    def __init__(self, client=None):
        self._client = client
        self.does_run = True
        self.__cmdlevel = 0
        self.dbname = None
        self.cur_orm = None
        self.cur_orm_obj = None
        self.cur_res_id = None
        self._orm_cache = []
        self._last_res = None
        self._eloc = {}
        self._logger = logging.getLogger('bqi.cli')
        import readline
        
        readline.set_completer(self._complete)
        readline.parse_and_bind('tab: complete')
        readline.set_completer_delims('')
        global opt
        if opt.inter_history and os.path.exists(opt.inter_history):
            readline.read_history_file(opt.inter_history)

    def finish(self):
        global opt
        import readline
        if opt.inter_history:
            readline.write_history_file(opt.inter_history)
        
    def handle(self):
        """Display the prompt and handle one command
        """

        if not self.does_run:
            return False

        server._io_flush() # before the prompt..
        try:
            cmpt = self.cmd_levelprompts[self.__cmdlevel] % self.__dict__
            cmpt += "> "
            # TODO grab console from logger.
            command_line = raw_input(cmpt)
            # print ""
            if not command_line:
                server._io_flush()
                return True

            command_elements = command_line.split()
            if not command_elements:
                return True
            command = command_elements[0]
            args = command_elements[1:]

        except EOFError:
            print ""
            self.does_run = False
            return False

        if not command:
            server._io_flush()
            return True

        if command in self.avail_cmds[self.__cmdlevel]:
            cmd = getattr(self, '_cmd_' +command)
            try:
                cmd(*args)
            except Exception, e:
                self._logger.error("Command %s failed: %s", command, e)
                self._logger.debug("Exception:", exc_info=True)
                print
            except KeyboardInterrupt:
                self._logger.warning("Cancelled")
                self.does_run = False
                return False
            server._io_flush()
        else:
            self._logger.error("Unknown command: %s", command[:10])

        if not self.does_run:
            return False
        else:
            return True


    def _complete(self, text, state):
        "Temporary debugger for completion"
        try:
            return self._complete_2(text,state)
        except Exception:
            self._logger.warning('Cannot complete:', exc_info=True)

    def _complete_2(self, text, state):
        possible = []
        for ac in self.avail_cmds.get(self.__cmdlevel,[]):
            if ac.startswith(text[:len(ac)]):
                possible.append(ac)
        
        if len(possible) == 1 and self.sub_commands.has_key(possible[0]) and \
            len(text) > len(possible[0]):
            pos = possible[0]
            possible = []
            if self.sub_commands.has_key(pos):
                txt = text[len(pos)+1:]
                scp = self.sub_commands[pos]
                if callable(scp):
                    possible = [ pos+' '+ p for p in scp(self, txt, state) ]
                else:
                    for sc in scp:
                        if sc.startswith(txt):
                            possible.append(pos + ' ' + sc)

        if state >= len(possible):
            return False
        else:
            return possible[state]

    def _cmd_debug(self, *args):
        argo = args and args[0] or 'on'
        args = args[1:]
        if argo == 'object':
            if not self.cur_orm:
                print "Command 'debug object ...' is only available at orm level!"
                return
            argo = args and args[0] or 'on'
            if self._client.series in ('pg84',):
                self._client.execute_common('root', 'set_obj_debug', self._client.dbname, self.cur_orm, (argo == 'on') and 1 or 0)
            else:
                print "Cannot change the ORM log level for %s server" % self._client.series
                return
            return
        do_server = True
        do_console = True
        do_bqi = True
        if argo == 'server':
            do_console = False
            do_bqi = False
            argo = (args and args[0]) or 'on'
        elif argo == 'console':
            do_server = False
            do_bqi = False
            argo = (args and args[0]) or 'on'

        if argo not in ('on', 'off', 'silent'):
            print 'Valid values for debug are "on", "off"!'
            return

        print "Set debug to %s" % (argo)
        
        log = logging.getLogger()
        lvl = logging.DEBUG
        if argo == 'on':
            if do_console:
                log.setLevel(logging.DEBUG)
                if console_log_handler:
                    console_log_handler.setLevel(logging.DEBUG)
            if do_server:
                self._client.execute_common('root', 'set_loglevel', 10)
        elif argo == 'off':
            if do_console and console_log_handler is not None:
                console_log_handler.setLevel(logging.INFO)
            if do_bqi:
                log.setLevel(logging.INFO)
            if do_server:
                self._client.execute_common('root', 'set_loglevel', 20)
        elif argo == 'silent':
            if console_log_handler is not None:
                console_log_handler.setLevel(logging.INFO)
            log.setLevel(logging.DEBUG)
            self._client.execute_common('root', 'set_loglevel', 10)
            
        server._io_flush()

    def _cmd_help(self, topic=None):
        """Print this help
        """
        if topic:
            for cmd in self.avail_cmds[self.__cmdlevel]:
                if topic and not cmd.startswith(topic):
                    continue
                print "Command: %s\n" % cmd
                doc = getattr(self, '_cmd_'+cmd).__doc__
                print doc
            return

        print self.help
        for cmd in self.avail_cmds[self.__cmdlevel]:
            if topic and not cmd.startswith(topic):
                continue
            doc = getattr(self, '_cmd_'+cmd).__doc__
            if doc:
                doc = doc.split('\n')[0]
                print "      " + cmd + ' '* (26 - len(cmd)) + doc
        print ""

    def _cmd_console(self, cmd=None, *args):
        global opt
        if cmd == 'width':
            if args:
                opt.console_width = int(args[0])
            print "Console width set to %d" % opt.console_width
        else:
            print "Unknown command!"

    def _cmd_quit(self):
        """Quit the interactive mode and continue bqi script
        """
        self.does_run = False

    def _cmd_db_list(self):
        """Lists the Databases accessible by the running server"""
        print "Available DBs:"
        pass #TODO


    def _cmd_db(self, *args):
        """List/Connect/Create or Drop a database
        
            Usage:
                db list
                db load
                db create
                db drop
            
            Note: at create, the demo-data and language settings come from bqi's 
                  command line
        """
        if not len(args):
            print "Usage: db {list|load|create|drop}"
            return False
        cmd = args[0]
        args = args[1:]
        try:
            if cmd == 'list':
                dbs = self._client.list_db()
                print "Available dbs:", ', '.join(dbs)
            elif cmd == 'load':
                uid = self._client._login()
                #self.dbname = dbname
                #self.__cmdlevel = 'db'
            elif cmd == 'create':
                self._client.create_db()
            elif cmd == 'drop':
                self._client.drop_db()
        except xmlrpclib.Fault, e:
            print 'xmlrpc exception: %s' % reduce_homedir( e.faultCode.strip())
            print 'xmlrpc +: %s' % reduce_homedir(e.faultString.rstrip())
            return
        except RpcException:
            print "Failed %s database:" % cmd
            return
        except Exception, e:
            print "Failed %s database:" % cmd, e
            return

    def _cmd_info(self):
        """Get info about server, database, or orm object
        """
        if not self.dbname:
            print "Currently NOT at database"
            return
        
        pass # TODO

    def _cmd_server(self, *args):
        """Server-level operations or info
        
        This command has several sub-commands:
            set loglevel <num|name>      Set the logging level. Name may only be supported
                                         at certain server versions
            set loggerlevel <logger> <num|name>  Set lever for some logger
            check                        Perform the "check connectivity" test
            stats                        Query the server for statistics info.
            get ...                  Retrieve certain server settings ...
        """
        #    restart                     Attempt to restart the server.

        if not args:
            print "You must supply a sub-command to 'server'"
            return
        try:
            if args[0] == 'set':
                if args[1] == 'loglevel':
                    self._client.execute_common('root', 'set_loglevel', args[2])
                elif args[1] == 'loggerlevel':
                    self._client.execute_common('root', 'set_loglevel', args[3], args[2])
                elif args[1] == 'pgmode':
                    self._client.execute_common('root', 'set_pgmode', args[2])
                else:
                    print "Wrong command"
                    return
            elif args[0] == 'get':
                res = None
                if args[1] == 'loglevel':
                    if self._client.series == 'pg84':
                        ret = self._client.execute_common('root', 'get_loglevel', *args[2:])
                    else:
                        ret = self._client.execute_common('root', 'get_loglevel')
                #elif args[1] == 'info':
                #    ret = self._client.execute_common('root', '')
                elif args[1] == 'about':
                    ret = self._client.execute_common('pub', 'about')
                elif args[1] == 'login-message':
                    ret = self._client.execute_common('pub', 'login_message')
                elif args[1] == 'timezone':
                    ret = self._client.execute_common('pub', 'timezone_get')
                elif args[1] == 'options':
                    ret = self._client.execute_common('pub', 'get_options')
                elif args[1] == 'environment':
                    ret = self._client.execute_common('pub', 'get_server_environment')
                elif args[1] == 'os-time':
                    ret = self._client.execute_common('root', 'get_os_time')
                elif args[1] == 'http-services':
                    ret = self._client.execute_common('pub', 'list_http_services')
                elif args[1] == 'pgmode':
                    ret = self._client.execute_common('root', 'get_pgmode')
                elif args[1] == 'sqlcount':
                    ret = self._client.execute_common('root', 'get_sqlcount')
                elif args[1] == 'garbage-stats':
                    ret = self._client.execute_common('root', 'get_garbage_stats')
                elif args[1] == 'sqlstats':
                    ret = self._client.execute_common('root', 'get_sql_stats')
                    print_sql_stats(ret)
                    ret = 'OK'
                elif args[1] == 'log-levels':
                    if self._client.series == 'pg84':
                        ret = self._client.execute_common('root', 'get_loglevel', '*')
                    else:
                        print "Command not supported for %s server series" % self._client.server_series
                else:
                    print "Wrong command"
                    return
                if isinstance(ret, basestring):
                    print "Result:"
                    print ret
                else:
                    print "Result:\n", pretty_repr(ret)
            elif args[0] == 'stats':
                ret = self._client.execute_common('pub', 'get_stats')
                print ret
            #elif args[0] == 'restart':
            #   pass # Non-trivial TODO
            elif args[0] == 'check':
                ret = self._client.execute_common('pub', 'check_connectivity')
            elif args[0] == 'reset' and args[1] == 'sqlstats':
                ret = self._client.execute_common('root', 'reset_sql_stats')
            else:
                print "Unknown sub-command: server %s" % args[0]
                return
        # Exceptions are handled locally in the command.
        except ClientException, e:
            logger.error(reduce_homedir("%s" % e))
            server.dump_blame(e)
            ret = False
        except xmlrpclib.Fault, e:
            e_fc = str(e.faultCode)
            logger.error('xmlrpc exception: %s', reduce_homedir(e_fc.strip()))
            logger.error('xmlrpc +: %s', reduce_homedir(e.faultString.rstrip()))
            server.dump_blame(e)
            ret = False
        except RpcException, e:
            server.dump_blame(e)
            ret = False
        except Exception, e:
            logger.exception('exc at %s:', ' '.join(args))
            server.dump_blame(e)
            ret = False

    def _cmd_set(self):
        """Get info about server, database, or orm object
        """

    def _cmd_exit(self):
        """Exit to upper command level """
        if self.__cmdlevel == 'orm_id':
            self.cur_res_id = None
            self.__cmdlevel = 'orm'
        elif self.__cmdlevel == 'foobar':
            self.__cmdlevel = 'foo'
        else:
            self.__cmdlevel = 0
            self.cur_res_id = None
            self.cur_orm = None
            self.cur_orm_obj = None
            self.dbname = None
            self._eloc = {}
        self._last_res = None

    def _cmd_module(self, cmd, *args):
        """Perform operations on modules
        
        Available ones are:
            info <mod>...         Get module information
            list                  List installed modules
            install <mod> ...     Install module(s)
            upgrade <mod> ...     Upgrade module(s)
            uninstall <mod> ...   Remove module(s)
        """
        if cmd not in ('refresh-list', 'list') and not args:
            print 'Must supply some modules!'
            return
        try:
            imm_obj = self._client.orm_proxy('ir.module.module')
            if cmd == 'info':
                inst_mods = imm_obj.search([('name','in', args)])
                if not inst_mods:
                    print "No modules with these names found!"
                    return
                for mod in imm_obj.read(inst_mods):
                    print_lexicon(mod, title="\nModule %s" % mod['name'], sort_fn=self._col_sorted)
            elif cmd == 'list':
                inst_mods = imm_obj.search([('state','=', 'installed')])
                if not inst_mods:
                    print "No modules installed! ??"
                else:
                    res = imm_obj.read(inst_mods, ['name', 'shortdesc'])
                    print "Installed modules:"
                    print_table(res, ['id', 'name', 'shortdesc'])
            elif cmd == 'install':
                self._client.install_module(args)
            elif cmd == 'upgrade':
                self._client.upgrade_module(args)
            elif cmd == 'uninstall':
                self._client.uninstall_module(args)
            elif cmd == 'refresh-list':
                self._client.update_modules_list()
            else:
                print "Unknown command: module %s" % cmd
        except xmlrpclib.Fault, e:
            print 'xmlrpc exception: %s' % reduce_homedir( e.faultCode.strip())
            print 'xmlrpc +: %s' % reduce_homedir(e.faultString.rstrip())
            return
        except RpcException:
            print "Failed module %s:" % cmd
            return
        except Exception, e:
            print "Failed module %s:" % cmd, e
            return

    def fetch_orm_names(self):
        try:
            self._orm_cache = self._client.get_orm_names()
        except Exception, e:
            print "exc:", e

    def _cmd_orm(self, model, res_id=None):
        """Select the ORM model to operate upon
        
            An extra argument of the resource id can be supplied, too.
        """
        if not model:
            print "Must select one orm model!"
            return
        try:
            self._client.get_orm_keys(model)
            orm_obj = self._client.orm_proxy(model)
        except xmlrpclib.Fault:
            print "Wrong ORM model!"
            return
        except RpcException, e:
            print "%s: %s" % e.args
            return
        if res_id:
            try:
                res_id = int(res_id)
            except ValueError:
                print "id of orm must be integer!"
                return
            try:
                orm_obj.read([res_id,], ['id',])
            except (xmlrpclib.Fault, RpcException):
                print "Record not found!"
                return
            self.cur_res_id = res_id
            self.__cmdlevel = 'orm_id'
        else:
            self.__cmdlevel = 'orm'
        self.cur_orm = model
        self.cur_orm_obj = orm_obj

    def _cmd_res_id(self, res_id):
        """Select a single resource of an ORM model
        """
        if not self.cur_orm:
            print "Must specify a model first!"
            return
        try:
            res_id = int(res_id)
        except ValueError:
            print "id of orm must be integer!"
            return
        try:
            self.cur_orm_obj('read', [res_id,], ['id',])
        except (xmlrpclib.Fault, RpcException):
            # TODO: fine-grain
            print "Record not found!"
            return
        self.cur_res_id = res_id
        self.__cmdlevel = 'orm_id'
        
    def _cmd_do(self, *args):
        """Perform an ORM operation on an object.
        
            Please specify a pythonic expression like "read(['name',])"
            If you are on a single resource, this will be added as a first
            list argument. Otherwise, you will need to specify the ids, too.
        """
        if not self.cur_orm:
            print "Must be at an ORM level!"
            return
        assert self.cur_orm_obj
        astr = ' '.join(args)
        if not '(' in astr:
            print "Syntax: foobar(...)"
            return
        try:
            astr = astr.strip()
            afn, aexpr = astr.split('(',1)
            aexpr = '(' + aexpr
            aexpr = eval(aexpr, {'this': self._last_res}, {})
        except Exception, e:
            print 'Tried to eval "%s"' % aexpr
            print "Exception:", e
            return
        if not isinstance(aexpr, tuple):
            aexpr = (aexpr,)
        if self.cur_res_id:
            aexpr = ( [self.cur_res_id,],) + aexpr
        try:
            logger.debug("Trying orm execute: %s(%s)", afn, ', '.join(map(repr,aexpr)))
            res = getattr(self.cur_orm_obj, afn)(*aexpr)
            server._io_flush()
        except xmlrpclib.Fault, e:
            if isinstance(e.faultCode, (int, long)):
                e.faultCode = str(e.faultCode)
            print 'xmlrpc exception: %s' % reduce_homedir(e.faultCode.strip())
            print 'xmlrpc +: %s' % reduce_homedir(e.faultString.rstrip())
            return
        except RpcException, e:
            return
        except Exception, e:
            print "Failed orm execute:", e
            self._logger.debug("Failed %s():", afn, exc_info=True)
            return

        toprint = repr(res)
        if len(toprint) < 128:
            print "Res:", toprint
        else:
            print "Res is a %s. Use the print cmd to inspect it." % type(res)
        self._last_res = res

    def _col_sorted(self, tups):
        """ Sort a list of (fieldname, value) tuples

        This is a special sort, because it considers some builtin columns
        and some frequently used ones will be sorted first
        """

        coldict = { 'id': 0, '__vptr': 5,
                'create_uid': 10, 'create_date': 11,
                'write_uid': 20, 'write_date': 21,
                'xmlid': 30,
                'name': 40, 'date': 42, 'state': 42, 'description': 43,
                'user_id': 44, 'company_id': 45
                }
        return sorted(tups, key=lambda x: coldict.get(x[0], x[0]))

    def _cmd_describe(self, *args):
        """ Describe an ORM model, its fields [and properties]

            Can be called either within the ORM, or like 'describe orm.model' from
            the root level.
        """
        model = None
        if self.cur_orm:
            model = self.cur_orm
            obj = self.cur_orm_obj
        elif args:
            model = args[0]
            obj = self._client.orm_proxy(model)
        else:
            print "ORM model must be specified!"
            return

        assert obj
        logger.debug("Trying %s.fields_get()", model)
        res = obj.fields_get()
        server._io_flush()

        # Form the table
        rows = []
        help_flds = {}
        selection_flds = {}
        for field, props in self._col_sorted(res.items()):
            crow = {'Field': field, 'String': props.pop('string'), 
                    'Type': props.pop('type')}
            rest = []
            if 'size' in props:
                crow['Type'] += '(%s)' % props.pop('size')
            elif crow['Type'] == 'float' and 'digits' in props:
                crow['Type'] += '(%s,%s)' % tuple(props.pop('digits'))
            if 'function' in props:
                props.pop('function')
                crow['Type'] = 'fn:' + crow['Type']
            if crow['Type'] in ('one2one', 'one2many', 'many2one', 'many2many') \
                    and 'relation' in props:
                crow['Type'] += '(%s)' % props.pop('relation')

            if 'help' in props:
                help_flds[field] = props.pop('help')

            if 'selection' in props:
                sels = dict(props.pop('selection'))
                rest.append('selection=(%s)' % (', ').join(sels.keys()))
                selection_flds[field] = sels

            for attr in ('required', 'readonly', 'select', 'selectable', 'translate', 'view_load'):
                if attr in props:
                    if props.pop(attr):
                        rest.append(attr)
            for k, v in props.items():
                # rest of them
                if not v:
                    continue
                rest.append('%s: %r' % (k, v))

            crow['Modifiers'] = '\n'.join(rest)
            rows.append(crow)

        print_centered('Model: "%s"' % model)
        print_table(rows, ['Field', 'String', 'Type', 'Modifiers'], max_width=True)
        print
        if selection_flds:
            print "Selection fields:"
            for field, sels in self._col_sorted(selection_flds.items()):
                print_lexicon(sels, title="  for %s:" % field, indent=6)
            print
        if help_flds:
            print_lexicon(help_flds, title="Help Strings:", sort_fn=self._col_sorted)
            print
        return

    def _eval_local(self, aexpr):
        # put persistent at locals, this etc. in globals
        loc = self._eloc
        glo = {}
        has_at = False
        if isinstance(self._last_res, dict):
            glo.update(self._last_res)
        glo['this'] = self._last_res
        aexpr = aexpr.strip()
        if aexpr.startswith('@'):
            has_at = True
            aexpr = aexpr[1:]
        if not aexpr:
            # like "@" alone
            return list(self._last_res)

        try:
            res = eval(aexpr, loc, glo)
        except Exception, e:
            print "Exception:", e
            return
        if has_at:
            try:
                res = self._last_res[res]
            except Exception, e:
                print "Exception this[@]:", e
                return
        return res

    def _cmd_print(self, *args):
        """Print any part of the last result.
        
        For every orm "do" command or so, the last result is stored in a
        register, namely 'this'. Write a pythonic expression to inspect
        this, like:
            print len(this)
            print this[4]['foobar']
        """
        if not args:
            # yes, an empty line ;)
            print
            return
        aexpr = ' '.join(args)
        res = self._eval_local(aexpr)
        print "Result:"
        print pretty_repr(res)
        
    def _cmd_with(self, *args):
        """Narrow the last result
        
        When the last result is a complex expression, it makes sense sometimes
        to "dive" into it and inspect a specific part:
            print len(this)
            print this[3]
            with this[3]
            print this['foobar']
        """
        if not args:
            return
        aexpr = ' '.join(args)
        res = self._eval_local(aexpr)
        toprint = repr(res)
        if len(toprint) < 60:
            print "With this:", toprint
        if res is not None:
            self._last_res = res

    def _cmd_table(self, *args):
        """Perform an ORM operation and present results as a table
        
           Syntax of this command resembles the SQL select command:
              > table name, address, active from this
              > table name, address, active from read([1,2,3])
        """
        if not self.cur_orm:
            print "Must be at an ORM level!"
            return
        
        cols_str = ''
        while args:
            if args[0] == 'from':
                break
            cols_str += ' ' + args[0]
            args = args[1:]

        if not args:
            print "Syntax error, expected 'from' clause (lowercase)"
        if args[0] != 'from':
            print "Syntax error, expected 'from' clause."
        
        args = args[1:]
        # we're just after the "from" clause
        
        if not '(' in args[0]:
            # it is a local expression, like "this"
            aexpr = ' '.join(args)
            res = self._eval_local(aexpr)
        else:
            astr = ' '.join(args)
            if not '(' in astr:
                print "Syntax: foobar(...)"
                return
            try:
                astr = astr.strip()
                afn, aexpr = astr.split('(',1)
                aexpr = '(' + aexpr
                aexpr = eval(aexpr, {'this': self._last_res}, {})
            except Exception, e:
                print 'Tried to eval "%s"' % aexpr
                print "Exception:", e
                return
            if not isinstance(aexpr, tuple):
                aexpr = (aexpr,)
            if self.cur_res_id:
                aexpr = ( [self.cur_res_id,],) + aexpr
            try:
                logger.debug("Trying orm execute: %s(%s)", afn, ', '.join(map(repr,aexpr)))
                res = getattr(self.cur_orm_obj, afn)(*aexpr)
                server._io_flush()
            except xmlrpclib.Fault, e:
                if isinstance(e.faultCode, (int, long)):
                    e.faultCode = str(e.faultCode)
                print 'xmlrpc exception: %s' % reduce_homedir( e.faultCode.strip())
                print 'xmlrpc +: %s' % reduce_homedir(e.faultString.rstrip())
                return
            except RpcException:
                return
            except Exception, e:
                print "Failed orm execute:", e
                return
        if not res:
            print "No result!"
            return

        cols = map(str.strip, cols_str.split(','))
        if cols == ['*',]:
            cols = None
        print_table(res, columns=cols)
        return

    def _cmd_obj_info(self):
        """Obtain model info
        """
        
        if not self.cur_orm:
            print "Must be at an ORM level!"
            return
        # TODO
        print "Currently at: %s" % self.cur_orm

    def _cmd_translation(self, *args):
        """import, export or load translations
        
        Available modes:
            import  -f <file> [-l lang-code] [-L lang-name]
            export [-l <lang>] [-o file| --sourcedirs] [--all | <modules> ...]
            load [-f|-N] <lang>
            sync <lang>
        """
        if (not args) or (args[0] not in ('import', 'export', 'load', 'sync')):
            print "One of import|export|load|sync must be specified"
            return
        
        cmd = args[0]
        args = args[1:]
        try:
            # we directly call the client methods, because their argument
            # syntax should be identical between cmdline and interactive.
            if cmd == 'import':
                self._client.import_trans(*args)
            elif cmd == 'export':
                self._client.export_trans(*args)
            elif cmd == 'load':
                self._client.load_trans(*args)
            elif cmd == 'sync':
                self._client.sync_trans(*args)
        except xmlrpclib.Fault, e:
            if isinstance(e.faultCode, (int, long)):
                e.faultCode = str(e.faultCode)
            print 'xmlrpc exception: %s' % reduce_homedir( e.faultCode.strip())
            print 'xmlrpc +: %s' % reduce_homedir(e.faultString.rstrip())
            return
        except RpcException:
            return
        except Exception, e:
            print "Failed translate:", e
            return

    def _cmd_test(self, cmd, *args):
        """Perform some predefined test
        
        Available ones are:
            account-moves <N>           Generate N account moves
        """
        try:
            if cmd == 'account-moves':
                self._client.gen_account_moves(args[0])
            else:
                print "Unknown sub-command: test %s" % cmd
        except xmlrpclib.Fault, e:
            if isinstance(e.faultCode, (int, long)):
                e.faultCode = str(e.faultCode)
            print 'xmlrpc exception: %s' % reduce_homedir( e.faultCode.strip())
            print 'xmlrpc +: %s' % reduce_homedir(e.faultString.rstrip())
            return
        except RpcException:
            print "Failed test %s:" % cmd
            return
        except Exception, e:
            print "Failed test %s:" % cmd, e
            return

    def _cmd_import(self, *args):
        """Import a data file, through the base_module_import wizard.

    Usage:
        import [-m <module>] [-l {xml|csv|yaml}] [-t] [-U]
                [-d <model>]  data-file.ext

    Arguments:
        -m <module> Module to import against, either detected from the
                    path name, or explicitly specified here.
        -l          Type of import file. Can be auto-detected from data
                    file extension
        -t          Test data mode. Otherwize "initial data" mode.
        -U          No Update. Activate that flag for the data
        -d <model>  The model to import against. Needed for csv files,
                    unless the filename matches (eg. 'ir.model.access.csv')
        """
        if (not args):
            print "At least the filename is required"
            return
        try:
            self._client.import_data_file(*args)
        except xmlrpclib.Fault, e:
            if isinstance(e.faultCode, (int, long)):
                e.faultCode = str(e.faultCode)
            print 'xmlrpc exception: %s' % reduce_homedir( e.faultCode.strip())
            print 'xmlrpc +: %s' % reduce_homedir(e.faultString.rstrip())
            return
        except RpcException, e:
            print "Failed import"
            return
        except Exception, e:
            print "Failed import:", e
            return

    def _cmd_login(self, login, passwd):
        """Login as (a different) user

    Usage:
        login <user> <password>

    Notes:
        This command will attempt to login <user> in the running server
        and use that instead of the previous login. All subsequent RPC
        calls will be executed as that user (hopefully).
        """
        
        self._client._login(login, passwd)

usage = """%prog command [options]

Basic Commands:
    start-server                Start Server
    create-db                   Create new database
    drop-db                     Drop database
    install-module [<m> ...]    Install module
    upgrade-module [<m> ...]    Upgrade module
    import [args] <data-file>   Import data file directly into module
    check-quality  [<m> ...]    Calculate quality and dump quality result 
                                [ into quality_log.pck using pickle ]
    fields-view-get             Check fields_view_get of all pooler objects
    multi <cmd> [<cmd> ...]     Execute several of the above commands, at a 
                                single server instance.
    keep[-running]              Pause and keep the server running, waiting for Ctrl+C
    inter[active]               Display interactive b-q-i prompt
    login <user> <passwd>       Login again, switch user
    
    translation-import -f <file> [-l lang-code] [-L lang-name]
                                Import file as translation for language
    translation-export [-l <lang>] [-o file| --sourcedirs] [--all | <modules> ...]
                                Export translations
    translation-load [-f|-N] <lang>
                                Load translations from addons dirs
    translation-sync <lang>     Sync trnslations from database

    get-sqlcount                Retrieve and print the SQL counter
"""

parser = optparse.OptionParser(usage)
parser.add_option("-R", "--remote", action="store_true", default=False,
                    help="Remote mode. Connect to running OpenERP server, rather than launching one"),
parser.add_option("-H", "--url", default=False,
                    help="URL of remote server to connect to"),
parser.add_option("-m", "--modules", dest="modules", action="append",
                     help="specify modules to install or check quality")
parser.add_option("--addons-path", dest="addons_path", help="specify the addons path")
parser.add_option("--all-modules", dest="all_modules", action='store_true', default=False,
                    help="Operate on all modules that are found on addons-path")
parser.add_option("--black-modules", dest="black_modules", default=None,
                    help="Exclude these modules from all-modules scan (space-separated)")
parser.add_option("--homedir", dest="homedir", default=None, 
                help="The directory, whose absolute path will be stripped from messages.")
parser.add_option("--xml-log", dest="xml_log", help="A file to write xml-formatted log to")
parser.add_option("--txt-log", dest="txt_log", help="A file to write plain log to, or 'stderr'")
parser.add_option("--machine-log", dest="mach_log", help="A file to write machine log stream, or 'stderr'")
parser.add_option("--max-logs", dest="max_logs", help="Backup that many logs of previous runs")
parser.add_option("--debug", dest="debug", action='store_true', default=False,
                    help="Enable debugging of both the script and the server")
parser.add_option("--debug-server", dest="debug_server", action='store_true', default=False,
                    help="Enable debugging of the server alone")
parser.add_option("--debug-bqi", dest="debug_bqi", action='store_true', default=False,
                    help="Enable debugging of this script alone")
parser.add_option("--debug-sql", dest="debug_sql", action='store_true', default=False,
                    help="Set the debugging level of the server to sql, for performance tests")

parser.add_option("-D", "--define", dest="defines", action="append",
                    help="Define configuration values for server, (pg84 only)")
parser.add_option("-P", "--pyarg", dest="pyargs", action="append",
                    help="Pass this argument to python interpreter")
parser.add_option("--profiled", dest="profiled", action='store_true', default=False,
                    help="Run the server session through a profiler")

parser.add_option("-W", dest="warnings", default=False,
                    help="Pass this flag to python, so that warnings are considered")

parser.add_option("--quality-logs", dest="quality_logs", help="specify the path of quality logs files which has to stores")
parser.add_option("--root-path", dest="root_path", help="specify the root path")
parser.add_option("--http-interface", dest="http_interface", help="Specify the http interface to listen on, by default is localhost (only).")
parser.add_option("-p", "--port", dest="port", help="specify the TCP port", type="int")
parser.add_option("--net_port", dest="netport",help="specify the TCP port for netrpc")
parser.add_option("-d", "--database", dest="db_name", help="specify the database name")
parser.add_option("--login", dest="login", help="specify the User Login")
parser.add_option("--password", dest="pwd", help="specify the User Password")
parser.add_option("--super-passwd", dest="super_passwd", help="The db admin password")
parser.add_option("--config", dest="config", help="Pass on this config file to the server")
parser.add_option("--ftp-port", dest="ftp_port", help="Choose the port to set the ftp server at")
parser.add_option("--smtp-maildir", dest="smtp_maildir", help="Maildir to use instead of SMTP server, for test mails")

parser.add_option("--no-demo", dest="no_demo", action="store_true", default=False,
                    help="Do not install demo data for modules installed")

parser.add_option("--language", dest="lang", help="Use that language as default for the new db")
parser.add_option("--translate-in", dest="translate_in",
                     help="specify .po files to import translation terms")
parser.add_option("--server-series", help="Specify argument syntax and options of the server.\nExamples: 'v600', 'pg84', 'srv-lib'")

parser.add_option("--color", dest="console_color", action='store_true', default=False,
                    help="Use color at stdout/stderr logs")
parser.add_option("--console-width", dest="console_width", type="int", default=100,
                    help="Width of console, for formatting")

parser.add_option("--console-nodebug", dest="console_nodebug", action='store_true', default=False,
                    help="Hide debug messages from console, send them to file log only.")

parser.add_option("-n", "--dry-run", dest="dry_run", action='store_true', default=False,
                    help="Don't start the server, just print the commands.")

parser.add_option("--inter-history", dest="inter_history",
                    help="Interactive history file")

pgroup = optparse.OptionGroup(parser, 'Config-File options',
                " These options help run this script with pre-configured settings.")

pgroup.add_option("-c", dest="conffile", 
            help="Read configuration options for this script from file. " 
            "Defaults to ~/.openerp-bqirc" )
pgroup.add_option("--no-bqirc", dest="have_bqirc", action="store_false", default=True,
            help="Do not read ~/.openerp-bqirc , start with empty options.")
pgroup.add_option("-s", dest="bqirc_section", action="append",
            help="Section of the config file which should be followed, like a script")

parser.add_option_group(pgroup)

(copt, args2) = parser.parse_args()

def die(cond, msg):
    if cond:
        print msg
        sys.exit(1)

args = []
# Now, parse the config files, if any:

opt = optparse.Values(copt.__dict__)

config_stray_opts = []
def parse_option_section(conf, items, allow_include=True):
    global opt, copt, args
    global config_stray_opts
    nonopts = ('conffile', 'have_bqirc', 'bqirc_section', 'include')
    default_section = None
    for key, val in items:
        if key == 'include' and allow_include:
            for inc in val.split(' '):
                parse_option_section(conf, conf.items(inc), allow_include=(allow_include-1))

    for key, val in items:
        if key in nonopts:
            continue
        elif key == 'default_section':
            default_section = val
        elif key == 'color_section':
            parse_color_section(config, val)
        elif key == 'commands':
            args += val.split(' ')
        elif key in dir(copt):
            if isinstance(getattr(copt, key), list) or \
                    (key in ('modules',)):
                val = val.split(' ')
            elif isinstance(getattr(copt, key), bool):
                val = bool(val.lower() in ('1', 'true', 't', 'yes'))
            elif key in ('addons_path', 'root_path', 'homedir',
                        'xml_log', 'txt_log', 'mach_log', 'inter_history', 
                        'smtp_maildir'):
                val = os.path.expanduser(val)
            if not getattr(copt, key):
                setattr(opt, key, val)
        else:
            config_stray_opts.append((key, val))
            pass

    return default_section

def parse_color_section(conf, sname):
    """Parse the config section sname for colors configuration
    """
    pass

if opt.have_bqirc:
    cfile = os.path.expanduser(copt.conffile or '~/.openerp-bqirc')
    config = SafeConfigParser()
    conf_filesread = config.read([cfile,])
    try:
        default_section = parse_option_section(config, config.items('general'), 5)
    except NoSectionError:
        default_section = []
        pass

    if copt.bqirc_section:
        default_section = copt.bqirc_section
    elif default_section:
        default_section = default_section.split(' ')
    else:
        default_section = []

    if default_section:
        for ds in default_section:
            parse_option_section(config, config.items(ds), 5)

def mkpasswd(nlen):
    ret = ''
    rnd = random.SystemRandom()
    crange = string.ascii_letters + string.digits + '_-.'
    for c in range(nlen):
        ret += rnd.choice(crange)
    return ret

if opt.pwd is None:
    opt.pwd = 'admin'
elif opt.pwd and opt.pwd == "@":
    opt.pwd = mkpasswd(8)

if opt.super_passwd is None:
    opt.super_passwd = 'admin'
elif opt.super_passwd and opt.super_passwd == "@":
    opt.super_passwd = mkpasswd(10)

args += args2

options = {
    'addons-path' : opt.addons_path or False,
    'quality-logs' : opt.quality_logs or '',
    'root-path' : opt.root_path or '',
    'translate-in': [],
    'port' : int(opt.port or 8069),
    'lang': opt.lang or 'en_US',
    'netport': (opt.netport and int(opt.netport)) or False,
    'dbname': opt.db_name ,
    'modules' : opt.modules,
    'login' : opt.login or 'admin',
    'pwd' : opt.pwd,
    'super_passwd': opt.super_passwd,
    'config': opt.config,
    'server_series': opt.server_series or 'v600',
    'homedir': '~/'
}

if opt.homedir:
    options['homedir'] = os.path.abspath(opt.homedir)
    if options['homedir'] and options['homedir'][-1] != '/':
        options['homedir'] += '/'

def reduce_homedir(ste):
    global opt
    return ste.replace(options['homedir'], '~/')

console_log_handler = None
def init_log():
    global opt
    global console_log_handler
    log = logging.getLogger()
    if opt.debug or opt.debug_bqi:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)
    max_logs = int(opt.max_logs or 10)

    if not (opt.xml_log or opt.txt_log or opt.mach_log):
        # Default to a txt logger
        opt.txt_log = 'stderr'

    if opt.xml_log:
        hnd = XMLStreamHandler(opt.xml_log)
        log.addHandler(hnd)
        
    if opt.txt_log:
        if opt.txt_log == 'stderr':
            seh = logging.StreamHandler()
            log.addHandler(seh)
            console_log_handler = seh
            if opt.console_nodebug:
                seh.setLevel(logging.INFO)
            if opt.console_color:
                seh.setFormatter(ColoredFormatter())
        elif opt.txt_log == 'stdout':
            soh = logging.StreamHandler(sys.stdout)
            console_log_handler = soh
            log.addHandler(soh)
            if opt.console_nodebug:
                soh.setLevel(logging.INFO)
            if opt.console_color:
                soh.setFormatter(ColoredFormatter())
        else:
            fh = logging.handlers.RotatingFileHandler(opt.txt_log, backupCount=max_logs)
            log.addHandler(fh)
            if os.path.exists(opt.txt_log):
                fh.doRollover()
            #hnd2.setFormatter()

    if opt.mach_log:
        if opt.mach_log == 'stdout':
            if console_log_handler is not None:
                raise Exception("Cannot have two loggers at stdout!")
            hnd3 = logging.StreamHandler(sys.stdout)
            console_log_handler = hnd3
        else:
            hnd3 = logging.handlers.RotatingFileHandler(opt.mach_log, backupCount=max_logs)
            if os.path.exists(opt.mach_log):
                hnd3.doRollover()
        hnd3.setFormatter(MachineFormatter())
        log.addHandler(hnd3)

init_log()

logger = logging.getLogger('bqi')

if opt.have_bqirc and conf_filesread:
    for r in conf_filesread:
        logger.info("Read config from %s" % r)
    for cso in config_stray_opts:
        logger.warning("Stray option in config: %s = %s", cso[0], cso[1])

def parse_cmdargs(args):
    """Parse the non-option arguments into an array of commands
    
    The array has entries like ('cmd', [args...])
    Multiple commands may be specified either with the 'multi'
    command or with the '--' separator from the last cmd.
    """
    global parser
    ret = []
    while len(args):
        command = args[0]
        if command == '--':
            args = args[1:]
            continue

        if command[0] in ('-', '+'): # TODO
            cmd2 = command[1:]
        else:
            cmd2 = command

        if cmd2 not in ('start-server','create-db','drop-db',
                    'install-module','upgrade-module','check-quality',
                    'install-translation', 'multi', 'fields-view-get',
                    'translation-import', 'translation-export',
                    'translation-load', 'translation-sync',
                    'get-sqlcount', 'import', 'login',
                    'keep', 'keep-running', 'inter', 'interactive'):
            parser.error("incorrect command: %s" % command)
            return
        args = args[1:]
        if command == '--':
            continue
        elif cmd2 == 'multi':
            ret.extend([(x, []) for x in args])
            return ret
        elif cmd2 in ('install-module', 'upgrade-module', 'check-quality',
                        'translation-import', 'translation-export',
                        'translation-load', 'translation-sync',
                        'install-translation', 'import', 'login'):
            # Commands that take args
            cmd_args = []
            while args and args[0] != '--':
                cmd_args.append(args[0])
                args = args[1:]
            ret.append((command, cmd_args))
        else:
            ret.append((command, []))
        
    return ret

cmdargs = parse_cmdargs(args)
if len(cmdargs) < 1:
    parser.error("You have to specify a command!")

die(opt.translate_in and (not opt.db_name),
        "the translate-in option cannot be used without the database (-d) option")

# Hint:i18n-import=purchase:ar_AR.po+sale:fr_FR.po,nl_BE.po
if opt.translate_in:
    translate = opt.translate_in
    for module_name,po_files in map(lambda x:tuple(x.split(':')),translate.split('+')):
        for po_file in po_files.split(','):
            if module_name == 'base':
                po_link = '%saddons/%s/i18n/%s'%(options['root-path'],module_name,po_file)
            else:
                po_link = '%s/%s/i18n/%s'%(options['addons-path'], module_name, po_file)
            options['translate-in'].append(po_link)

if (not opt.http_interface) or (opt.http_interface == '0.0.0.0'):
    uri = 'http://localhost:' + str(options['port'])
else:
    uri = 'http://%s:%s' % ( opt.http_interface, str(options['port']))

def get_modules2(ad_paths):
    """Returns the list of module (path, name)s
    """
    def listmods(adir):
        def clean(name):
            name = os.path.basename(name)
            if name[-4:] == '.zip':
                name = name[:-4]
            return (adir, name)

        def is_really_module(name):
            if name.startswith('.'):
                return False
            name = os.path.join(adir, name)
            return os.path.isdir(name) or zipfile.is_zipfile(name)
        return map(clean, filter(is_really_module, os.listdir(adir)))

    plist = []
    for ad in ad_paths:
        plist.extend(listmods(ad))
    return list(set(plist))


def load_mod_info(mdir, module):
    """
    :param module: The name of the module (sale, purchase, ...)
    """
    for filename in ['__openerp__.py', '__terp__.py']:
        description_file = os.path.join(mdir, module, filename)
        # Broken for zip modules.
        if description_file and os.path.isfile(description_file):
            return eval(open(description_file,'rb').read())

    return {}

connect_dsn =  {'user': options['login'], 
            'passwd': options['pwd'], 
            'superpass': options['super_passwd'],
            'dbname': options['dbname'],
            }

def parse_url_dsn(url):
    import urlparse
    global connect_dsn
    netloc_re = re.compile( r'(?:(?P<user>[^:@]+?)(?:\:(?P<pass>[^@]*?))?@)?'
        r'(?P<host>(?:[\w\-\.]+)|(?:\[[0-9a-fA-F:]+\]))'
        r'(?:\:(?P<port>[0-9]{1,5}))?$')
    uparts = urlparse.urlparse(url, allow_fragments=False)
    
    if uparts.scheme:
        connect_dsn['proto'] = uparts.scheme
    if uparts.netloc:
        um = netloc_re.match(uparts.netloc)
        if not um:
            raise ValueError("Cannot decode net locator: %s" % uparts.netloc)
        for k, v in um.groupdict().items():
            if v is not None:
                connect_dsn[k] = v
    if uparts.query:
        pass
    # path, params, fragment

parse_url_dsn(uri)

if opt.url:
    parse_url_dsn(opt.url)
    try:
        from openerp_libclient import protocols
        __hush_pyflakes = [protocols,]
        from openerp_libclient import session as libclient_session
        client_session = libclient_session.Session
        client_kwargs = {'notifier': libclient_session.FilterNotifier() }
        client_kwargs['notifier']._filter_fn = reduce_homedir
        del RpcException
        del RpcServerException
        from openerp_libclient.errors import RpcException, RpcServerException
    except ImportError:
        raise ImportError("openerp client library not found. Cannot use url parameter")
    try:
        from openerp_libclient.extra.log_client import getTransportFromDSN
    except ImportError:
        raise ImportError("openerp client library doesn't have remote logging utility")

if not opt.remote:
    server = local_server_thread(root_path=options['root-path'], port=options['port'],
                        netport=options['netport'], addons_path=options['addons-path'],
                        dbname=options['dbname'],
                        srv_mode=options['server_series'], config=options['config'],
                        do_warnings=bool(opt.warnings in ('all','warn')),
                        ftp_port=opt.ftp_port, defines=opt.defines, pyargs=opt.pyargs,
                        debug=opt.debug or opt.debug_server)
else:
    # connect to remote server!
    server = remote_server_thread()

logger.info('start of script')
try:
    mods = options['modules'] or []
    if opt.all_modules:
        try:
            logger.debug("Scanning all modules in %s", options['addons-path'])
            # this shall work the same as addons/__init__.py
            if opt.black_modules:
                black_modules = filter(bool, opt.black_modules.split(' '))
            else:
                black_modules = []

            def is_black(modname):
                for bm in black_modules:
                    if fnmatch(modname, bm):
                        return True
                return False

            addon_paths = map(str.strip, options['addons-path'].split(','))
            for mdir, mname in get_modules2(addon_paths):
                if is_black(mname):
                    logger.debug("Module %s is black listed, skipping.", mname)
                    continue
                mrdir = reduce_homedir(mdir)
                try:
                    mod_info = load_mod_info(mdir, mname)
                except Exception:
                    logger.warning("Cannot load module info from %s/%s:", mrdir, mname, exc_info=True)
                    continue
                if not mod_info:
                    # it is acceptable if one subdir of our modules path is not a module
                    logger.debug("Path %s/%s is not a module", mrdir, mname)
                    continue
                if not mod_info.get('installable', True):
                    logger.info("Module %s at %s is not installable, skipping", mname, mrdir)
                    continue
                # Here, it should be a valid module
                mods.append(mname)
        except Exception:
            logger.exception("Cannot scan modules:")
    
    logging.getLogger('bqi.state').info("set num_modules %d", len(mods))
    if opt.dry_run:
        logger.info("Dry run! Here is what would happen:")
        logger.info("%s", ' '.join(server.args))
        logger.info("Modules considered are: %s", ", ".join(mods))
        logger.info("And then, do %d steps:", len(cmdargs))
        for cmd, args, in cmdargs:
            logger.info(" > %s %s", cmd, ' '.join(args))
        logger.debug("Options now:")
        for key, val in opt.__dict__.items():
            if not val:
                continue
            logger.debug("Option: %s (%s): %s", key,type(val), val)
        sys.exit(0)

    server.start_full()
    client = client_worker(uri, options)
    ost = client.get_ostimes()
    logger.info("Server started at: User: %.3f, Sys: %.3f" % (ost[0], ost[1]))

    ret = True
    for cmd, args in cmdargs:
        try:
            if (not ret) and not cmd.startswith('+'):
                continue
            ign_result = cmd.startswith('-')
            if cmd[0] in ['-', '+']:
                cmd = cmd[1:]

            if cmd == 'create-db':
                ret = client.create_db(lang=options['lang'])
            elif cmd == 'drop-db':
                ret = client.drop_db()
            elif cmd == 'start-server':
                # a simple login will trigger a db load and ensure
                # that the server's ORM is working
                ret = bool( client._login() )
            elif cmd == 'install-module':
                ret = client.install_module(mods + args)
            elif cmd == 'upgrade-module':
                ret = client.upgrade_module(mods+args)
            elif cmd == 'check-quality':
                ret = client.check_quality(mods+args, options['quality-logs'])
            elif cmd == 'install-translation':
                ret = client.import_translate(options['translate-in'])
            elif cmd == 'fields-view-get':
                ret = client.fields_view_get()
            elif cmd == 'translation-import':
                ret = client.import_trans(*args)
            elif cmd == 'translation-load':
                ret = client.load_trans(*args)
            elif cmd == 'translation-export':
                ret = client.export_trans(*args)
            elif cmd == 'translation-sync':
                ret = client.sync_trans(*args)
            elif cmd == 'get-sqlcount':
                scount = client.execute_common('root', 'get_sqlcount')
                logger.info("SQL counter: %s", scount)
                del scount
                ret = True
            elif cmd == 'import':
                ret = client.import_data_file(*args)
            elif cmd == 'login':
                ret = client._login(*args)
            elif cmd == 'keep' or cmd == 'keep-running':
                try:
                    logger.info("Server is running, script is paused. Press Ctrl+C to continue.")
                    if not opt.remote:
                        print "Remember, the 'admin' password is \"%s\" and the super-user \"%s\"" % \
                                (opt.pwd, opt.super_passwd)
                    while server.is_running:
                        time.sleep(60)
                    logger.info("Server stopped, exiting")
                except KeyboardInterrupt:
                    logger.info("Stopping after Ctrl+C")
                    ret = False
            elif cmd == 'inter' or cmd == 'interactive':
                logger.info("Interactive mode. Enjoy!")
                print "Remember, the 'admin' password is \"%s\" and the super-user \"%s\"" % \
                            (opt.pwd, opt.super_passwd)
                cmdp = CmdPrompt(client)
                try:
                    while True and server.is_running:
                        r = cmdp.handle()
                        if not r:
                            break
                except KeyboardInterrupt:
                    logger.info("Keyboard interrupt, exiting")

                cmdp.finish()

        except ClientException, e:
            logger.error(reduce_homedir("%s" % e))
            server.dump_blame(e)
            ret = False
        except xmlrpclib.Fault, e:
            e_fc = str(e.faultCode)
            logger.error('xmlrpc exception: %s', reduce_homedir(e_fc.strip()))
            logger.error('xmlrpc +: %s', reduce_homedir(e.faultString.rstrip()))
            server.dump_blame(e)
            ret = False
        except RpcException, e:
            server.dump_blame(e)
            ret = False
        except Exception, e:
            logger.exception('exc:')
            server.dump_blame(e)
            ret = False
        
        server.clear_context()
        
        if (not ret) and ign_result:
            # like make's commands, '-' means ignore result
            logger.info("Command %s failed, but will continue.", cmd)
            ret = True

        if not ret:
            logger.error("Command %s failed, stopping tests.", cmd)
        
        # end for

    ost = client.get_ostimes(ost)
    logger.info("Server ending at: User: %.3f, Sys: %.3f" % (ost[0], ost[1]))

    server.stop()
    server.join()
    if ret:
        sys.exit(0)
    else:
        sys.exit(3)
except ServerException, e:
    logger.error(reduce_homedir("%s" % e))
    server.dump_blame(e)
    server.stop()
    server.join()
    sys.exit(4)
except ClientException, e:
    logger.error(reduce_homedir("%s" % e))
    server.stop()
    server.join()
    sys.exit(5)
except xmlrpclib.Fault, e:
    logger.error('xmlrpc exception: %s', reduce_homedir( e.faultCode.strip()))
    logger.error('xmlrpc +: %s', reduce_homedir(e.faultString.rstrip()))
    server.stop()
    server.join()
    sys.exit(1)
except RpcException, e:
    server.stop()
    server.join()
    sys.exit(1)
except KeyboardInterrupt:
    logger.error("Received Interrupt signal, exiting")
    server.stop()
    server.join()
    sys.exit(6)
except Exception, e:
    logger.exception('')
    server.stop()
    server.join()
    sys.exit(1)

logger.info('end of script')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
