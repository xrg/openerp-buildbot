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
from zope.interface import implements
from twisted.spread import pb
from twisted.web import html, server
from twisted.web.resource import Resource
from buildbot.status.web.logs import ChunkConsumer

from buildbot import interfaces
from buildbot.status import builder
from buildbot.status.web.base import IHTMLLog, HtmlResource

textlog_stylesheet = """
<style type="text/css">
 div.data {
  font-family: "Courier New", courier, monotype;
 }
 span.stdout {
  font-family: "Courier New", courier, monotype;
 }
 span.stderr {
  font-family: "Courier New", courier, monotype;
  color: red;
 }
 span.header {
  font-family: "Courier New", courier, monotype;
  color: blue;
 }
</style>
"""

qualitylog_stylesheet = """
<link rel="stylesheet" type="text/css" href="%(root)scss/quality-log-style.css" media="all"/>
<link type="text/css" href="%(root)sjs/jquery/themes/base/ui.all.css" rel="stylesheet" />
<script type="text/javascript" src="%(root)sjs/jquery/jquery-1.3.2.js"></script>
<script type="text/javascript" src="%(root)sjs/jquery/ui/ui.core.js"></script>
<script type="text/javascript" src="%(root)sjs/jquery/ui/ui.tabs.js"></script>
<link type="text/css" href="%(root)sjs/jquery/demos.css" rel="stylesheet" />
<script type="text/javascript">
$(function() {
                $("#tabs").tabs();
    });
</script>"""
#%(c['buildbotURL'],c['buildbotURL'],c['buildbotURL'],c['buildbotURL'],c['buildbotURL'],c['buildbotURL'])

class TextLog(Resource):
    # a new instance of this Resource is created for each client who views
    # it, so we can afford to track the request in the Resource.
    implements(IHTMLLog)

    asText = False
    subscribed = False
    logname = ''
    
    def __init__(self, original):
        Resource.__init__(self)
        self.original = original

    def getChild(self, path, req):
        if path == "text":
            self.asText = True
            return self
        return HtmlResource.getChild(self, path, req)

    def htmlHeader(self, request):
        BuildbotURL = str(request.URLPath()).split('builders')[0]
        self.logname = str(request.URLPath()).split('/')[-1]
        if self.logname == 'stdio':
            title = "Log File contents"
            data = "<html>\n<head><title>" + title + "</title>\n"
            data += textlog_stylesheet
        else:
            title = "Module-Quality-File contents"
            data = "<html>\n<head><title>" + title + "</title>\n"
            data += qualitylog_stylesheet%{'root':BuildbotURL}
        data += "</head>\n"
        data += "<body vlink=\"#800080\">\n"
        texturl = request.childLink("text")
        if self.logname == 'stdio':
            data += '<a href="%s">(view as text)</a><br />\n' % texturl
        data += "<pre>\n"
        return data

    def content(self, entries):
        spanfmt = '<span class="%s">%s</span>'
        data = ""
        if self.logname != 'stdio':
            self.asText = True
        for type, entry in entries:
            if self.asText:
                if type != builder.HEADER:
                    data += entry
            else:
                data += spanfmt % (builder.ChunkTypes[type],
                                   html.escape(entry))
        return data

    def htmlFooter(self):
        data = "</pre>\n"
        data += "</body></html>\n"
        return data

    def render_HEAD(self, request):
        if self.asText:
            request.setHeader("content-type", "text/plain")
        else:
            request.setHeader("content-type", "text/html")

        # vague approximation, ignores markup
        request.setHeader("content-length", self.original.length)
        return ''

    def render_GET(self, req):
        self.req = req

        if self.asText:
            req.setHeader("content-type", "text/plain")
        else:
            req.setHeader("content-type", "text/html")

        if not self.asText:
            req.write(self.htmlHeader(req))

        self.original.subscribeConsumer(ChunkConsumer(req, self))
        return server.NOT_DONE_YET

    def finished(self):
        if not self.req:
            return
        try:
            if not self.asText:
                self.req.write(self.htmlFooter())
            self.req.finish()
        except pb.DeadReferenceError:
            pass
        # break the cycle, the Request's .notifications list includes the
        # Deferred (from req.notifyFinish) that's pointing at us.
        self.req = None