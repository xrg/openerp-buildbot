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

class OpenObjectMailNotifier(MailNotifier):
    def __init__(self, username=None, password=None, port=2525, fromaddr=None, mode="failing", 
               categories=None, builders=None,
               addLogs=False, relayhost="localhost",
               subject="%(projectName)s %(builder)s %(result)s",
               lookup=None, extraRecipients=[],
               sendToInterestedUsers=True, reply_to=None, html_body=False, TLS=True, mail_watcher=[]):
        MailNotifier.__init__(self, fromaddr, mode, categories, builders,
                               addLogs, relayhost, subject, lookup,
                               extraRecipients, sendToInterestedUsers)
        self.reply_to = reply_to
        self._username = username
        self._password = password
        self._port = port
        self._body = ''
        self.html_body = html_body
        self.TLS = TLS
        self.mail_watcher = mail_watcher
        self.projectName = ''

    def buildMessage(self, name, build, results):
        """Send an email about the result. Don't attach the patch as
        MailNotifier.buildMessage do."""
        self.subject = '%(projectName)s %(builder)s %(result)s'
        self.projectName = self.status.getProjectName()
        ss = build.getSourceStamp()
        build_url = self.status.getURLForThing(build)
        waterfall_url = self.status.getBuildbotURL()
        if ss is None:
            source = "unavailable"
        else:
            source = ""
        if ss.branch:
            source += "[branch %s] " % ss.branch
        if ss.revision:
            source += ss.revision
        else:
            source += "" 

        t = build.getText()
        failed_step = []
        for i in range(1,len(t)):
          failed_step.append(t[i])
        if failed_step:
            failed_step = " ".join(failed_step)
        else:
            failed_step = ""

        if results == SUCCESS:
            status_text = "OpenERP Builbot succeeded !"
            res = "success"
        elif results == WARNINGS:
            status_text = "OpenERP Buildbot Had Warnings !"
            res = "warnings"
        else:
            status_text = "OpenERP Buildbot FAILED !" 
            res = "failure"
        
        self.subject = self.subject % {
            'result': res,
            'projectName': self.projectName,
            'builder': name,
        }


        recipients = []
        for u in build.getInterestedUsers():
            recipients.append(u)        
        changes = list(ss.changes)

        self._body=''
        for change in changes:
            m = Message()
            if self.html_body:
                self._body = self.get_HTML_mail(name,build,build_url,waterfall_url,failed_step,status_text,change)
            else:
                self._body = self.get_TEXT_mail(name,build,build_url,waterfall_url,failed_step,status_text,change)
            self.sendMessage(m, recipients)
        return True 

    def get_HTML_mail(self,name='',build = None,build_url=None,waterfall_url=None,failed_step='',status_text='',change=''):
        files_added = []
        files_modified = []
        files_renamed = []
        files_removed = [] 
        files_added_lbl = ''
        files_modified_lbl = ''
        files_renamed_lbl = ''
        files_removed_lbl = ''
        branch_link = ''
        rev_no = change.rev_no
        if change.revision:
            revision = "Revision: <b>%s</b><br />\n" % change.revision
        branch = ""
        if change.branch:
            i = change.branch.index('launchpad')
            branch_link = 'https://bazaar.' + change.branch[i:] + '/revision/' + str(rev_no) + '#'
            branch = change.branch
        if change.files_added:
            files_added_lbl = "<b>Added files: </b>\n"
            for file in change.files_added:
                file_link = branch_link + file
                files_added.append("<a href='%s'>%s</a>" % (file_link,file))
        if change.files_modified:
            files_modified_lbl = "<b>Modified files: </b>\n"
            for file in change.files_modified:
                file_link = branch_link + file
                files_modified.append("<a href='%s'>%s</a>" % (file_link, file))
        if change.files_renamed:
            files_renamed_lbl = "<b>Renamed files: </b>\n"
            for file in change.files_renamed:
                file_link = branch_link + file[1]
                files_renamed.append("%s  ==>  %s<br ><a href='%s'>%s</a>" % (file[0], file[1], file_link, file_link))
        if change.files_removed:
            files_removed_lbl = "<b>Removed files: </b>\n"
            for file in change.files_removed:
                file_link = branch_link + file
                files_removed.append("<a href='%s'>%s</a>" % (file_link,file))
        try:
            who_name = change.who.encode('utf-8')[:change.who.index('<')]
        except:
            who_name = change.who.encode('utf-8')        
        kwargs = { 'who_name'     : who_name,
                   'project_name' : self.projectName,
                   'name'   : name,
                   'waterfall_url' : urllib.quote(waterfall_url, '/:') ,
                   'build_url' : build_url,
                   'name_quote' : urllib.quote(name),
                   'failed_step' : failed_step,
                   'status_text' : status_text,
                   'who' : change.who.encode('utf-8'),
                   'when' : formatdate(change.when,usegmt=True),
                   'branch' : branch,
                   'revision' : change.revision,
                   'rev_no': rev_no,
                   'files_added'   : files_added_lbl + html.UL(files_added),
                   'files_modified' : files_modified_lbl + html.UL(files_modified),
                   'files_renamed' : files_renamed_lbl + html.UL(files_renamed),
                   'files_removed' : files_removed_lbl + html.UL(files_removed),
                   'comments': change.comments,
                   'reason':build.getReason()}
        return html_mail % kwargs 
                  
    def get_TEXT_mail(self,name='',build = None,build_url=None,waterfall_url=None,failed_step='',status_text='',change=''):
        files_added = []
        files_modified = []
        files_renamed = []
        files_removed = [] 
        files_added_lbl = ''
        files_modified_lbl = ''
        files_renamed_lbl = ''
        files_removed_lbl = ''
        branch_link = ''
        rev_no = change.rev_no
        if change.revision:
            revision = change.revision
        branch = ""
        if change.branch:
            i = change.branch.index('launchpad')
            branch_link = 'https://bazaar.' + change.branch[i:] + '/revision/' + str(rev_no) + '#'
            branch = change.branch
        if change.files_added:
            files_added_lbl = "\n\nAdded files: \n" + "---------------\n"
            for file in change.files_added:
                file_link = branch_link + file
                files_added.append(" * %s \n   ( %s )" % (file, file_link))
        if change.files_modified:
            files_modified_lbl = "\n\nModified files: \n" + "---------------\n"
            for file in change.files_modified:
                file_link = branch_link + file
                files_modified.append(" * %s \n   ( %s )" % (file, file_link))
        if change.files_renamed:
            files_renamed_lbl = "\n\nRenamed files: \n" + "---------------\n"
            for file in change.files_renamed:
                file_link = branch_link + file[1]
                files_renamed.append(" * %s  ==>  %s \n   ( %s )" % (file[0], file[1], file_link))
        if change.files_removed:
            files_removed_lbl = "\n\nRemoved files: \n" + "---------------\n"
            for file in change.files_removed:
                file_link = branch_link + file
                files_removed.append(" * %s \n   ( %s )" % (file, file_link))
        try:
            who_name = change.who.encode('utf-8')[:change.who.index('<')]
        except:
            who_name = change.who.encode('utf-8')
        kwargs = { 'who_name'     : who_name,
                   'project_name' : self.projectName,
                   'name'   : name,
                   'waterfall_url' : urllib.quote(waterfall_url, '/:'),
                   'build_url' : build_url,
                   'name_quote' : urllib.quote(name),
                   'failed_step' : failed_step,
                   'status_text' : status_text,
                   'who' : change.who.encode('utf-8'),
                   'when' : formatdate(change.when,usegmt=True),
                   'branch' : branch,
                   'revision' : revision,
                   'rev_no': rev_no,
                   'files_added'   : files_added_lbl + '\n'.join(files_added),
                   'files_modified' : files_modified_lbl + '\n'.join(files_modified),
                   'files_renamed' : files_renamed_lbl + '\n'.join(files_renamed), 
                   'files_removed' : files_removed_lbl + '\n'.join(files_removed),
                   'comments': change.comments,
                   'reason':build.getReason()}
        return text_mail % kwargs

    def sendMessage(self, m, recipients):

        email_to = recipients
        email_cc = self.mail_watcher
        email_from = self.fromaddr
        email_reply_to = self.reply_to
        smtp_user = self._username
        smtp_password = self._password
        port = str(self._port)
        smtp_server = self.relayhost
        subject = self.subject
        body = self._body
        subtype = 'plain'
        
        if self.html_body:
            subtype ='html'
        msg = MIMEText(body or '',_subtype=subtype, _charset='utf-8')
        
        msg['Subject'] = Header(subject.decode('utf8'), 'utf-8')
        msg['From'] = email_from
        msg['To'] = COMMASPACE.join(email_to)
        msg['Cc'] = COMMASPACE.join(email_cc)
        msg['Reply-To'] = email_reply_to
        msg['Date'] = formatdate(localtime=True,usegmt=True)
     
        try:
            s = smtplib.SMTP()
            s.connect(smtp_server,port)
            if smtp_user and smtp_password:
               if self.TLS: # deliberately start tls if using TLS
                   s.ehlo()
                   s.starttls() 
                   s.ehlo()
               s.login(smtp_user, smtp_password)
            s.sendmail(email_from, email_to + email_cc, msg.as_string())
            s.quit()
        except Exception, e:
            print "Exception:",e
        return True           

text_mail = """Hello %(who_name)s,
        
Your last commit had broken the branch %(project_name)s (%(name)s). Please recheck your code. The details of the build is provided here. If you think this can be a recursive problem, don't hesitate to write automated tests.

To get more information about how to integrate tests in your module, please read the documentation:
  * Automated Tests 

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
http://openobject.com"""

html_mail = """<html>
            <body>
            <var>
            Hello %(who_name)s,<br/><br/>
            We are sorry to say that your last commit had broken %(project_name)s (%(name)s).
Can you please recheck your commit ?<br/><br/></var>
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

