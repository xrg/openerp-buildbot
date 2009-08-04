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

class OpenObjectMailNotifier(MailNotifier):
    def __init__(self, username=None, password=None, port=2525, fromaddr=None, mode="failing", 
               categories=None, builders=None,
               addLogs=False, relayhost="localhost",
               subject="buildbot %(result)s in %(projectName)s on %(builder)s",
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

    def buildMessage(self, name, build, results):
        """Send an email about the result. Don't attach the patch as
        MailNotifier.buildMessage do."""

        projectName = self.status.getProjectName()
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

        change = list(ss.changes)
        m = Message()
        if self.html_body:
            self._body = self.get_HTML_mail(name,build_url,waterfall_url,failed_step,status_text,change[0])
        else:
            self._body = self.get_TEXT_mail(name,build_url,waterfall_url,failed_step,status_text,change[0])

        self.subject = self.subject % {
            'result': res,
            'projectName': c['projectName'],
            'builder': name.upper(),
            'reason': build.getReason(),
        }
        recipients = []
        for u in build.getInterestedUsers():
            recipients.append(u)
        return self.sendMessage(m, recipients)  

    def get_HTML_mail(self,name='',build_url=None,waterfall_url=None,failed_step='',status_text='',change=''):
        files = [f.encode('utf-8') for f in change.files]
        html_mail = """
           <html>
            <body>
            <var>
            Hello %s,<br/><br/>
            We are sorry to say that your last commit had broken %s (%s).
Can you please recheck your commit ?<br/><br/></var>
            <table bordercolor="black" align="left">
            <tr>
                <td><b>The details are as below:</b>
                    <tr>
                        <td align="left">Dashboard:</td>
                        <td align="left"><a href=%s>%s</a></td>
                    </tr>
                    <tr>
                        <td align="left">Run details:</td>
                        <td align="left"><a href=%s>%s</a></td>
                    </tr>
                    <tr>
                        <td align="left">Waterfall:</td>
                        <td align="left"><a href=%swaterfall?builder=%s>%swaterfall?builder=%s</a></td>
                    </tr>
                    <tr>
                        <td align="left">Step(s) Failed:</td>
                        <td align="left"><font color="red">%s</font></td>
                    </tr>
                    <tr>
                            <td align="left">Status:</td>
                            <td align="left"><font color="red">%s</font></td>
                            
                    </tr>
                    <tr>
                        <td><b>Commit History:</b>
                            <tr>
                                <td align="left">Changed by:</td>
                                <td align="left">%s</td>
                            </tr>
                            <tr>
                                <td align="left">Changed at:</td>
                                <td align="left">%s</td>
                            </tr>
                            <tr>
                                <td align="left">Branch:</td>
                                <td align="left"><a href=%s>%s</td>
                            </tr>
                            <tr>
                                <td align="left">Revision:</td>
                                <td align="left">%s</td>
                            </tr>
                            <tr>
                                <td align="left">Changed files:</td>
                                <td align="left"><font size="3">%s</font></td>
                            </tr>
                            <tr>
                                <td align="left">Comments:</td>
                                <td align="left"><font size="3">%s</font></td>
                            </tr>
                        </td>
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
                                <td>Great Achievements Start With Tiny Investments !</td>
                            </tr>
                       </td>
                    </tr>
                </td>
                </tr>
            </table>
            </body>
            </html>
            """ % (change.who[:change.who.index('<')],
                   c['projectName'],
                   name,
                   urllib.quote(waterfall_url, '/:'),
                   urllib.quote(waterfall_url, '/:'),
                   build_url,
                   build_url,
                   urllib.quote(waterfall_url, '/:'),
                   urllib.quote(name),
                   urllib.quote(waterfall_url, '/:'),
                   urllib.quote(name),
                   failed_step,
                   status_text,
                   change.who,
                   formatdate(change.when,usegmt=True),
                   change.branch,
                   change.branch,
                   change.revision,
                   '<br/>'.join(files),
                   change.comments)
        return html_mail  

    def get_TEXT_mail(self,name='',build_url=None,waterfall_url=None,failed_step='',status_text='',change=''):
        files = [f.encode('utf-8') for f in change.files]
        text_mail = """Hello %s,

We are sorry to say that your last commit had broken %s (%s).
Can you please recheck your commit ?

The details are as below:

Dashboard      : %s 
Run details    : %s
Waterfall      : %swaterfall?builder=%s
Step(s) Failed : %s
Status         : %s

Commit History:

Changed by     : %s
Changed at     : %s
Branch         : %s
Revision       : %s
Changed files  : %s
Comments       : %s


Regards,
OpenERP Quality Team

Great Achievements Start With Tiny Investments !
            """ % (change.who[:change.who.index('<')],
                   c['projectName'],
                   name,
                   urllib.quote(waterfall_url, '/:'),
                   build_url,
                   urllib.quote(waterfall_url, '/:'),
                   urllib.quote(name),
                   failed_step,
                   status_text,
                   change.who,
                   formatdate(change.when,usegmt=True),
                   change.branch,
                   change.revision,
                   '\n'.join(files),
                   change.comments)
        return text_mail  

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

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:

