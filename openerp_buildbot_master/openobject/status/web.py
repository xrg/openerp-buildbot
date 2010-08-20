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

def get_args_int(args, name, default=0):
    if args.get(name) is None:
        return default
    try:
        return int(args.get(name,[default,])[0])
    except (ValueError, TypeError):
        return default

baseweb.HEADER = '''
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en-gb" >
    <head>
        <title>OpenERP Integration Server</title>
        <meta content="text/html; charset=utf-8" http-equiv="Content-Type"/>
        <meta content="index, follow" name="robots"/>
        <link rel="stylesheet" href="%(root)scss/styles.css" type="text/css" />
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
        req.setHeader('Cache-Control', 'no-cache')
        base_builders_url = self.path_to_root(req) + "buildersresource/"
        builders = req.args.get("builder", status.getBuilderNames())
        branches = [b for b in req.args.get("branch", []) if b]
        all_builders = [html.escape(bn) for bn in builders]
        num_cols = get_args_int(req.args, 'num', 5)
        

        data = ""
        data += "<table class='grid' id='latest_builds'>"
        data += '<tr class="header" style="vertical-align:center font-size: 18px;"><td class="grid-cell" align="center">Branches / Builds</td>'
        for num in range(num_cols):
            data+= '<td class="grid-cell" align="center" >Build: %s</td>' % (num + 1)
        data += '<td class="grid-cell" align="center">Current Status</td>'
        
        for bn in all_builders:
            base_builder_url = base_builders_url + urllib.quote(bn, safe='')
            builder = status.getBuilder(bn)
            data += "<tr class='grid-row'>\n"
            data += '<td class="grid-cell" align="center"><a href="%s">%s</a></td>\n'%(base_builder_url, html.escape(bn))
            # It is difficult to do paging here, because we are already iterating over the
            # builders, so won't have the same build names or rev-ids.
            builds = list(builder.generateFinishedBuilds(map_branches(branches),num_builds=num_cols))
            builds.reverse()
            for build in builds[:num_cols]:
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
                except Exception:
                    label = None
                if not label:
                    label = "#%d" % build.getNumber()
                text = ['<a href="%s" title="%s">%s</a>' % (url, html.escape(build.getReason()), label)]
                box = Box(text, class_="build%s" % build_get_class(build), align="center")
                data += box.td()
            for i in range(len(builds),num_cols):
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

class OOStatusHelper(object):
    """ Helper functions for OpenObjectStatusResourceBuild, OpenObjectStatusResourceBuilder
    """
    _base_logs = ('stdio', 'stderr', 'bqi.rest', 'bqi.rest.blame', 
                    'server.out', 'server.err',
                    'interrupt', 'err.html', 'err.text')

    def _get_step_names(self, build, step_tname):
        """Put the step names for build in step_tname struct
        
           The format is ('name', 'substep-name' or False)
        """
        
        for step in build.getSteps():
            name = step.getName()
            if (name, False) not in step_tname:
                step_tname.append((name,False))
            if name == 'OpenERP-Test':
                for slog in step.getLogs():
                    sname = slog.getName()
                    if sname in self._base_logs:
                        continue
                    sname = sname.split('.',1)[0]
                    if (name, sname) not in step_tname:
                        step_tname.append((name, sname))

    def _req_fmt(self, req, **kwargs):
        """ Format a url like req's request, but also with some args
        """
        
        args = req.args.copy()
        for key, val in kwargs.items():
            args[key] = [val,]
        args_pairs = []
        args_str = ''
        for key, vals in args.items():
            args_pairs.append('%s=%s' % (key, urllib.quote(str(vals[0]))))
        if args_pairs:
            args_str += '?' + '&'.join(args_pairs)
        return req.path + args_str

    def _iter_td(self, req, name, subname, build, is_build=False):
        """ Get the "td" block for some build.steps
        """
        
        data = ''
        data += "<td>"
        found = False
        for s in build.getSteps():
            slogs = []
            if s.getName() != name:
                continue
            if name == 'OpenERP-Test':
                for slog in s.getLogs():
                    if (subname is False and slog.getName() in self._base_logs) \
                            or subname == (slog.getName().split('.',1)[0]):
                        slogs.append(slog)
            else:
                slogs = s.getLogs()
        
            if not slogs:
                continue
            
            found = True
            data += "  <ol>\n"
            for logfile in slogs:
                logname = logfile.getName()
                if logname.endswith('.blame'):
                    continue
                if not is_build:
                    logurl = req.childLink("builds/%d/steps/%s/logs/%s" %
                            (build.getNumber(),urllib.quote(name),
                            urllib.quote(logname)))
                else:
                    logurl = req.childLink("steps/%s/logs/%s" %
                            (urllib.quote(name), urllib.quote(logname)))
                data += ("  <li><a href=\"%s\">%s</a>\n" %
                            (logurl, logfile.getName()))
                if name == 'OpenERP-Test' and logname not in ('stdio', 'server.out',):
                    txt = logfile.getText()
                    color = 'success'
                    disp_txt = 'Passed'
                    btitle = "OK"
                    for blog in s.getLogs():
                        if blog.getName() != (logname + '.blame'):
                            continue
                        # We found a blame log for this log
                        color = 'failure'
                        disp_txt = 'Failed'
                        btitle = html.escape(blog.getText())
                        wefailed = True
                        break
                
                    data += ': <span class="%s" title="%s">%s</span>' % \
                                (color, btitle, disp_txt)
                data += "</li>\n"
            data += "</ol>"

            if not subname:
                text = " ".join(s.getText())
                color = ''
                if text.find('Failed') != -1:
                    color = 'failure'
                elif text.find('Sucessfully') != -1 or text.find('Passed') != -1:
                    color = 'success'
                elif text.find('Warnings') != -1:
                    color = 'warnings'
                elif text.find('exception') != -1:
                    color = 'exception'
                if color:
                    data += '<span class="%s"> %s</span></td>'%(color,text)
                else:
                    data += '<span>%s</span></td>'%(text)

        if not found:
            data += '<span>n/a</span>'
        data += '</td>'
        return data

class OpenObjectStatusResourceBuild(OOStatusHelper,StatusResourceBuild):
    def __init__(self, build_status=None, build_control=None, builder_control=None):
        StatusResourceBuild.__init__(self, build_status, build_control, builder_control)

    def body(self, req):
        b = self.build_status
        status = self.getStatus(req)
        req.setHeader('Cache-Control', 'no-cache')
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
        data += "<td class='grid-cell'><span>%s<br/>%s</span></td></tr>"% (html.escape(str(revision)),commiter)
        
        step_tname = []
        self._get_step_names(b, step_tname)

        for name, subname in step_tname:
            if subname:
                data += '<tr class="grid-row"><td class="grid-cell">%s<br/>%s</td>' % (name, subname)
            else:
                data += '<tr class="grid-row"><td class="grid-cell">%s</td>' % name
            data += self._iter_td(req, name, subname, b, is_build=True)
            data += "</tr>"
        data += " </table>"

        bdata = ''
        for sstep in b.getSteps():
            sbdata = ''
            for slog in sstep.getLogs():
                slname = slog.getName()
                if not slname.endswith('.blame'):
                    continue
                sbdata += '<h4>%s</h4>\n<ul>' % html.escape(slname[:-6])
                for bline in slog.getText().split('\n'):
                    sbdata += '<li>%s</li>\n' % html.escape(bline)
                sbdata += '</ul>\n'

            if sbdata:
                bdata += '<h3>%s</h3>\n%s' % (sstep.getName(), sbdata)
        if bdata:
            data += '<h2>All trouble info</h2>\n' + bdata

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

class OpenObjectStatusResourceBuilder(OOStatusHelper,StatusResourceBuilder):

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
        req.setHeader('Cache-Control', 'no-cache')
        control = self.builder_control

        projectName = status.getProjectName()

        data = '<a href="%s">%s</a>\n' % (self.path_to_root(req), projectName)

        data += "<h1>Builder: %s</h1>\n" % html.escape(builder_name)

        base_builder_url = self.path_to_root(req) + "buildersresource/" + urllib.quote(builder_name, safe='')
        # Then a section with the last n builds, with the most recent build
        # distinguished from the rest.
        num_cols = get_args_int(req.args, 'num', 5)
        max_buildnum = get_args_int(req.args, 'max', None)

        step_tname = []
        builds = []

        for build in b.generateFinishedBuilds(num_builds=num_cols, max_buildnum=max_buildnum):
            if build not in builds:
                builds.append(build)
            self._get_step_names(build, step_tname)
        
        if req.args.get('mrange',False):
            mrange = req.args['mrange'][0]
            if mrange.endswith('%'):
                mrange=mrange[:-1]
                step_tname = filter( lambda sn: sn[1] is False or sn[1].startswith(mrange), step_tname)
            elif '-' in mrange:
                mmin, mmax = mrange.split('-', 1)
                mmax += 'zzzz'  # so that a-b gets up to bzzar..
                step_tname = filter( lambda sn: sn[1] is False or (sn[1] >= mmin and sn[1] <= mmax) , step_tname)
            else:
                step_tname = filter( lambda sn: sn[1] is False or (sn[1] == mrange) , step_tname)

        if not builds:
            data += "<h2>Recent Builds:No Builds</h2>\n"
        else:
            data += "<h2>Recent Builds:</h2>\n"
            data += "<table border='1'><tr><th>Commiter <br> / Steps</th>"
        for build in builds:
            ss = build.getSourceStamp()
            commiter = ""
            revision = '?'
            hback = ''
            hnext = ''
            if list(build.getResponsibleUsers()):
                for who in build.getResponsibleUsers():
                    commiter += "%s" % html.escape(who)
            else:
                commiter += "No Commiter Found !"
            if ss.revision:
                revision = html.escape(str(ss.revision))
            
            data += "<th><span>"
            
            url = (base_builder_url + "/builds/%d" % build.getNumber())
            data += '<a href="%s">#%d rev: %s</a><br/>%s' % \
                    (url, build.getNumber(), revision, commiter)

            if build.getNumber() > 0 and (build is builds[-1]):
                data += '</span><br/><a href="%s">prev builds&gt;</a></th>' % \
                    (self._req_fmt(req, max=(build.getNumber()-1)), )
            elif max_buildnum is not None and max_buildnum <= build.getNumber() \
                    and (build is builds[0]):
                data += '</span><br/><a href="%s">&lt;next builds</a><span>' % \
                (self._req_fmt(req, max=(build.getNumber()+ num_cols)), )
            else:
                data += '</span></th>'
        data += "</tr>"
        
        for name, subname in step_tname:
            if subname:
                data += '<tr><td>%s<br/><a href="%s">%s</a></td>' % \
                    (name, self._req_fmt(req, mrange="%s%%" % subname), subname)
            else:
                data += "<tr><td>%s</td>" % name
            for build in builds:
                data += self._iter_td(req, name, subname, build)
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

    def setupUsualPages(self, *args, **kwargs):
        WebStatus.setupUsualPages(self, *args, **kwargs)
        self.putChild("buggraph", BugGraph())
        self.putChild("latestbuilds", LatestBuilds())
        self.putChild("buildersresource", OpenObjectBuildersResource())



# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
