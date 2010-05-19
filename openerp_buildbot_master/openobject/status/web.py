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

from buildbot.status.web.base import HtmlResource,map_branches,Box,ICurrentBox,build_get_class
from buildbot.status.web.baseweb import WebStatus,OneBoxPerBuilder
from buildbot.status.web import baseweb
import xmlrpclib
import pickle
import os
from lxml import etree
import urllib

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
        from twisted.web import html
        status = self.getStatus(req)
        control = self.getControl(req)

        builders = req.args.get("builder", status.getBuilderNames())
        branches = [b for b in req.args.get("branch", []) if b]

        building = False
        online = 0

        base_builders_url = self.path_to_root(req) + "builders/"
        all_builders = [html.escape(bn) for bn in builders]
        trunk_builders = [bn for bn in all_builders if bn.startswith('trunk')]
        stable_builders = [bn for bn in all_builders if bn.startswith('stable')]
        trunk_builders_link = 'waterfall?builder='+'&amp;builder='.join(trunk_builders)
        stable_builders_link = 'waterfall?builder=' + '&amp;builder='.join(stable_builders)
        tr_b = False
        st_b = False
        data = ""
        data += "<table class='grid' id='latest_builds'>"
        for bn in all_builders:
            if (bn.startswith('stable')) and (not st_b):
                st_b = True
                data += "<table class='grid' id='stable_builds'>\n"
                data += "<tr class='grid-header'><td class='grid-cell'><span>Latest Stable</span></td><td class='grid-cell'><a href=%s>Stable Tests</a></td><td class='grid-cell'><a href='Changelog/5.0'>Changelog</a></td></tr><\n>"[:-3]%(stable_builders_link)
            if (bn.startswith('trunk')) and (not tr_b):
                tr_b = True
                data += "<tr id='trunk_builds'><td colspan='3'></td>"
                data += "<tr class='grid-header'><td class='grid-cell'><span>Latest Trunk</span></td><td class='grid-cell'><a href='%s'>Trunk Tests</a></td><td class='grid-cell'><a href='Changelog/trunk'>Changelog</a></td></tr><\n>"[:-3]%(trunk_builders_link)

            base_builder_url = base_builders_url + urllib.quote(bn, safe='')
            builder = status.getBuilder(bn)
            data += "<tr class='grid-row'>\n"
            data += '<td class="grid-cell"><a href="%s">%s</a></td>\n' \
                  % (base_builder_url, html.escape(bn))
            builds = list(builder.generateFinishedBuilds(map_branches(branches),
                                                         num_builds=1))
            if builds:
                b = builds[0]
                url = (base_builder_url + "/builds/%d" % b.getNumber())
                try:
                    label = b.getProperty("got_revision")
                except KeyError:
                    label = None
                if not label or len(str(label)) > 20:
                    label = "#%d" % b.getNumber()
                text = ['<a href="%s">%s</a>' % (url, label)]
                text.append(' '.join(b.getText()))
                box = Box(text, b.getColor(),
                        class_="LastBuild box %s" % build_get_class(b))
                data += box.td(class_="grid-cell",align="center")
            else:
                data += '<td class="grid-cell" align="center">no build</td>\n'
            current_box = ICurrentBox(builder).getBox(status)
            data += current_box.td(class_="grid-cell",align="center")
            data+='</tr>'

            builder_status = builder.getState()[0]
            if builder_status == "building":
                building = True
                online += 1
            elif builder_status != "offline":
                online += 1

        data += "</table></table>\n"
        if control is not None:
            if building:
                stopURL = "builders/_all/stop"
                data += make_stop_form(stopURL, True, "Builds")
            if online:
                forceURL = "builders/_all/force"
                data += make_force_build_form(forceURL, True)
        return data

class OpenObjectWebStatus(WebStatus):
    def __init__(self, http_port=None, distrib_port=None, allowForce=False):
        WebStatus.__init__(self, http_port=http_port, distrib_port=distrib_port, allowForce=allowForce)

    def setupUsualPages(self, *args, **kargs):
        WebStatus.setupUsualPages(self)
        self.putChild("buggraph", BugGraph())
        self.putChild("latestbuilds", LatestBuilds())




# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
