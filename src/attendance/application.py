from flask import Blueprint, flash, render_template, url_for, session, redirect, current_app
from .auth import login_required, team_leader_required
from .db import db, Applications, Employee, AttendanceSummary
from .functions import approval_authorization, check_attendance_summary, check_available_leave, get_emails
from .mail import send_mail2

application = Blueprint('application', __name__)

@application.route('/application/approve/<application_id>')
@login_required
@team_leader_required
def approve(application_id):
    if session['role'] == 'Head':
        application_for = 'department'
    elif session['role'] in ('Supervisor', 'Manager'):
        application_for = 'team'

    application = Applications.query.filter_by(id=application_id).one()
    
    can_approve = approval_authorization(application)
    if not can_approve:
        current_app.logger.error(' approval(): "%s" trying to approve application "%s"', session['username'], application_id)
        flash('You are not authorized to approve this application', category='error')
        return render_template(url_for('leave.search_application', application_for=application_for))

    attendance_summary = check_attendance_summary(application.start_date, application.end_date)
    if attendance_summary:
        msg = f'Attendance summary already prepared for {application.start_date.strftime("%B")},{application.start_date.year}' 
        flash(msg, category='error')
        return render_template(url_for('leave.search_application', application_for=application_for))

    if application.type == 'Casual' or application.type == 'Medical':
        available = check_available_leave(application, 'update')
        if not available:
            flash('Leave not available, please check leave summary', category='error')
            return render_template(url_for('leave.search_application', application_for='team'))
    
    application.status = 'Approved'
    db.session.commit()
    msg = f'Application "{application_id}" approved'
    flash(msg, category='message')
    
    emails = get_emails(application, 'approve')
    
    if application.type in ('Casual', 'Medical', 'Casual adjust'):
        type = 'leave'
    elif application.type in ('In', 'Out', 'Both'):
        type = 'attendance'
    else:
        type = ''

    rv = send_mail2(sender=emails['sender'], receiver=emails['receiver'], cc=emails['cc'], application=application, type=type, action='approved')
    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')

    return redirect(url_for('leave.search_application', application_for=application_for))
