from flask import Blueprint, flash, render_template, url_for, session, redirect, current_app
from .auth import login_required
from .db import db, Applications
from .functions import check_authorization, check_attendance_summary, check_available_leave, get_emails, return_leave, delete_files
from .mail import send_mail2

application = Blueprint('application', __name__)

@application.route('/application/<action>/<application_id>')
@login_required
def process(action, application_id=None):
    if action not in ('approve', 'cancel', 'submit'):
        current_app.logger.error('<action> value %s unknown, session user %s', action, session['username'])
        flash('Failed to execute the function', category='error')
        return render_template('base.html')
    
    application = Applications.query.filter_by(id=application_id).one()

    if session['empid'] == application.empid:
        application_for = 'self'
    elif session['role'] == 'Head':
        application_for = 'department'
    elif session['role'] in ('Supervisor', 'Manager'):
        application_for = 'team'

    if session['empid'] != application.empid:
        has_authorization = check_authorization(application)
        if not has_authorization:
            current_app.logger.error(' process(): "%s" trying to approve application "%s"', session['username'], application_id)
            msg = f'You are not authorized to "{action}" this application "{application_id}"'
            flash(msg, category='error')
            return render_template(url_for('leave.search_application', application_for=application_for))
    else:
        if action == 'approve':
            current_app.logger.error(' process(): "%s" trying to approve own application "%s"', session['username'], application_id)
            flash('You cannot approve your own application', category='error')
            return render_template(url_for('leave.search_application', application_for=application_for))
        
        if action == 'cancel':
            if application.status.lower() == 'approved':
                current_app.logger.error(' process(): "%s" trying to cancel own approved application "%s"', session['username'], application_id)
                flash('You cannot cancel your own approved application', category='error')
                return render_template(url_for('leave.search_application', application_for=application_for))

    attendance_summary = check_attendance_summary(application.start_date, application.end_date)
    if attendance_summary:
        msg = f'Attendance summary already prepared for {application.start_date.strftime("%B")},{application.start_date.year}' 
        flash(msg, category='error')
        return render_template(url_for('leave.search_application', application_for=application_for))

    #Approve application
    if action == 'approve':            
        if application.type == 'Casual' or application.type == 'Medical':
            available = check_available_leave(application, 'update')
            if not available:
                flash('Failed to approve application', category='error')
                return render_template(url_for('leave.search_application', application_for=application_for))
    
        application.status = 'Approved'
        msg = f'Application "{application_id}" approved'
    
    #Cancel application
    if action == 'cancel':
        if application.status == 'Approved':
            if application.type in ('Casual', 'Medical'):
                return_leave(application)
        
            if application.type == 'Medical':
                files = application.file_url.split(';')
                error = ''
            
                if not files:
                    error = 'File name not found in database'
                else:
                    file_list = delete_files(files)
                    if file_list != '':
                        error = 'Files not found in OS: ' + file_list
            
                if error != '':
                    flash(error, category='error')
            
        db.session.delete(application)
        msg = f'Application "{application_id}" cancelled'
    
    #Send mail to all concerned
    emails = get_emails(application, action)
    if emails['error']:
        current_app.logger.error('Failed to get emails for application "%s" %s', application.id, action)
        flash('Failed to get email addresses for sending email', category=error)
        return redirect(url_for('leave.search_application', application_for=application_for))
    
    if application.type in ('Casual', 'Medical', 'Casual adjust'):
        type = 'leave'
    elif application.type in ('In', 'Out', 'Both'):
        type = 'attendance'
    else:
        type = ''
    
    if action == 'approve':
        action = 'approved'
    elif action == 'cancel':
        action = 'cancelled'

    rv = send_mail2(sender=emails['sender'], receiver=emails['receiver'], cc=emails['cc'], application=application, type=type, action=action)
    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')

    db.session.commit()
    flash(msg, category='message')
    return redirect(url_for('leave.search_application', application_for=application_for))


