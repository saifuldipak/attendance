from smtplib import SMTP, SMTPException
from email import message
from datetime import datetime
from socket import timeout
from flask import current_app

#connecting to SMTP server and sending message
def send_message(host, port, sender, receivers, msg):
    
    #connecting to host
    try: 
        server = SMTP(host=host, port=port, local_hostname=None, timeout=5)
    except timeout:
        return 'SMTP server not reachable'
    except SMTPException as e:
        return e
    
    #sending message
    try:
        server.send_message(msg, from_addr=sender, to_addrs=receivers)
    except SMTPException as e:
        return e
    else:
        server.quit()


#send mail for leave or attendance application submission, approval and password reset
def send_mail(host, port, sender, receiver, type, **kwargs):
    
    #checking if required arguments are passed or not
    if not (host or port or sender or receiver or type):
        return 'You must provide host, port, sender email, receiver email and type arguments'
    
    if 'action' in kwargs:
        action = kwargs['action']
    
    if 'application' in kwargs:
        application = kwargs['application']
    
    if type == 'leave' or type =='attendance':
        if not (action or application):
            return 'If "type" argument is "leave" or "attendance", you must provide "action" and\
                     "application" argument'
    
    
    #creating receiver email list
    receivers = [receiver]
    
    if 'cc1' in kwargs:
        receivers.append(kwargs['cc1'])
    
    if 'cc2' in kwargs:
        receivers.append(kwargs['cc2'])
    
    if 'cc3' in kwargs:
        receivers.append(kwargs['cc3'])

    #creating email subject
    if type == 'leave':
        subject = f"[{application.employee.fullname}] {application.type} leave application id -'{application.id}' {action}"
    elif type == 'attendance':
        subject = f"[{application.employee.fullname}] Attendance application id - '{application.id}' {action}"
    elif type == 'reset':
        subject = 'Your Attendance app password has been reset'
    else:
        return 'Type arguement must be "leave, attendance or reset"'

    #creating email body for leave and attendance
    if type == 'leave' or type == 'attendance':
        if type == 'leave':
            name = f'Leave: {application.type}'

        if type == 'attendance':
            name = f'Attendance: {application.type}'

        body = f'''
        Application ID: {application.id}
        Name: {application.employee.fullname}
        {name}
        Start date: {application.start_date}
        End date: {application.end_date}
        Remark: {application.remark}
        Status: {application.status}
        '''
    
    #creating email body for password reset
    if type == 'reset':
        if 'extra' not in kwargs:
            return 'If "type" argument is "reset", you must provide "extra" argument'
        else:
            body = f"New password : {kwargs['extra']}"
    
    #creating email with header and body
    msg = message.Message()
    msg.add_header('from', sender)
    msg.add_header('to', receiver)
    
    if type == 'leave' or type == 'attendance':
        if 'cc1' in kwargs:
            msg.add_header('cc', kwargs['cc1'])
 
        if 'cc2' in kwargs:
            msg.add_header('cc', kwargs['cc2'])
        
        if 'cc3' in kwargs:
            msg.add_header('cc', kwargs['cc3'])
    
    msg.add_header('date', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    msg.add_header('subject', subject)
    msg.set_payload(body)
    
    #sending messaging 
    return send_message(host, port, sender, receivers, msg)


def send_mail2(sender, receiver, type, **kwargs):
    
    #checking if required arguments are passed or not
    if not (sender or receiver or type):
        return 'You must provide host, port, sender email, receiver email and type arguments'
    
    if 'action' in kwargs:
        action = kwargs['action']
    
    if 'application' in kwargs:
        application = kwargs['application']
    
    if type == 'leave' or type =='attendance':
        if not (action or application):
            return 'If "type" argument is "leave" or "attendance", you must provide "action" and\
                     "application" argument'
    
    #creating receiver email list
    receivers = [receiver]
    
    if 'cc' in kwargs:
        for cc in kwargs['cc']:
            receivers.append(cc)

    #creating email subject
    if type == 'leave':
        subject = f"[{application.employee.fullname}] {application.type} leave application id -'{application.id}' {action}"
    elif type == 'attendance':
        subject = f"[{application.employee.fullname}] {application.type} attendance application id - '{application.id}' {action}"
    elif type == 'reset':
        subject = 'Your Attendance app password has been reset'
    else:
        msg = f'Unknown type {type}'
        return msg

    #creating email body for leave and attendance
    if type == 'leave' or type == 'attendance':
        if type == 'leave':
            name = f'Leave: {application.type}'

        if type == 'attendance':
            name = f'Attendance: {application.type}'

        body = f'''
        Application ID: {application.id}
        Name: {application.employee.fullname}
        {name}
        Start date: {application.start_date}
        End date: {application.end_date}
        Remark: {application.remark}
        Status: {application.status}
        '''
    
    #creating email body for password reset
    if type == 'reset':
        if 'extra' not in kwargs:
            return 'If "type" argument is "reset", you must provide "extra" argument'
        else:
            body = f"New password : {kwargs['extra']}"
    
    #creating email with header and body
    msg = message.Message()
    msg.add_header('from', sender)
    msg.add_header('to', receiver)
    
    if type == 'leave' or type == 'attendance':
        if 'cc' in kwargs:
            cc_list = ','.join(kwargs['cc'])
            msg.add_header('cc', cc_list)
    
    msg.add_header('date', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    msg.add_header('subject', subject)
    msg.set_payload(body)
    
    #connecting to host
    try: 
        server = SMTP(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], local_hostname=None, timeout=5)
    except timeout:
        return 'SMTP server not reachable'
    except SMTPException as e:
        return e
    
    #sending message
    try:
        server.send_message(msg, from_addr=sender, to_addrs=receivers)
    except SMTPException as e:
        return e
    else:
        server.quit()
        