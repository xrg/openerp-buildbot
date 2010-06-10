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

from buildbot.status.web.base import HtmlResource,map_branches,Box,ICurrentBox,build_get_class,path_to_builder
from buildbot.status.web.baseweb import WebStatus,OneBoxPerBuilder
from buildbot.status.web import baseweb
from buildbot.status.web.build import StatusResourceBuild,BuildsResource
from buildbot.status.web.builder import StatusResourceBuilder, StatusResourceAllBuilders
from twisted.web import html
import xmlrpclib
import pickle
import os
from lxml import etree
import urllib, time
from buildbot import version, util

ROOT_PATH = '.'

baseweb.HEADER = '''
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en-gb" >
    <head>
        <title>OpenERP Integration Server</title>
        <meta content="text/html; charset=iso-8859-1" http-equiv="Content-Type"/>
        <meta content="index, follow" name="robots"/>
        <link rel="stylesheet" href="%(root)scss/styles.css" type="text/css" />
        <meta content="text/html; charset=utf-8" http-equiv="content-type"/>
        <link type="%(root)simage/x-icon" rel="shortcut icon" href="%(root)sfavicon.ico"/>
        <!-- Open Object Css File Start -->
        <link type="text/css" href="%(root)scss/style.css" rel="stylesheet"/>
        <link type="text/css" href="%(root)scss/listgrid.css" rel="stylesheet"/>
        <link type="text/css" href="%(root)scss/dashboard.css" rel="stylesheet"/>


        <!-- Open Object Css File End -->
    </head>
<body>

            <table width="1004" border="0" cellspacing="0" cellpadding="0">
            <tr>
                <td width="202"><a href="http://openobject.com" alt="Open Object - Free Management Solution Logo"/><img src="%(root)simages/openobject.jpg" border="0"/></a></td>
                <td width="335"><div align="right"><img src="%(root)simages/picture.jpg" width="242" height="68" /></div></td>
                <td width="440" align="right" valign="top">
                    <table id="Table_01" height="35" border="0" cellpadding="0" cellspacing="0">
                    <tr>
                        <td class="greycurveleft" width="23px" height="35px">
                        </td>
                        <td width="107" class="headerlinkgrey">
                            <div class="headerlink" align="center"><a href="http://openerp.com"><strong>Open  ERP</strong></a></div>
                        </td>
                        <td width="22px" height="35px" class="greyredcurve"></td>
                        <td width="125" height="35" class="headerlinkgrey">
                            <div class="headerlink" align="center"><a href="http://ondemand.openerp.com"><strong>On Demand</strong></a></div>
                        </td>
                        <td width="20" height="35" class="redcurve">&nbsp;</td>
                        <td width="139" height="35" class="redline">
                            <div class="headerlink" align="center"><a href="http://openobject.com"><strong>Community</strong></a></div>
                        </td>
                        <td width="16" height="35" ><img src="%(root)simages/redcurveright.jpg"/></td>
                    </tr>
                    </table>
                </td>
            </tr>
            </table>

            <table width="1004" border="0" cellspacing="0" cellpadding="0" id="menu_header">
            <tr>
                <td width="141" id="menu_header_menu" nowrap="nowrap"></td>
                <td nowrap="nowrap" align="left" height="25px"></td>
            </tr>
            <tr>
              <td id="menu_header_menu2" nowrap="nowrap"></td>
              <td nowrap="nowrap" align="left"></td>
              </tr>
            </table>'''

baseweb.HEAD_ELEMENTS = [
    '<link href="%(root)sbuildbot.css" rel="stylesheet" type="text/css" />',
    ]
baseweb.BODY_ATTRS = {}

baseweb.FOOTER = '''
            <table width="1004" border="0" align="center" cellpadding="0" cellspacing="0">
                <tr>
                    <td valign="top" align="right"><img src="%(root)simages/fourmis.jpg"/></td>
                </tr>
            </table>

            <table border="0" width="1004" cellpadding="0" cellspacing="0">
                <tr height="1">
                    <td width="1004" bgcolor="#D6D6D6"></td>
                </tr>
            </table>

            <table border="0" width="1004" cellpadding="5" cellspacing="0">
                <tr>
                    <td bgcolor="#ffffff">
                        <div class="footertext">
                            &copy; 2001-TODAY <a href="http://tiny.be">Tiny sprl</a>. All rights reserved.<br/>
                            OpenERP and OpenObject are trademarks of the Tiny company.<br/>
                            They both are released under GPL V3.0.
                        </div>
                    </td>
                </tr>
            </table>
            </td></tr></table></div>
</body>
</html>
'''

class BugGraph(HtmlResource):

    title = "Bug Graph"

    def content(self, request):
        s = request.site.buildbot_service
        s.body_attrs.update({'onload':"javascript:getlatestgraph()"})
        data = ""
        data += self.fillTemplate(s.header, request)
        data += "<head>\n"
        for he in s.head_elements:
            data += " " + self.fillTemplate(he, request) + "\n"
            data += self.head(request)
        data += "</head>\n\n"
        data += '<body %s>\n' % " ".join(['%s="%s"' % (k,v)
                                          for (k,v) in s.body_attrs.items()])
        data += self.body(request)
        data += "</body>\n"
        data += self.fillTemplate(s.footer, request)
        return data

    def body(self, request):
        datasets=['',[]]
        try:
            fp = open(ROOT_PATH + '/bugs.pck','a+')
            datasets = pickle.load(fp)
            import calendar
            import time
            fromDate = request.args.get('fromDate')[0]
            toDate = request.args.get('toDate')[0]
            fromDate = time.strftime(fromDate)
            toDate = time.strftime(toDate)

            for type in datasets[1]:
                for value in type:
                    dt = time.strftime('%Y/%m/%d',(int(value[0]),int(value[1]),1,0,0,0,0,0,0))
                    if dt < fromDate or dt > toDate:
                        index = type.index(value)
                        type[index] = []
        except:
            pass
        data = ''' <span id='retrivalTime'>%s</span><span id='datasets'>%s</span> ''' %(datasets[0],datasets[1])
        return data

class LatestBuilds(HtmlResource):

    title = "Latest Builds"

    def body(self, req):
        status = self.getStatus(req)
        building = False
        online = 0
        control = self.getControl(req)
        base_builders_url = self.path_to_root(req) + "buildersresource/"
        builders = req.args.get("builder", status.getBuilderNames())
        branches = [b for b in req.args.get("branch", []) if b]
        all_builders = [html.escape(bn) for bn in builders]

        data = ""
        data += "<table class='grid' id='latest_builds'>"
        data +="""<tr class='grid-row'><td class='grid-cell'>Latest Builds/Tested Branches</td><td class='grid-cell'>Build : 5</td><td class='grid-cell'>Build : 4</td>
                 <td class='grid-cell'>Build : 3</td><td class='grid-cell'>Build : 2</td><td class='grid-cell'>Build : 1</td><td class='grid-cell'>Current Build</td>"""
        for bn in  all_builders:
            base_builder_url = base_builders_url + urllib.quote(bn, safe='')
            builder = status.getBuilder(bn)
            data += "<tr class='grid-row'>\n"
            data += '<td class="grid-cell"><a href="%s">%s</a></td>\n'%(base_builder_url, html.escape(bn))
            builds = list(builder.generateFinishedBuilds(map_branches(branches),num_builds=5))
            for build in builds[:5]:
                url = (base_builder_url + "/builds/%d" % build.getNumber())
                try:
                    ss = build.getSourceStamp()
                    commiter = ""
                    if list(build.getResponsibleUsers()):
                        for who in build.getResponsibleUsers():
                            commiter += "%s" % html.escape(who)
                    else:
                        commiter += "No Commiter Found !"
                    if ss.revision:
                        revision = ss.revision
                    label = str(revision) + '-' + ''.join(build.text) + '-' +commiter
                except:
                    label = None
                if not label:
                    label = "#%d" % build.getNumber()
                text = ['<a href="%s">%s</a>' % (url, label)]
                box = Box(text, build.getColor(),class_="LastBuild box %s" % build_get_class(build))
                data += box.td(class_="grid-cell",align="center")
            for i in range(len(builds),5):
                data += '<td class="grid-cell" align="center">no build</td>'
            if not builds:
                data += '<td class="grid-cell" align="center">no build</td>'
            current_box = ICurrentBox(builder).getBox(status)
            data += current_box.td(class_="grid-cell",align="center")

            builder_status = builder.getState()[0]
            if builder_status == "building":
                building = True
                online += 1
            elif builder_status != "offline":
                online += 1
            data += "</tr>"
        data += "</table>"
        if control is not None:
            if building:
                stopURL = "builders/_all/stop"
                data += make_stop_form(stopURL, True, "Builds")
            if online:
                forceURL = "builders/_all/force"
                data += make_force_build_form(forceURL, True)
        return data

class OpenObjectStatusResourceBuild(StatusResourceBuild):
    def __init__(self, build_status=None, build_control=None, builder_control=None):
        StatusResourceBuild.__init__(self, build_status, build_control, builder_control)

    def body(self, req):
        b = self.build_status
        status = self.getStatus(req)
        projectName = status.getProjectName()
        data = ('<div class="title"><a href="%s">%s</a></div>'
                % (self.path_to_root(req), projectName))
        builder_name = b.getBuilder().getName()
        data += ("<h1><a href=\"%s\">Builder %s</a>: Build #%d</h1>"
                 % (path_to_builder(req, b.getBuilder()),
                    builder_name, b.getNumber()))
        ss = b.getSourceStamp()
        commiter = ""
        if list(b.getResponsibleUsers()):
            for who in b.getResponsibleUsers():
                commiter += "%s" % html.escape(who)
        else:
            commiter += "No Commiter Found !"
        if ss.revision:
            revision = ss.revision
        data += "<table class='grid' id='build_detail'>"
        data += "<tr class='grid-header'><td class='grid-cell'><span>%s</span></td>"%(builder_name)
        data += "<td class='grid-cell'><span>%s-%s</span></td></tr>"% (html.escape(str(revision)),commiter)
        if b.getLogs():
            for s in b.getSteps():
                name = s.getName()
                data += "<tr class='grid-row'>"
                data += "<td class='grid-cell'>"
                data += (" <li><a href=\"%s\">%s</a>\n"
                         % (req.childLink("steps/%s" % urllib.quote(name)),
                            name))
                data +='</li></td>'
                data +="<td class='grid-cell'>"
                if s.getLogs():
                    data += "  <ol>\n"
                    for logfile in s.getLogs():
                        logname = logfile.getName()
                        logurl = req.childLink("steps/%s/logs/%s" %
                                               (urllib.quote(name),
                                                urllib.quote(logname)))
                        data += ("   <li><a href=\"%s\">%s</a></li>\n" %
                                 (logurl, logfile.getName()))
                    text = " ".join(s.getText())
                    color = ''
                    if text.find('Failed') != -1:
                        color = 'failure'
                    elif text.find('Sucessfully') != -1:
                        color = 'success'
                    elif text.find('Warnings') != -1:
                        color = 'warnings'
                    elif text.find('exception') != -1:
                        color = 'exception'
                    if color:
                        data += '<span class="%s"> %s</span></ol></td></tr>'%(color, text)
                    else:
                        data += '<span>%s</span></ol></td></tr>'%(text)
                else:
                    data += '<span>Skipped</span></ol></td>'

            data += "</ol></table>"

        if ss.changes:
            data += "<h2>All Changes</h2>\n"
            data += "<ol>\n"
            for c in ss.changes:
                data += "<li>" + c.asHTML() + "</li>\n"
            data += "</ol>\n"
        return data

class OpenObjectBuildsResource(BuildsResource):
    def __init__(self, builder_status=None, builder_control=None):
        BuildsResource.__init__(self, builder_status, builder_control)

    def getChild(self, path, req):
        try:
            num = int(path)
        except ValueError:
            num = None
        if num is not None:
            build_status = self.builder_status.getBuild(num)
            if build_status:
                if self.builder_control:
                    build_control = self.builder_control.getBuild(num)
                else:
                    build_control = None
                return OpenObjectStatusResourceBuild(build_status, build_control,
                                           self.builder_control)
        return HtmlResource.getChild(self, path, req)

class OpenObjectStatusResourceBuilder(StatusResourceBuilder):

    def __init__(self, builder_status=None, builder_control=None):
        StatusResourceBuilder.__init__(self, builder_status, builder_control)

    def getChild(self, path, req):
        if path == "force":
            return self.force(req)
        if path == "ping":
            return self.ping(req)
        if path == "events":
            num = req.postpath.pop(0)
            req.prepath.append(num)
            num = int(num)
            # TODO: is this dead code? .statusbag doesn't exist,right?
            log.msg("getChild['path']: %s" % req.uri)
            return NoResource("events are unavailable until code gets fixed")
            filename = req.postpath.pop(0)
            req.prepath.append(filename)
            e = self.builder_status.getEventNumbered(num)
            if not e:
                return NoResource("No such event '%d'" % num)
            file = e.files.get(filename, None)
            if file == None:
                return NoResource("No such file '%s'" % filename)
            if type(file) == type(""):
                if file[:6] in ("<HTML>", "<html>"):
                    return static.Data(file, "text/html")
                return static.Data(file, "text/plain")
            return file
        if path == "builds":
            return OpenObjectBuildsResource(self.builder_status, self.builder_control)

        return HtmlResource.getChild(self, path, req)

    def body(self, req):
        b = self.builder_status
        builder_name = b.getName()
        status = self.getStatus(req)
        control = self.builder_control

        projectName = status.getProjectName()

        data = '<a href="%s">%s</a>\n' % (self.path_to_root(req), projectName)

        data += "<h1>Builder: %s</h1>\n" % html.escape(builder_name)

        # Then a section with the last 5 builds, with the most recent build
        # distinguished from the rest.

        data += "<h2>Recent Builds:</h2>\n"
        data += "<table border='1'><tr><th>Commiter <br> / Steps</th>"
        step_name = []
        builds = []

        for build in b.generateFinishedBuilds(num_builds=5):
            if build not in builds:
                builds.append(build)
            for step in build.getSteps():
                name = step.getName()
                if name not in step_name:
                    step_name.append(name)

        for build in builds:
            ss = build.getSourceStamp()
            commiter = ""
            if list(build.getResponsibleUsers()):
                for who in build.getResponsibleUsers():
                    commiter += "%s" % html.escape(who)
            else:
                commiter += "No Commiter Found !"
            if ss.revision:
                revision = ss.revision
            data += "<th><span>%s-%s</span></th>"% (html.escape(str(revision)),commiter)
        data += "</tr>"
        for name in step_name:
            data += "<tr><td>%s</td>"%name
            for build in builds:
                data += "<td>"
                for s in build.getSteps():
                    if s.getName() == name:
                        if s.getLogs():
                            data += "  <ol>\n"
                            for logfile in s.getLogs():
                                logname = logfile.getName()
                                logurl = req.childLink("builds/%d/steps/%s/logs/%s" %
                                                       (build.getNumber(),urllib.quote(name),
                                                        urllib.quote(logname)))
                                data += ("  <li><a href=\"%s\">%s</a></li>\n" %
                                         (logurl, logfile.getName()))
                            data += "</ol>"
                            text = " ".join(s.getText())
                            color = ''
                            if text.find('Failed') != -1:
                                color = 'failure'
                            elif text.find('Sucessfully') != -1:
                                color = 'success'
                            elif text.find('Warnings') != -1:
                                color = 'warnings'
                            elif text.find('exception') != -1:
                                color = 'exception'
                            if color:
                                data += '<span class="%s"> %s</span></td>'%(color,text)
                            else:
                                data += '<span>%s</span></td>'%(text)
                        else:
                            data += '<span>Skipped</span></td>'
            data += "</tr>"
        data += " </table>"
        return data

class OpenObjectBuildersResource(HtmlResource):

    def getChild(self, path, req):
        s = self.getStatus(req)
        if path in s.getBuilderNames():
            builder_status = s.getBuilder(path)
            builder_control = None
            c = self.getControl(req)
            if c:
                builder_control = c.getBuilder(path)
            return OpenObjectStatusResourceBuilder(builder_status, builder_control)
        if path == "_all":
            return StatusResourceAllBuilders(self.getStatus(req),
                                             self.getControl(req))
        return HtmlResource.getChild(self, path, req)

class OpenObjectWebStatus(WebStatus):
    def __init__(self, http_port=None, distrib_port=None, allowForce=False):
        WebStatus.__init__(self, http_port=http_port, distrib_port=distrib_port, allowForce=allowForce)

    def setupUsualPages(self, *args, **kargs):
        WebStatus.setupUsualPages(self)
        self.putChild("buggraph", BugGraph())
        self.putChild("latestbuilds", LatestBuilds())
        self.putChild("buildersresource", OpenObjectBuildersResource())



# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
