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

from buildbot.status.mail import MailNotifier
from buildbot.status import base
from email.Message import Message
import urllib
import smtplib    
from email.MIMEText import MIMEText
from email.MIMEMultipart import MIMEMultipart
from email.Header import Header
from email.Utils import formatdate, COMMASPACE
from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS
from twisted.web import html
from openobject import tools

class OpenObjectMailNotifier(MailNotifier):
    def __init__(self, projectURL="http://localhost/", reply_to=None,
                    mode="failing", html_body=False, **kwargs):
        extraHeaders = {}
        if reply_to:
            extraHeaders['Reply-To'] = reply_to
        MailNotifier.__init__(self, mode=mode, extraHeaders=extraHeaders, **kwargs)
        #         messageFormatter=defaultMessage

        self.projectName = 'OpenERP'
        self.projectURL=projectURL
        self.html_body = html_body
  
    def buildMessage(self, name, build, results):
        """Send an email about the result. Don't attach the patch as
        MailNotifier.buildMessage do."""
        ss = build.getSourceStamp()
        waterfall_url = self.projectURL
        build_url = "%sbuilders/%s/builds/%s" % ( self.projectURL,
                        build.builder.name, build.number)
        if ss is None:
            source = "unavailable"
        else:
            source = ""

        if ss.branch:
            source += "[branch %s] " % ss.branch
        if ss.revision:
            source += str(ss.revision)
        else:
            source += "" 

        failed_step = []
        t = build.getText()
        for i in range(1,len(t)):
          failed_step.append(t[i])
        if failed_step:
            failed_step = " ".join(failed_step)
        else:
            failed_step = ""

        failed_tests = []
        for tr in build.getTestResultsOrd():
            if tr.results == SUCCESS and self.mode != 'all':
                continue
            tr_url = "%s/tests/%s" % ( build_url, '.'.join(tr.name))
            failed_tests.append(('.'.join(tr.name), tr_url, tr.text))
            
        if results == SUCCESS:
            status_text = "OpenERP Builbot succeeded !"
            res = "success"
            test_reasoning = reasoning_success
        elif results == WARNINGS:
            status_text = "OpenERP Buildbot Had Warnings !"
            res = "warnings"
            test_reasoning = reasoning_warnings
        else:
            status_text = "OpenERP Buildbot FAILED !" 
            res = "failure"
            test_reasoning = reasoning_failure

        to_recipients = set()
        cc_recipients = set()
        for cu in build.getInterestedUsers():
            to_recipients.add(cu)

        if self.sendToInterestedUsers and to_recipients:
            cc_recipients.update(self.extraRecipients)
        else:
            to_recipients.update(self.extraRecipients)

        changes = list(ss.changes)
        for change in changes:
            mtype = 'plain'
            if self.html_body:
                mtype = 'html'
                body = self.get_HTML_mail(name,build,build_url,waterfall_url,failed_step, failed_tests, status_text, test_reasoning, change)
            else:
                body = self.get_TEXT_mail(name,build,build_url,waterfall_url,failed_step, failed_tests, status_text, test_reasoning, change)
                
            m = self.createEmail({'body': body, 'type': mtype},
                    builderName=build.builder.name, projectName=self.projectName, 
                    results=results, build=build)

            m['To'] = ", ".join(to_recipients)
            if cc_recipients:
                m['CC'] = ", ".join(cc_recipients)

            self.sendMessage(m, list(to_recipients| cc_recipients))
        return True

    def get_HTML_mail(self,name='',build=None, build_url=None, waterfall_url=None,
                    failed_step='', failed_tests=None, status_text='', test_reasoning='', change=''):
        files_added = []
        files_modified = []
        files_renamed = []
        files_removed = [] 
        files_added_lbl = ''
        files_modified_lbl = ''
        files_renamed_lbl = ''
        files_removed_lbl = ''
        failed_tests_data = ''
        branch_link = ''

        rev_no = change.revision
        if change.hash:
            revision = "Revision: <b>%s</b><br />\n" % change.hash
        branch = ""
        try:
            if change.branch:
                i = change.branch.index('launchpad')
                branch_link = 'https://bazaar.' + change.branch[i:] + '/revision/' + str(rev_no) + '#'
                branch = change.branch
        except Exception: pass

        if failed_tests:
            failed_tests_data = "<ul>"
            for ftn, ft_url, ft_text in failed_tests:
                failed_tests_data += '<li><a href="%s">%s</a>: %s</li>\n' % \
                        (ft_url, ftn, ft_text)
            failed_tests_data += '</ul>\n'

        try:
            who_name = change.who[:change.who.index('<')]
        except:
            who_name = change.who

        kwargs = { 'who_name'     : tools._to_unicode(who_name),
                   'project_name' : self.projectName,
                   'name'   : name,
                   'waterfall_url' : urllib.quote(waterfall_url, '/:') ,
                   'build_url' : build_url,
                   'name_quote' : urllib.quote(name),
                   'failed_step' : failed_step,
                   'status_text' : status_text,
                   'who' : tools._to_unicode(change.who),
                   'when' : formatdate(change.when,usegmt=True),
                   'branch' : branch,
                   'revision' : change.revision,
                   'rev_no': rev_no,
                   'files_added'   : files_added_lbl + html.UL(files_added),
                   'files_modified' : files_modified_lbl + html.UL(files_modified),
                   'files_renamed' : files_renamed_lbl + html.UL(files_renamed),
                   'files_removed' : files_removed_lbl + html.UL(files_removed),
                   'failed_tests_data': failed_tests_data,
                   'comments': change.comments,
                   'reason':build.getReason()}
        kwargs['test_reasoning'] = test_reasoning % kwargs

        return tools._to_decode(html_mail % kwargs) 
                  
    def get_TEXT_mail(self,name='',build = None,build_url=None, waterfall_url=None,
                    failed_step='', failed_tests=None, status_text='', test_reasoning='', change=''):
        files_added = []
        files_modified = []
        files_renamed = []
        files_removed = [] 
        files_added_lbl = ''
        files_modified_lbl = ''
        files_renamed_lbl = ''
        files_removed_lbl = ''
        failed_tests_data = ''
        branch_link = ''

        rev_no = change.revision
        if change.hash:
            revision = change.hash
        branch = ""
        try:
            if change.branch:
                i = change.branch.index('launchpad')
                branch_link = 'https://bazaar.' + change.branch[i:] + '/revision/' + str(rev_no) + '#'
                branch = change.branch
        except Exception: pass
        
        if failed_tests:
            failed_tests_data = "\nTest results:\n--------------\n"
            for ftn, ft_url, ft_text in failed_tests:
                failed_tests_data += '%s: %s\n%s\n\n' % \
                        (ftn, ft_url, ft_text)
        try:
            who_name = change.who[:change.who.index('<')]
        except:
            who_name = change.who

        kwargs = { 'who_name'     : tools._to_unicode(who_name),
                   'project_name' : self.projectName,
                   'name'   : name,
                   'waterfall_url' : urllib.quote(waterfall_url, '/:'),
                   'build_url' : build_url,
                   'name_quote' : urllib.quote(name),
                   'failed_step' : failed_step,
                   'status_text' : status_text,
                   'who' : tools._to_unicode(change.who),
                   'when' : formatdate(change.when,usegmt=True),
                   'branch' : branch,
                   'revision' : revision,
                   'rev_no': rev_no,
                   'files_added'   : files_added_lbl + '\n'.join(files_added),
                   'files_modified' : files_modified_lbl + '\n'.join(files_modified),
                   'files_renamed' : files_renamed_lbl + '\n'.join(files_renamed), 
                   'files_removed' : files_removed_lbl + '\n'.join(files_removed),
                   'failed_tests_data': failed_tests_data,
                   'comments': change.comments,
                   'reason':build.getReason()}
        kwargs['test_reasoning'] = test_reasoning % kwargs
        return tools._to_decode(text_mail % kwargs)


text_mail = """Hello %(who_name)s,
        
%(test_reasoning)s

The details are as below:
=========================

Dashboard      : %(waterfall_url)s 
Run details    : %(build_url)s
Waterfall      : %(waterfall_url)swaterfall?builder=%(name_quote)s
Step(s) Failed : %(failed_step)s
Status         : %(status_text)s

Reason Of Failure:
-----------------
  %(reason)s

%(failed_tests_data)s

Commit History:
---------------

Changed by     : %(who)s
Changed at     : %(when)s
Branch         : %(branch)s
Revision       : %(revision)s
Revision No.   : %(rev_no)s
%(files_added)s%(files_modified)s%(files_renamed)s%(files_removed)s

Comments       : 
%(comments)s



Regards,
OpenERP Quality Team
http://openobject.com
"""

reasoning_success = """Your commit has passed our tests for %(project_name)s (%(name)s)."""

reasoning_warnings = """Your commit has produced warnings at our tests for %(project_name)s (%(name)s).
Can you please consider improving your commit ? """

reasoning_failure = """We are sorry to say that your last commit had broken %(project_name)s (%(name)s).
Can you please recheck your commit ? """

html_mail = """<html>
            <body>
            <var>
            Hello %(who_name)s,<br/><br/>
            %(test_reasoning)s<br/><br/></var>
            <table bordercolor="black" align="left">
            <tr>
                <td><b>The details are as below:</b>
                    <tr>
                        <td align="left">Dashboard:</td>
                        <td align="left"><a href=%(waterfall_url)s>%(waterfall_url)s</a></td>
                    </tr>
                    <tr>
                        <td align="left">Run details:</td>
                        <td align="left"><a href=%(build_url)s>%(build_url)s</a></td>
                    </tr>
                    <tr>
                        <td align="left">Waterfall:</td>
                        <td align="left"><a href=%(waterfall_url)swaterfall?builder=%(name_quote)s>%(waterfall_url)swaterfall?builder=%(name_quote)s</a></td>
                    </tr>
                    <tr>
                        <td align="left">Step(s) Failed:</td>
                        <td align="left"><font color="red">%(failed_step)s</font></td>
                    </tr>
                    <tr>
                            <td align="left">Status:</td>
                            <td align="left"><font color="red">%(status_text)s</font></td>
                            
                    </tr>
                    <tr>
                            <td align="left">Test Results:</td>
                            <td align="left">%(failed_tests_data)s</td>
                            
                    </tr>
                    <tr>
                        <td align="left">Reason Of Failure:</td>
                        <td align="left"><font size="3">%(reason)s</font></td>
                    </tr>
                    <tr>
                        <td><b>Commit History:</b></td>
                    <tr>
                        <td align="left">Changed by:</td>
                        <td align="left">%(who)s</td>
                    </tr>
                    <tr>
                        <td align="left">Changed at:</td>
                        <td align="left">%(when)s</td>
                    </tr>
                    <tr>
                        <td align="left">Branch:</td>
                        <td align="left"><a href='%(branch)s'>%(branch)s</a></td>
                    </tr>
                    <tr>
                        <td align="left">Revision:</td>
                        <td align="left">%(revision)s</td>
                    </tr>
                    <tr>
                        <td align="left">Revision No:</td>
                        <td align="left">%(rev_no)s</td>
                    </tr>
                    <tr>
                        <td align="left">%(files_added)s</td>
                    </tr>
                    <tr>
                        <td align="left">%(files_modified)s</td>
                    </tr>
                    <tr>
                        <td align="left">%(files_renamed)s</td>
                    </tr>
                    <tr>
                        <td align="left">%(files_removed)s</td>
                    </tr>
                    <tr>
                        <td align="left">Comments:</td>
                        <td align="left"><font size="3">%(comments)s</font></td>
                    </tr>
                    <tr></tr>
                    <tr></tr>
                    <tr></tr>
                    <tr></tr>
                    <tr></tr>
                    <tr>
                        <td>Regards,
                            <tr>
                                <td><font color="red">OpenERP Quality Team</font></td>
                            </tr>
                            <tr>
                                <td>http://openobject.com</td>
                            </tr>
                       </td>
                    </tr>
            </table>
            </body>
            </html>"""
     
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:

