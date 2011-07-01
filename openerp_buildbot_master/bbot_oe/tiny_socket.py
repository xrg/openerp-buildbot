##############################################################################
#
# Copyright (c) 2004-2010 TINY SPRL. (http://tiny.be) All Rights Reserved.
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
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
#
##############################################################################

import socket
import cPickle
import sys
import logging
import gzip
import StringIO

class Myexception(Exception):
    def __init__(self, faultCode, faultString):
        self.faultCode = faultCode
        self.faultString = faultString
        self.args = (faultCode, faultString)

class mysocket:
    def __init__(self, sock=None):
        if sock is None:
            self.sock = socket.socket( socket.AF_INET, socket.SOCK_STREAM)
        else:
            self.sock = sock
        # self.sock.settimeout(120)
        # prepare this socket for long operations: it may block for infinite
        # time, but should exit as soon as the net is down
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    def connect(self, host, port=False):
        if not port:
            protocol, buf = host.split('//')
            host, port = buf.split(':')
        self.sock.connect((host, int(port)))
    def disconnect(self):
        # on Mac, the connection is automatically shutdown when the server disconnect.
        # see http://bugs.python.org/issue4397
        if sys.platform != 'darwin':
            self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()
    def mysend(self, msg, exception=False, traceback=None):
        msg = cPickle.dumps([msg,traceback])
        size = len(msg)
        self.sock.send('%8d' % size)
        self.sock.send(exception and "1" or "0")
        totalsent = 0
        while totalsent < size:
            sent = self.sock.send(msg[totalsent:])
            if sent == 0:
                raise RuntimeError, "socket connection broken"
            totalsent = totalsent + sent
    def myreceive(self):
        buf=''
        while len(buf) < 8:
            chunk = self.sock.recv(8 - len(buf))
            if not chunk:
                raise RuntimeError, "socket connection broken"
            buf += chunk
        size = int(buf)
        buf = self.sock.recv(1)
        if buf != "0":
            exception = buf
        else:
            exception = False
        msg = ''
        while len(msg) < size:
            chunk = self.sock.recv(size-len(msg))
            if not chunk :
                raise RuntimeError, "socket connection broken"
            msg = msg + chunk
        res = cPickle.loads(msg)
        if isinstance(res[0],Exception):
            if exception:
                raise Myexception(str(res[0]), str(res[1]))
            raise res[0]
        else:
            return res[0]

from xmlrpclib import Transport,ProtocolError

import httplib
class HTTP11(httplib.HTTP):
    _http_vsn = 11
    _http_vsn_str = 'HTTP/1.1'

    def is_idle(self):
        return self._conn and self._conn._HTTPConnection__state == httplib._CS_IDLE

try:
    if sys.version_info[0:2] < (2,6):
            # print "No https for python %d.%d" % sys.version_info[0:2]
        raise AttributeError()

    class HTTPS(httplib.HTTPS):
        _http_vsn = 11
        _http_vsn_str = 'HTTP/1.1'

        def is_idle(self):
            return self._conn and self._conn._HTTPConnection__state == httplib._CS_IDLE
            # Still, we have a problem here, because we cannot tell if the connection is
            # closed.

except AttributeError:
    # if not in httplib, define a class that will always fail.
    class HTTPS():
        def __init__(self,*args):
            raise NotImplementedError( "your version of httplib doesn't support HTTPS" )

class PersistentTransport(Transport):
    """Handles an HTTP transaction to an XML-RPC server, persistently."""

    def __init__(self, use_datetime=0, send_gzip=False):
        self._use_datetime = use_datetime
        self._http = {}
        self._log = logging.getLogger('Rpc.Transport')
        self._send_gzip = send_gzip
        # print "Using persistent transport"

    def make_connection(self, host):
        # create a HTTP connection object from a host descriptor
        if not self._http.has_key(host):
            host, extra_headers, x509 = self.get_host_info(host)
            self._http[host] = HTTP11(host)
            self._log.info("New connection to %s", host)
        if not self._http[host].is_idle():
            # Here, we need to discard a busy or broken connection.
            # It might be the case that another thread is using that
            # connection, so it makes more sense to let the garbage
            # collector clear it.
            self._http[host] = None
            host, extra_headers, x509 = self.get_host_info(host)
            self._http[host] = HTTP11(host)
            self._log.info("New connection to %s",host)

        return self._http[host]

    def get_host_info(self, host):
        host, extra_headers, x509 = Transport.get_host_info(self,host)
        if extra_headers == None:
            extra_headers = []

        extra_headers.append( ( 'Connection', 'keep-alive' ))

        return host, extra_headers, x509

    def _parse_response(self, response):
        """ read response from input file/socket, and parse it
            We are persistent, so it is important to only parse
            the right amount of input
        """

        p, u = self.getparser()

        if response.msg.get('content-encoding') == 'gzip':
            gzdata = StringIO.StringIO()
            while not response.isclosed():
                rdata = response.read(1024)
                if not rdata:
                    break
                gzdata.write(rdata)
            gzdata.seek(0)
            rbuffer = gzip.GzipFile(mode='rb', fileobj=gzdata)
            while True:
                respdata = rbuffer.read()
                if not respdata:
                    break
                p.feed(respdata)
        else:
            while not response.isclosed():
                rdata = response.read(1024)
                if not rdata:
                    break
                if self.verbose:
                    print "body:", repr(response)
                p.feed(rdata)
                if len(rdata)<1024:
                    break

        p.close()
        return u.close()

    def request(self, host, handler, request_body, verbose=0):
        # issue XML-RPC request

        try:
            h = self.make_connection(host)
            if verbose:
                h.set_debuglevel(1)

            self.send_request(h, handler, request_body)
        except httplib.CannotSendRequest:
            # try once more..
            if h: h.close()
            h = self.make_connection(host)
            if verbose:
                h.set_debuglevel(1)

            self.send_request(h, handler, request_body)

        self.send_host(h, host)
        self.send_user_agent(h)
        self.send_content(h, request_body)

        resp = None
        try:
            resp = h._conn.getresponse()
            # TODO: except BadStatusLine, e:

            errcode, errmsg, headers = resp.status, resp.reason, resp.msg
            if errcode != 200:
                raise ProtocolError( host + handler, errcode, errmsg, headers )

            self.verbose = verbose

            try:
                sock = h._conn.sock
            except AttributeError:
                sock = None

            return self._parse_response(resp)
        finally:
            if resp: resp.close()

    def send_content(self, connection, request_body):
        connection.putheader("Content-Type", "text/xml")

        if self._send_gzip and len(request_body) > 512:
            buffer = StringIO.StringIO()
            output = gzip.GzipFile(mode='wb', fileobj=buffer)
            output.write(request_body)
            output.close()
            buffer.seek(0)
            request_body = buffer.getvalue()
            connection.putheader('Content-Encoding', 'gzip')

        connection.putheader("Content-Length", str(len(request_body)))
        connection.putheader("Accept-Encoding",'gzip')
        connection.endheaders()
        if request_body:
            connection.send(request_body)

    def send_request(self, connection, handler, request_body):
        connection.putrequest("POST", handler, skip_accept_encoding=1)

class SafePersistentTransport(PersistentTransport):
    """Handles an HTTPS transaction to an XML-RPC server."""

    # FIXME: mostly untested

    def make_connection(self, host):
        # create a HTTPS connection object from a host descriptor
        # host may be a string, or a (host, x509-dict) tuple
        if not self._http.has_key(host):
            import httplib
            host, extra_headers, x509 = self.get_host_info(host)
            self._http[host] = HTTPS(host, None, **(x509 or {}))
        return self._http[host]

class AuthClient(object):
    def getAuth(self, atype, realm):
        raise NotImplementedError("Cannot authenticate for %s" % atype)

    def resolveFailedRealm(self, realm):
        """ Called when, using a known auth type, the realm is not in cache
        """
        raise NotImplementedError("Cannot authenticate for realm %s" % realm)

import base64
class BasicAuthClient(AuthClient):
    def __init__(self):
        self._realm_dict = {}
        self._log = logging.getLogger('BasicAuthClient')

    def getAuth(self, atype, realm):
        if atype != 'Basic' :
            return super(BasicAuthClient,self).getAuth(atype, realm)

        if not self._realm_dict.has_key(realm):
            self._log.debug("realm dict: %r", self._realm_dict)
            self._log.debug("missing key: \"%s\"" % realm)
            self.resolveFailedRealm(realm)
        return 'Basic '+ self._realm_dict[realm]

    def addLogin(self, realm, username, passwd):
        """ Add some known username/password for a specific login.
            This function should be called once, for each realm
            that we want to authenticate against
        """
        assert realm
        auths = base64.encodestring(username + ':' + passwd)
        if auths[-1] == "\n":
            auths = auths[:-1]
        self._realm_dict[realm] = auths

    def resetLogin(self, realm):
        """ When some login fails, initially, we need to reset the
            failed credentials, so that they are no more used.
        """
        if self._realm_dict.has_key(realm):
            del self._realm_dict[realm]

class addAuthTransport:
    """ Intermediate class that authentication algorithm to http transport
    """

    def setAuthClient(self, authobj):
        """ Set the authentication client object.
            This method must be called before any request is issued, that
            would require http authentication
        """
        assert isinstance(authobj, AuthClient)
        self._auth_client = authobj

    def setAuthTries(self, tries):
        self._auth_tries = int(tries)

    def request(self, host, handler, request_body, verbose=0):
        # issue XML-RPC request
        max_tries = getattr(self, "_auth_tries", 3)
        tries = 0
        atype = None
        realm = None
        h = None

        while(tries < max_tries):
            if not h:
                h = self.make_connection(host)
                if verbose:
                    h.set_debuglevel(1)

            tries += 1
            try:
                self.send_request(h, handler, request_body)
                self.send_host(h, host)
                self.send_user_agent(h)
            except httplib.CannotSendRequest:
                if h: h.close()
                continue

            if atype:
                # This line will bork if self.setAuthClient has not
                # been issued. That is a programming error, fix your code!
                auths = self._auth_client.getAuth(atype, realm)
                h.putheader('Authorization', auths)
            self.send_content(h, request_body)

            resp = h._conn.getresponse()
            #  except BadStatusLine, e:

            if resp.status == 401:
                if 'www-authenticate' in resp.msg:
                    (atype,realm) = resp.msg.getheader('www-authenticate').split(' ',1)
                    data1 = resp.read()
                    if realm.startswith('realm="') and realm.endswith('"'):
                        realm = realm[7:-1]
                    # print "Resp:", resp.version,resp.isclosed(), resp.will_close
                    #print "Want to do auth %s for realm %s" % (atype, realm)
                    if atype != 'Basic':
                        raise ProtocolError(host+handler, 403,
                                        "Unknown authentication method: %s" % atype, resp.msg)
                    continue # with the outer while loop
                else:
                    raise ProtocolError(host+handler, 403,
                                'Server-incomplete authentication', resp.msg)

            if resp.status != 200:
                raise ProtocolError( host + handler,
                    resp.status, resp.reason, resp.msg )

            self.verbose = verbose

            try:
                sock = h._conn.sock
            except AttributeError:
                sock = None

            return self._parse_response(resp)

        raise ProtocolError(host+handler, 403, "No authentication",'')

class PersistentAuthTransport(addAuthTransport,PersistentTransport):
    pass

class SafePersistentAuthTransport(addAuthTransport,SafePersistentTransport):
    pass

#eof