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

from buildbot.status.web.base import HtmlResource, path_to_builder
from buildbot.status.web.base import path_to_slave, path_to_change
from buildbot.status.web.base import map_branches, build_get_class

from buildbot.status.web.builder import BuildersResource

from buildbot.status.web.baseweb import WebStatus
from buildbot.status.web.builder import StatusResourceBuilder
from twisted.web import html
from twisted.python import log
import pickle
import re
import urllib, time
from buildbot import version, util
from twisted.internet import defer
from openerp_libclient.tools import ustr

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

def revision_id(ss):
    if ss.revision:
        return str(ss.revision)
    elif ss.changes:
        ch = ss.changes[0]
        if ch.revision:
            return str(ch.revision)
        elif 'hash' in ch.properties:
            return ch.properties['hash'][:12]
    return '-'

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
        # TODO: deprecate!
        datasets=['',[]]
        try:
            fp = open(ROOT_PATH + '/bugs.pck','a+')
            datasets = pickle.load(fp)
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
        # building = False
        # online = 0
        req.setHeader('Cache-Control', 'no-cache')
        # base_builders_url = "buildersresource/"
        base_builders_url = "builders/"
        cats = req.args.get('groups', False)
        if cats is not False:
            cats = cats.split(',')
        else:
            cats = None
        builders = map(status.getBuilder, req.args.get("builder", status.getBuilderNames(cats)))
        branches = [b for b in req.args.get("branch", []) if b]
        num_cols = get_args_int(req.args, 'num', 5)
        
        def __builder_lastfinish(bn):
            "Get the most recent time a builder has finished a build"
            fb = bn.getLastFinishedBuild()
            if fb:
                return fb.getTimes()[1]
            else:
                return 0

        builders.sort(key=__builder_lastfinish, reverse=True)
        # put the most recent builders on top. This may fetch one build per
        # builder, but is still much better than fetching all of them.

        num_builders = get_args_int(req.args, "nbuilders", 25)
        cxt['num_cols'] = num_cols
        cxt['builders'] = []
        builders_grouped = {}
        groups_seq = {}  # sequence of groups
        groups_pub = {}  # public flag of groups
        for builder in builders:
            bn = builder.name
            base_builder_url = base_builders_url + urllib.quote(bn, safe='')
            categ = builder.category
            if categ and len(builders_grouped.get(categ,[])) >= num_builders:
                continue
            bld_props = status.botmaster.builders[bn].properties # hack into the structure
            bname = bn
            if categ and bn.startswith(categ + '-'):
                bname = bname[len(categ)+1:]
            bname = html.escape(bname.replace('-',' ', 1))
            bldr_cxt = { 'name': bname , 'url': base_builder_url, 
                        'builds': [], 
                        'sequence': bld_props.get('sequence', 10),
                        'last_tstamp': 0}
            if categ:
                groups_pub[categ] = bld_props.get('group_public', True)
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
                    revision = "-"
                    if list(build.getResponsibleUsers()):
                        for who in build.getResponsibleUsers():
                            commiter += "%s" % html.escape(reduce_eml(who))
                    else:
                        commiter += "No Commiter Found !"
                    revision = revision_id(ss)
                    label = '%s-%s: %s' % (revision, commiter, ''.join(build.text))
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
                if build.getTimes()[1] > bldr_cxt['last_tstamp']:
                    bldr_cxt['last_tstamp'] = build.getTimes()[1]

            builder_status = builder.getState()[0]
            bldr_cxt['status'] = builder_status
        
        # Now, sort the builders and grouped:
        now = time.time()
        cxt['builders'].sort(key=lambda bld: (bld['sequence'], now - bld['last_tstamp']))
        for bldrs in builders_grouped.values():
            bldrs.sort(key=lambda bld: (bld['sequence'], now - bld['last_tstamp']))

        cxt['builders_grouped'] = [] # will be list of tuples
        for gk, bldrs in builders_grouped.items():
            cxt['builders_grouped'].append(
                    { 'group_name': gk,
                      'group_seq': groups_seq.get(gk,10),
                      'public': groups_pub.get(gk,True),
                      'builders': bldrs
                    })
            cxt['builders_grouped'].sort(key=lambda bgrp: bgrp['group_seq'])
            
        template = req.site.buildbot_service.templates.get_template(self.tpl_page)
        return template.render(**cxt)


class OOBuildersResource(BuildersResource):

    def getChild(self, path, req):
        s = self.getStatus(req)
        if path in s.getBuilderNames():
            builder_status = s.getBuilder(path)
            return BuildsMatrix(builder_status)

        return BuildersResource.getChild(self, path, req)

class BuildsMatrix(StatusResourceBuilder):
    """Through this page, the tests of several builds may be compared
    """
    title = "Matrix of Builds"

    def __init__(self, builder_status, template=False):
        StatusResourceBuilder.__init__(self, builder_status)
        if not template:
            self.tpl_page = "buildermatrix.html"
        else:
            self.tpl_page = template


    def get_line_values(self, req, build, include_builder=True):
        ''' Append more information to the base.BuildLineMixIn ones
        '''
        # builder_name = build.getBuilder().getName()
        # results = build.getResults()
        
        values = super(BuildsMatrix, self).get_line_values(req=req, build=build, 
                        include_builder=include_builder)
        
        # now, append the tests ;)
        
        values['test_results'] = {}
        values['test_result_order'] = []
        values['class_b'] = "build%s" % build_get_class(build)
        for tres in build.getTestResultsOrd():
            name0 = tres.name and tres.name[0] or ''
            if name0 not in values['test_result_order']:
                values['test_result_order'].append(name0)
            values['test_results'].setdefault(name0,[]).append( {
                                'name': tres.name ,
                                'results': tres.results, 
                                'text': tres.text })
        # TODO: perhaps filter?
        return values

    @defer.deferredGenerator
    def content(self, req, cxt):
        """ Mainly the same with parent class, but enumerates test results, too """
        b = self.builder_status

        cxt['name'] = b.getName()
        req.setHeader('Cache-Control', 'no-cache')
        slaves = b.getSlaves()
        connected_slaves = [s for s in slaves if s.isConnected()]

        cxt['current'] = [self.builder(x, req) for x in b.getCurrentBuilds()]

        cxt['pending'] = []
        wfd = defer.waitForDeferred(
        b.getPendingBuildRequestStatuses())
        yield wfd
        statuses = wfd.getResult()
        for pb in statuses:
            changes = []

            wfd = defer.waitForDeferred(
                    pb.getSourceStamp())
            yield wfd
            source = wfd.getResult()

            changes = []

            if source.changes:
                for c in source.changes:
                    changes.append({ 'url' : path_to_change(req, c),
                                            'who' : c.who})
            if source.revision:
                reason = source.revision
            else:
                reason = "no changes specified"

            cxt['pending'].append({
                'when': time.strftime("%b %d %H:%M:%S", time.localtime(pb.getSubmitTime())),
                'delay': util.formatInterval(util.now() - pb.getSubmitTime()),
                'reason': reason,
                'id': pb.brid,
                'changes' : changes
                })

        numbuilds = int(req.args.get('numbuilds', ['5'])[0])
        recent = cxt['recent'] = []
        tr_names = cxt['test_results_order'] = []
        for build in b.generateFinishedBuilds(num_builds=int(numbuilds)):
            lvals = self.get_line_values(req, build, False)
            recent.append(lvals)
            for trn in lvals.get('test_result_order',[]):
                if trn not in tr_names:
                    tr_names.append(trn)

        sl = cxt['slaves'] = []
        connected_slaves = 0
        for slave in slaves:
            s = {}
            sl.append(s)
            s['link'] = path_to_slave(req, slave)
            s['name'] = slave.getName()
            c = s['connected'] = slave.isConnected()
            if c:
                s['admin'] = unicode(slave.getAdmin() or '', 'utf-8')
                connected_slaves += 1
        cxt['connected_slaves'] = connected_slaves

        cxt['authz'] = self.getAuthz(req)
        cxt['builder_url'] = path_to_builder(req, b)

        template = req.site.buildbot_service.templates.get_template(self.tpl_page)
        yield template.render(**cxt)

class OpenObjectWebStatus(WebStatus):
    compare_attrs = ["http_port", "distrib_port",]
    def __init__(self, http_port=None, distrib_port=None, allowForce=False):
        WebStatus.__init__(self, http_port=http_port, distrib_port=distrib_port, 
                allowForce=allowForce, provide_feeds=['rss', 'atom'])

    def setupUsualPages(self, *args, **kwargs):
        WebStatus.setupUsualPages(self, *args, **kwargs)
        # self.putChild("buggraph", BugGraph())
        self.putChild("", LatestBuilds("root.html"))
        self.putChild("latestbuilds", LatestBuilds())
        self.putChild("latestbuildsb", LatestBuilds("latestbuilds_bare.html"))
        self.putChild("builders", OOBuildersResource())

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
