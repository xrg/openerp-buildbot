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

from buildbot.status.web.base import HtmlResource, path_to_builder, \
     path_to_build, css_classes
from buildbot.status.web.base import map_branches,Box,ICurrentBox,build_get_class,path_to_builder

from buildbot.status.web.baseweb import WebStatus
from buildbot.status.web import baseweb
from buildbot.status.web.build import StatusResourceBuild,BuildsResource
from buildbot.status.web.builder import StatusResourceBuilder, StatusResourceAllBuilders
from twisted.web import html
from twisted.python import log
import xmlrpclib
import pickle
import os
import re
from lxml import etree
import urllib, time
from buildbot import version, util
from openobject.buildstep import blame_severities
from openobject.tools import ustr

ROOT_PATH = '.'

def get_args_int(args, name, default=0):
    if args.get(name) is None:
        return default
    try:
        return int(args.get(name,[default,])[0])
    except (ValueError, TypeError):
        return default

_eml_re = re.compile(r'(.+) ?\<.+\> *$')

def reduce_eml(aeml):
    """Print just the name of a committer, from email address format"""
    global _eml_re
    try:
        m = _eml_re.match(aeml.strip())
        if m:
            return m.group(1)
        return repr(aeml)
    except Exception:
        pass
    return aeml

def last_change(ss, short=False):
    if ss.changes:
        return ss.changes[-1].getTime()
    else:
        return ''

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

    def __init__(self, template=False):
        HtmlResource.__init__(self)
        if not template:
            self.tpl_page = "latestbuilds.html"
        else:
            self.tpl_page = template

    def content(self, req, cxt):
        status = self.getStatus(req)
        building = False
        online = 0
        req.setHeader('Cache-Control', 'no-cache')
        # base_builders_url = "buildersresource/"
        base_builders_url = "builders/"
        cats = req.args.get('groups', False)
        if cats is not False:
            cats = cats.split(',')
        else:
            cats = None
        builders = req.args.get("builder", status.getBuilderNames(cats))
        branches = [b for b in req.args.get("branch", []) if b]
        num_cols = get_args_int(req.args, 'num', 5)
        
        cxt['num_cols'] = num_cols
        cxt['builders'] = []
        builders_grouped = {}
        groups_seq = {}  # sequence of groups
        for bn in builders:
            base_builder_url = base_builders_url + urllib.quote(bn, safe='')
            builder = status.getBuilder(bn)
            bld_props = status.botmaster.builders[bn].properties # hack into the structure
            categ = builder.category
            bname = bn
            if categ and bn.startswith(categ + '-'):
                bname = bname[len(categ)+1:]
            bname = html.escape(bname.replace('-',' ', 1))
            bldr_cxt = { 'name': bname , 'url': base_builder_url, 
                        'builds': [], 
                        'sequence': bld_props.get('sequence', 10) }
            if categ:
                if bld_props.get('group_public', True):
                    builders_grouped.setdefault(categ, []).append(bldr_cxt)
                    if 'group_seq' in bld_props:
                        groups_seq[categ] = bld_props['group_seq']
            else:
                cxt['builders'].append(bldr_cxt)

            
            # It is difficult to do paging here, because we are already iterating over the
            # builders, so won't have the same build names or rev-ids.
            builds = list(builder.generateFinishedBuilds(map_branches(branches), num_builds=num_cols))
            # builds.reverse()
            
            bldr_cxt['builds'] = []
            for build in builds[:num_cols]:
                url = (base_builder_url + "/builds/%d" % build.getNumber())
                build_cxt = {'url': url}
                bldr_cxt['builds'].append(build_cxt)
                try:
                    ss = build.getSourceStamp()
                    commiter = ""
                    if list(build.getResponsibleUsers()):
                        for who in build.getResponsibleUsers():
                            commiter += "%s" % html.escape(reduce_eml(who))
                    else:
                        commiter += "No Commiter Found !"
                    if ss.revision:
                        revision = ss.revision
                    label = '%s-%s: %s' % (str(revision), commiter, ''.join(build.text))
                except Exception:
                    label = None
                if not label:
                    label = "#%d" % build.getNumber()
                tftime = time.strftime('%a %d, %H:%M:%S', time.localtime(build.getTimes()[1]))
                ttitle = 'Test at: %s\n%s' %(ustr(tftime), html.escape(ustr(build.getReason())))
                class_b = "build%s" % build_get_class(build)
                
                build_cxt.update({ 'label': label, 'commiter': commiter,
                                'tftime': tftime, 'ttitle': ttitle,
                                'last_t': ustr(last_change(ss, True)),
                                'class_b': class_b })

            
            builder_status = builder.getState()[0]
            bldr_cxt['status'] = builder_status
        
        # Now, sort the builders and grouped:
        cxt['builders'].sort(key=lambda bld: bld['sequence'])
        for bldrs in builders_grouped.values():
            bldrs.sort(key=lambda bld: bld['sequence'])

        cxt['builders_grouped'] = [] # will be list of tuples
        for gk, bldrs in builders_grouped.items():
            cxt['builders_grouped'].append((groups_seq.get(gk,10), gk, bldrs))
            
        template = req.site.buildbot_service.templates.get_template(self.tpl_page)
        return template.render(**cxt)

class OOStatusHelper(object):
    """ Helper functions for OpenObjectStatusResourceBuild, OpenObjectStatusResourceBuilder
    """
    _base_logs = ('stdio', 'stderr', 'bqi.rest', 'bqi.rest.blame', 
                    'server.out', 'server.err',
                    'interrupt', 'err.html', 'err.text')
                    
    _blame_re = re.compile(r'\[(.+)\]\: ')

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
        found = False
        found_class = None
        found_sev = 0
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
                data += ("<li><a href=\"%s\">%s</a>\n" %
                            (logurl, logfile.getName()))
                if name == 'OpenERP-Test' \
                    and logname not in ('stdio', 'server.out', 'server.err') \
                    and not logname.endswith('.qlog'):
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
                        blame_txt = blog.getText()
                        # We inspect the first line (already sorted) of the 
                        # blame to locate top severity
                        bm = self._blame_re.search(blame_txt.split('\n')[0])
                        if bm: #
                            if blame_severities.get(bm.group(1), 3) > found_sev:
                                # This blame is worse than the previous ones
                                found_sev = blame_severities.get(bm.group(1), 3)
                                found_class = bm.group(1) or 'error'
                        else:
                            # Default severity, at blame line, is error
                            if found_sev < 3:
                                found_sev = 3
                                found_class = 'error'
                        btitle = html.escape(blame_txt)
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
                    data += '<span class="%s"> %s</span>'%(color,text)
                else:
                    data += '<span>%s</span>'%(text)

        if not found:
            data += '<span>n/a</span>'
        if found_class:
            data = ('<td class="grid-cell-%s">' % (found_class,)) + data + '</td>\n'
        else:
            data = '<td class="grid-cell-ok">' + data + '</td>\n'
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
        data += ("<h1>Builder %s: Build #%d</h1>"
                 % (builder_name, b.getNumber()))
        ss = b.getSourceStamp()
        commiter = ""
        
        (t_start, t_finish) = b.getTimes()
        data += '<p>Started at: %s, finished at %s</p>' % \
            (time.strftime('%a %d, %H:%M:%S', time.localtime(t_start)), 
            time.strftime('%a %d, %H:%M:%S', time.localtime(t_finish)))
        
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
            data += "</tr>\n"
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
            data += '<table border="1" class="grid"><tr><th>Commiter <br> / Steps</th>'
        for build in builds:
            ss = build.getSourceStamp()
            commiter = ""
            revision = '?'
            hback = ''
            hnext = ''
            if list(build.getResponsibleUsers()):
                for who in build.getResponsibleUsers():
                    commiter += "%s" % html.escape(reduce_eml(who))
            else:
                commiter += "No Commiter Found !"
            if ss.revision:
                revision = html.escape(str(ss.revision))
            
            data += "<th><span>"
            
            url = (base_builder_url + "/builds/%d" % build.getNumber())
            data += '<a href="%s">#%d rev: %s</a> %s<br/>%s' % \
                    (url, build.getNumber(), revision,
                    last_change(ss), commiter)

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
        # self.putChild("buggraph", BugGraph())
        self.putChild("", LatestBuilds("root.html"))
        self.putChild("latestbuilds", LatestBuilds())
        self.putChild("latestbuildsb", LatestBuilds("latestbuilds_bare.html"))
        # self.putChild("buildersresource", OpenObjectBuildersResource())



# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
