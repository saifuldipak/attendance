from smtplib import SMTP, SMTPException
from email import message
from datetime import datetime
from socket import timeout

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

    action = kwargs['action']
    application = kwargs['application']
    if type == 'leave' or type =='attendance':
        if not (action or application):
            return 'If "type" argument is "leave" or "attendance", you must provide "action" and\
                     "application" argument'
    
    
    #creating receiver email list
    receivers = [receiver]
    cc1 = kwargs['cc1']
    if cc1:
        receivers.append(cc1)
    cc2 = kwargs['cc2']
    if cc2:
        receivers.append(cc2)

    #creating email subject
    if type == 'leave':
        subject = f'[{application.employee.fullname}] {application.type} leave application\
                     {application.id}] {action}'
    elif type == 'attendance':
        subject = f'[{application.employee.fullname}] Attendance application [{application.id}]\
                     {action}'
    elif type == 'reset':
        subject = 'Password reset'
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
        Details: http://localhost:5000/
        '''
    
    #creating email body for password reset
    extra = kwargs['extra']
    if type == 'reset':
        if not extra:
            return 'If "type" argument is "reset", you must provide "extra" argument'
        else:
            body = f'New password : {extra}'
    
    #creating email with header and body
    msg = message.Message()
    msg.add_header('from', sender)
    msg.add_header('to', receiver)
    
    if type == 'leave' or type == 'attendance':
        msg.add_header('cc', cc1)
        msg.add_header('cc', cc2)
    
    msg.add_header('date', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    msg.add_header('subject', subject)
    msg.set_payload(body)
    
    #sending messaging 
    return send_message(host, port, sender, receivers, msg)