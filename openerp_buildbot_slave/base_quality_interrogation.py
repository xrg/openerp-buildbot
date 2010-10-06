#!/usr/bin/python
# -*- coding: utf-8 -*-
##############################################################################
#    
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>).
#    Copyright (C) 2010 OpenERP SA. (http://www.openerp.com)
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
# import ConfigParser
import optparse
import sys
import threading
import os
import signal
import time
import pickle
import base64
# import socket
import subprocess
import select
import re
import zipfile

admin_passwd = 'admin'

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

class ClientException(Exception):
    """Define our own exception, to avoid traceback
    """
    pass

class ServerException(Exception):
    pass

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

class server_thread(threading.Thread):
    
    def regparser(self, section, regex, funct, multiline=False):
        """ Register a parser for server's output.
        @param section the name of the logger that we try to match, can be *
        @param regex A regular expression to match, or a plain string
        @param funct A callable to execute on match, or a string to log, or
                    a tuple(bqi-class, log_level, string ) to log.
        @param multiline If true, this output can span multiple lines
        """
        self.__parsers.setdefault(section, []).append( (regex, funct, multiline) )

    def regparser_exc(self, etype, erege, funct):
        self.__exc_parsers.append( (etype, erege, funct))

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

    def __init__(self, root_path, port, netport, addons_path, pyver=None, 
                srv_mode='v600', timed=False, debug=False, do_warnings=False,
                ftp_port=None,
                config=None):
        threading.Thread.__init__(self)
        self.root_path = root_path
        self.port = port
        # self.addons_path = addons_path
        self.args = [ 'python%s' %(pyver or ''),] 
        if do_warnings:
            self.args.append('-Wall')
        self.args += ['%sopenerp-server.py' % root_path,]
        if addons_path:
            self.args += [ '--addons-path=%s' % addons_path ]
        if debug:
            self.args += [ '--log-level=debug' ]
        else:
            self.args += [ '--log-level=test' ]
            
        if config:
            self.args += [ '-c', config ]

        # TODO: secure transport, persistent ones.
        if srv_mode == 'v600':
            self.args.append('--xmlrpc-port=%s' % port )
            self.args.append('--no-xmlrpcs')
            # FIXME: server doesn't support this!
            #if ftp_port:
            #    self.args.append('--ftp_server_port=%d' % int(ftp_port))
        elif srv_mode == 'pg84':
            self.args.append('--httpd-port=%s' % port )
            self.args.append('--no-httpds')
            self.args.append('-Dtests.nonfatal=True')
            if ftp_port:
                self.args.append('-Dftp.port=%s' % ftp_port)
        else:
            raise RuntimeError("Invalid server mode %s" % srv_mode)

        if netport:
            self.args.append('--netrpc-port=%s' % netport)
        else:
            self.args.append('--no-netrpc')


        if timed:
            self.args.insert(0, 'time')
        self.proc = None
        self.is_running = False
        self.is_ready = False
        self._lports = {}
        self._io_bufs = {} # Buffers for stdin, stdio processing
        # Will hold info about current op. of the server
        self.state_dict = {'module-mode': 'startup'}

        # self.is_terminating = False
        
        # Regular expressions:
        self.linere = re.compile(r'\[(.*)\] ([A-Z]+):([\w\.-]+):(.*)$', re.DOTALL)
        self.linewere = re.compile(r'(.*\.py):([0-9]+): ([A-Za-z]*Warning): (.*)$', re.DOTALL)
        
        self.log = logging.getLogger('srv.thread')
        self.log_sout = logging.getLogger('server.stdout')
        self.log_serr = logging.getLogger('server.stderr')
        self.log_state = logging.getLogger('bqi.state') # will receive command-like messages

        self.__parsers = {}
        self.__exc_parsers = []
        self.regparser('web-services', 
                'the server is running, waiting for connections...', 
                self.setRunning)
        self.regparser('server', 
                'OpenERP server is running, waiting for connections...', 
                self.setRunning)
        self.regparser('web-services',
                re.compile(r'starting (.+) service at ([0-9\.]+) port ([0-9]+)'),
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
        
        self.regparser_exc('XMLSyntaxError', re.compile(r'line ([0-9]+), column ([0-9]+)'),
                            lambda etype, ematch: { 'file-line': ematch.group(1), 'file-col': ematch.group(2)} )

    def _io_flush(self):
        """ Process any remaining data in _io_bufs
        """

        for fd in self._io_bufs.keys():
            r = self._io_bufs[fd]
        
            while r.endswith("\n"):
                r = r[:-1]

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
            parsers.extend(self.__parsers.get(pk,[]))
        
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
        if self._lports.get('HTTP') != str(self.port):
            self.log.warning("server does not listen HTTP at port %s" % self.port)
        return True
        
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
                        sstr = '\n'.join(faultlines[-2])
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
                    for etype, erege, funct in self.__exc_parsers:
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

class client_worker(object):
    """ This object will connect to a server and perform the various tests.
    
        It holds some common options.
    """
    
    def __init__(self, uri, options):
        global server
        self.log = logging.getLogger('bqi.client')
        if not server.is_ready:
            self.log.error("Server not ready, cannot work client")
            raise RuntimeError()
        self.uri = uri
        self.user = options['login']
        self.pwd = options['pwd']
        self.dbname = options['dbname']
        self.super_passwd = 'admin' # options['super_passwd']
        self.series = options['server_series']

    def _execute(self, connector, method, *args):
        self.log.debug("Sending command '%s' to server", method)
        res = getattr(connector,method)(*args)
        self.log.debug("Command '%s' returned from server", method)
        return res

    def _login(self):
        conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/common')
        uid = self._execute(conn, 'login', self.dbname, self.user, self.pwd)
        if not uid:
            self.log.error("Cannot login as %s@%s" %(self.user, self.pwd))
        return uid

    def import_translate(self, translate_in):
        uid = self._login()
        if not uid:
            return False
        # TODO !
        conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/wizard')
        server.state_dict['module-mode'] = 'translate'
        self.log.debug("Executing module.lang.import %s", translate_in)
        wiz_id = self._execute(conn, 'create',self.dbname, uid, self.pwd, 'module.lang.import')
        if not wiz_id:
            raise ServerException("The language import wizard doesn't exist")
        for trans_in in translate_in:
            lang,ext = os.path.splitext(trans_in.split('/')[-1])
            state = 'init'
            datas = {'form':{}}
            while state!='end':
                res = self._execute(conn,'execute',self.dbname, uid, self.pwd, wiz_id, datas, state, {})
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
        uid = self._login()
        quality_logs += 'quality-logs'
        if not uid:
            return False
        conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/object')
        final = {}
        qlog = logging.getLogger('bqi.qlogs')
        
        self.log.debug("Checking quality of modules %s", ', '.join(modules))
        for module in modules:
            qualityresult = {}
            test_detail = {}
            server.state_dict['module-mode'] = 'quality'
            try:
                quality_result = self._execute(conn,'execute', self.dbname, 
                                    uid, self.pwd,
                                    'module.quality.check','check_quality',module)
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
            # and continue with other modules..
        return True

    def get_ostimes(self, prev=None):
        if self.series not in ('pg84',):
            self.log.debug("Using client-side os.times()")
            return os.times()
        try:
            conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/common')
            ost = self._execute(conn,'get_os_time', self.super_passwd)
            if prev is not None:
                for i in range(0,5):
                    ost[i] -= prev[i]
            return ost
        except Exception:
            self.log.exception("Get os times")
            return ( 0.0, 0.0, 0.0, 0.0, 0.0 )


    def wait(self, id, timeout=600.0):
        progress=0.0
        expire = time.time() + timeout
        conn = xmlrpclib.ServerProxy(self.uri+'/xmlrpc/db')
        while not progress==1.0:
            if time.time() >= expire:
                raise ClientException("Timed out creating the database")
            time.sleep(2.0)
            progress,users = self._execute(conn,'get_progress',self.super_passwd, id)
            self.log.debug("Progress: %s", progress)
        return True


    def create_db(self, lang='en_US'):
        conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/db')
        # obj_conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/object')
        #wiz_conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/wizard')
        #login_conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/common')
        server.state_dict['severity'] = 'blocking'
        db_list = self._execute(conn, 'list')
        if self.dbname in db_list:
            raise ClientException("Database already exists, drop it first!")
        id = self._execute(conn,'create',self.super_passwd, self.dbname, True, lang)
        self.wait(id)
        server.clear_context()
        if not self.install_module(['base_module_quality',]):
            self.log.warning("Could not install 'base_module_quality' module.")
            # but overall pass
        server.clear_context()
        self.log.info("Successful create of db: %s", self.dbname)
        return True

    def drop_db(self):
        conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/db')
        db_list = self._execute(conn,'list')
        if self.dbname in db_list:
            self.log.info("Going to drop db: %s", self.dbname)
            self._execute(conn, 'drop', self.super_passwd, self.dbname)
            self.log.info("Dropped db: %s", self.dbname)
            return True
        else:
            self.log.warning("Not dropping db '%s' because it doesn't exist", self.dbname)
            return False

    def install_module(self, modules):
        uid = self._login()
        if not uid:
            return False
        
        # what buttons to press at each state:
        self.log.debug("Installing modules: %s", ', '.join(modules))
        server.state_dict['module-mode'] = 'install'
        obj_conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/object')
        
        bad_mids = self._execute(obj_conn, 'execute', self.dbname, uid, self.pwd, 
                        'ir.module.module', 'search', 
                        [('name','in',modules), ('state','=','uninstallable')])
        module_ids = self._execute(obj_conn, 'execute', self.dbname, uid, self.pwd, 
                        'ir.module.module', 'search', [('name','in',modules)])
        if not module_ids:
            self.log.error("Cannot find any of [%s] modules to install!",
                            ', '.join(modules))
            return False
        
        # Read the names of modules, so that we can identify them.
        mod_names_res = self._execute(obj_conn, 'execute', self.dbname, uid, self.pwd, 
                        'ir.module.module', 'read', module_ids,
                        ['name'])
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
                self._execute(obj_conn, 'execute', self.dbname, uid, self.pwd, 
                            'ir.module.module', 'button_install', [mid,])
            except xmlrpclib.Fault, e:
                logger.error('xmlrpc exception: %s', reduce_homedir(e.faultCode.strip()))
                logger.error('xmlrpc +: %s', reduce_homedir(e.faultString.rstrip()))
                server.dump_blame(e, ekeys={ 'context': '%s.install' % mod_names[mid],
                            'module': mod_names[mid], 'severity': 'error'})

        server.state_dict['severity'] = 'blocking'
        ret = self._modules_upgrade(uid)
        server.clear_context()
        return ret

        
    def _modules_upgrade(self, uid):
        """ Perform the modules upgrade wizard, for ones previously selected
        """
        obj_conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/object')
        wizard_conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/wizard')

        wiz_id = False
        ret = False
        try:
            form_presses = { 'init': 'start', 'next': 'start',  'config': 'end',  'start': 'end'}
            wiz_id = self._execute(wizard_conn, 'create', self.dbname, uid, self.pwd, 
                            'module.upgrade.simple')
            datas = {}
            ret = self.run_wizard(wizard_conn, uid, wiz_id, form_presses, datas)
            return True
        except xmlrpclib.Fault, e:
            if e.faultCode == 'wizard.module.upgrade.simple':
                self.log.debug("Could not find the old-style wizard for module upgrade, trying the new one")
                wiz_id = False
            else:
                raise

        try:
            wiz_id = self._execute(obj_conn, 'execute', self.dbname, uid, self.pwd, 
                            'base.module.upgrade', 'create', {})
        except xmlrpclib.Fault, e:
            raise ServerException("No usable wizard for module upgrade found, cannot continue")

        ret = self._execute(obj_conn, 'execute', self.dbname, uid, self.pwd,
                        'base.module.upgrade', 'upgrade_module', [wiz_id,], {})
        self.log.debug("Upgrade wizard returned: %r", ret)
        
        assert ret, "The upgrade wizard must return some dict, like redirect to the config view"
        return True

        
        
    def run_wizard(self, wizard_conn, uid, wiz_id, form_presses, datas):
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
            res = self._execute(wizard_conn, 'execute', self.dbname, uid, self.pwd, 
                            wiz_id, datas, state, {})
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
        uid = self._login()
        if not uid:
            return False
        server.state_dict['module-mode'] = 'upgrade'
        obj_conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/object')
        wizard_conn = xmlrpclib.ServerProxy(self.uri + '/xmlrpc/wizard')
        module_ids = self._execute(obj_conn, 'execute', self.dbname, uid, self.pwd, 
                            'ir.module.module', 'search', [('name','in',modules)])
        self._execute(obj_conn, 'execute', self.dbname, uid, self.pwd, 
                            'ir.module.module', 'button_upgrade', module_ids)
        
        server.state_dict['severity'] = 'blocking'
        ret = self._modules_upgrade(uid)
        server.clear_context()
        return ret


usage = """%prog command [options]

Basic Commands:
    start-server         Start Server
    create-db            Create new database
    drop-db              Drop database
    install-module [<m> ...]   Install module
    upgrade-module [<m> ...]   Upgrade module
    install-translation        Install translation file
    check-quality  [<m> ...]    Calculate quality and dump quality result 
                                [ into quality_log.pck using pickle ]
    multi <cmd> [<cmd> ...]     Execute several of the above commands, at a 
                                single server instance.
"""
parser = optparse.OptionParser(usage)
parser.add_option("-m", "--modules", dest="modules", action="append",
                     help="specify modules to install or check quality")
parser.add_option("--addons-path", dest="addons_path", help="specify the addons path")
parser.add_option("--all_modules", dest="all_modules", action='store_true', default=False,
                    help="Operate on all modules that are found on addons-path")
parser.add_option("--homedir", dest="homedir", default=None, 
                help="The directory, whose absolute path will be stripped from messages.")
parser.add_option("--xml-log", dest="xml_log", help="A file to write xml-formatted log to")
parser.add_option("--txt-log", dest="txt_log", help="A file to write plain log to, or 'stderr'")
parser.add_option("--machine-log", dest="mach_log", help="A file to write machine log stream, or 'stderr'")
parser.add_option("--debug", dest="debug", action='store_true', default=False,
                    help="Enable debugging of both the script and the server")

parser.add_option("-W", dest="warnings", default=False,
                    help="Pass this flag to python, so that warnings are considered")

parser.add_option("--quality-logs", dest="quality_logs", help="specify the path of quality logs files which has to stores")
parser.add_option("--root-path", dest="root_path", help="specify the root path")
parser.add_option("-p", "--port", dest="port", help="specify the TCP port", type="int")
parser.add_option("--net_port", dest="netport",help="specify the TCP port for netrpc")
parser.add_option("-d", "--database", dest="db_name", help="specify the database name")
parser.add_option("--login", dest="login", help="specify the User Login")
parser.add_option("--password", dest="pwd", help="specify the User Password")
parser.add_option("--config", dest="config", help="Pass on this config file to the server")
parser.add_option("--ftp-port", dest="ftp_port", help="Choose the port to set the ftp server at")

parser.add_option("--language", dest="lang", help="Use that language as default for the new db")
parser.add_option("--translate-in", dest="translate_in",
                     help="specify .po files to import translation terms")
parser.add_option("--server-series", help="Specify argument syntax and options of the server.\nExamples: 'v600', 'pg84'")

(opt, args) = parser.parse_args()

def die(cond, msg):
    if cond:
        print msg
        sys.exit(1)

options = {
    'addons-path' : opt.addons_path or False,
    'quality-logs' : opt.quality_logs or '',
    'root-path' : opt.root_path or '',
    'translate-in': [],
    'port' : opt.port or 8069,
    'lang': opt.lang or 'en_US',
    'netport':opt.netport or False,
    'dbname': opt.db_name ,
    'modules' : opt.modules,
    'login' : opt.login or 'admin',
    'pwd' : opt.pwd or 'admin',
    'config': opt.config,
    'server_series': opt.server_series or 'v600',
    'homedir': '~/'
}

if opt.homedir:
    options['homedir'] = os.path.abspath(opt.homedir)+'/'

def reduce_homedir(ste):
    global options
    return ste.replace(options['homedir'], '~/')

import logging
def init_log():
    global opt
    log = logging.getLogger()
    if opt.debug:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)
    has_stdout = has_stderr = False

    if not (opt.xml_log or opt.txt_log or opt.mach_log):
        # Default to a txt logger
        opt.txt_log = 'stderr'

    if opt.xml_log:
        hnd = XMLStreamHandler(opt.xml_log)
        log.addHandler(hnd)
        
    if opt.txt_log:
        if opt.txt_log == 'stderr':
            log.addHandler(logging.StreamHandler())
            has_stderr = True
        elif opt.txt_log == 'stdout':
            log.addHandler(logging.StreamHandler(sys.stdout))
            has_stdout = True
        else:
            log.addHandler(logging.FileHandler(opt.txt_log))
            #hnd2.setFormatter()

    if opt.mach_log:
        if opt.mach_log == 'stdout':
            if has_stdout:
                raise Exception("Cannot have two loggers at stdout!")
            hnd3 = logging.StreamHandler(sys.stdout)
            has_stdout = True
        else:
            hnd3 = logging.FileHandler(opt.mach_log)
        hnd3.setFormatter(MachineFormatter())
        log.addHandler(hnd3)

init_log()

logger = logging.getLogger('bqi')

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
                    'install-translation', 'multi'):
            parser.error("incorrect command: %s" % command)
            return
        args = args[1:]
        if command == '--':
            continue
        elif cmd2 == 'multi':
            ret.extend([(x, []) for x in args])
            return ret
        elif cmd2 in ('install-module', 'upgrade-module', 'check-quality',
                        'install-translation'):
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

#die(lmodules and (not opt.db_name),
#        "the modules option cannot be used without the database (-d) option")

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

uri = 'http://localhost:' + str(options['port'])

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

server = server_thread(root_path=options['root-path'], port=options['port'],
                        netport=options['netport'], addons_path=options['addons-path'],
                        srv_mode=options['server_series'], config=options['config'],
                        do_warnings=bool(opt.warnings in ('all','warn')),
                        ftp_port=opt.ftp_port,
                        debug=opt.debug)

logger.info('start of script')
try:
    mods = options['modules'] or []
    if opt.all_modules:
        try:
            logger.debug("Scanning all modules in %s", options['addons-path'])
            # this shall work the same as addons/__init__.py
            addon_paths = map(str.strip, options['addons-path'].split(','))
            for mdir, mname in get_modules2(addon_paths):
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
            elif cmd == 'install-module':
                ret = client.install_module(mods + args)
            elif cmd == 'upgrade-module':
                ret = client.upgrade_module(mods+args)
            elif cmd == 'check-quality':
                ret = client.check_quality(mods+args, options['quality-logs'])
            elif cmd == 'install-translation':
                ret = client.import_translate(options['translate-in'])
        except ClientException, e:
            logger.error(reduce_homedir("%s" % e))
            server.dump_blame(e)
            ret = False
        except xmlrpclib.Fault, e:
            logger.error('xmlrpc exception: %s', reduce_homedir(e.faultCode.strip()))
            logger.error('xmlrpc +: %s', reduce_homedir(e.faultString.rstrip()))
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
