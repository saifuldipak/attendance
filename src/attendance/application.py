import re
from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from sqlalchemy import extract
from sqlalchemy.exc import NoResultFound, SQLAlchemyError

from attendance.auth import login_required
from attendance.db import Applications, Employee, Team, db
from attendance.forms import (
    ApplicationAttendance,
    ApplicationCasual,
    ApplicationFiberAttendance,
    ApplicationFiberCasual,
    ApplicationFiberMedical,
    ApplicationMedical,
    Searchapplication,
)
from attendance.functions import (
    MailDeliveryError,
    check_application_dates,
    check_attendance_summary,
    check_authorization,
    check_available_leave,
    check_data_access,
    check_holiday_dates,
    check_view_permission,
    delete_files,
    get_emails,
    get_fiscal_year,
    save_files,
    send_mail,
    update_available_leave,
)
from attendance.schemas import EmployeeFiscalYear

application = Blueprint('application', __name__)


@application.route('/application/submit/<application_type>', methods=['GET', 'POST'])
@login_required
def submit(application_type):
    # 1. Map Form Classes
    form_mapping = {
        'casual': ApplicationCasual,
        'fiber_casual': ApplicationFiberCasual,
        'medical': ApplicationMedical,
        'fiber_medical': ApplicationFiberMedical,
        'attendance': ApplicationAttendance,
        'fiber_attendance': ApplicationFiberAttendance,
    }

    form_class = form_mapping.get(application_type)
    if not form_class:
        current_app.logger.error("Unknown application type '%s' submitted by user '%s'", application_type, session.get('username'))
        flash('Unknown application type', category='error')
        return render_template('base.html')

    form = form_class()

    if not form.validate_on_submit():
        return render_template('forms.html', type='application', application_type=application_type, form=form)

    # 2. Date & Attendance Validations
    application_dates_exist = check_application_dates(form, application_type)
    if application_dates_exist:
        flash(application_dates_exist, category='error')
        return render_template('forms.html', type='application', application_type=application_type, form=form)

    if application_type in ('casual', 'fiber_casual') and getattr(form, 'holiday_duty_type', None) and form.holiday_duty_type.data != 'No':
        holiday_dates_exist = check_holiday_dates(form, application_type)
        if holiday_dates_exist:
            flash(holiday_dates_exist, category='error')
            return render_template('forms.html', type='application', application_type=application_type, form=form)

    if check_attendance_summary(form.start_date.data, form.end_date.data):
        month_name = form.start_date.data.strftime("%B")
        msg = f'Attendance summary prepared. You cannot submit leave for {month_name}, {form.start_date.data.year}'
        flash(msg, category='error')
        return redirect(request.url)

    if not form.end_date.data:
        form.end_date.data = form.start_date.data

    leave_duration = (form.end_date.data - form.start_date.data).days + 1

    # 3. Determine Authorization & Status
    if application_type in ('fiber_casual', 'fiber_medical', 'fiber_attendance'):
        user_team = session.get('team', '')
        user_role = session.get('role', '')
        if re.search('^Fiber', user_team) and user_role == 'Supervisor':
            employee_id = form.empid.data
            status = 'Approved'
        else:
            current_app.logger.error("Unauthorized user '%s' attempting to submit fiber team application", session.get('username'))
            flash('You are not authorized to submit & approve Fiber team applications', category='error')
            return redirect(url_for('forms.application', type=application_type))
    else:
        employee_id = session['empid']
        status = 'Approval Pending'

    # 4. Construct Application Object
    holiday_type = getattr(form, 'holiday_duty_type', None)
    if application_type in ('casual', 'fiber_casual') and holiday_type and holiday_type.data != 'No':
        form.type.data = 'Casual adjust'

    application = Applications()
    application.empid = employee_id
    application.type = form.type.data
    application.start_date = form.start_date.data
    application.end_date = form.end_date.data
    application.duration = leave_duration
    application.remark = form.remark.data
    application.submission_date = datetime.now().astimezone()
    application.status = status
    

    if application_type in ('casual', 'fiber_casual') and holiday_type:
        application.holiday_duty_type = form.holiday_duty_type.data
        application.holiday_duty_start_date = form.holiday_duty_start_date.data
        application.holiday_duty_end_date = form.holiday_duty_end_date.data

    # 5. Check Leave Availability
    if application_type in ('casual', 'fiber_casual') and (not holiday_type or holiday_type.data == 'No'):
        action_mode = 'update' if application_type == 'fiber_casual' else 'check'
        rv = check_available_leave(application, action_mode) if action_mode == 'update' else check_available_leave(application)
        if rv != 'Leave available':
            flash(rv, category='error')
            return redirect(request.url)

    if application_type in ('medical', 'fiber_medical'):
        action_mode = 'update' if application_type == 'fiber_medical' else 'check'
        rv = check_available_leave(application, action_mode) if action_mode == 'update' else check_available_leave(application)
        if rv != 'Leave available':
            flash(rv, category='error')
            return redirect(request.url)

        # File upload processing
        uploaded_files = [f for f in [form.file1.data, getattr(form, 'file2', None) and form.file2.data, getattr(form, 'file3', None) and form.file3.data] if f]
        if uploaded_files:
            application.file_url = save_files(uploaded_files, session['username'])

    # 6. Database Commit
    try:
        db.session.add(application)
        db.session.commit()
        flash('Application submitted', category='info')
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception("Database error submitting application for '%s'", session.get('username'))
        flash('A database error occurred while submitting your application.', category='error')
        return redirect(request.url)

    # 7. Notification Emails
    email_action = 'approve' if application_type in ('fiber_casual', 'fiber_medical', 'fiber_attendance') else 'submit'
    emails = get_emails(application, action=email_action)

    if emails.get('error'):
        current_app.logger.error("Failed to retrieve emails for submitted application (%s)", session.get('username'))
        flash('Application saved, but failed to retrieve email addresses for notification.', category='warning')
        return redirect(url_for('forms.application', application_type=application_type))

    # Determine email category and action labels
    mail_type = 'attendance' if application_type in ('attendance', 'fiber_attendance') else 'leave'
    mail_action = 'approved' if application_type in ('fiber_casual', 'fiber_medical', 'fiber_attendance') else 'submitted'

    # Dispatch Email using new Exception-based send_mail contract
    try:
        send_mail(
            sender=emails['sender'],
            receiver=emails['receiver'],
            mail_type=mail_type,
            action=mail_action,
            application=application,
            cc=emails.get('cc', [])
        )
    except MailDeliveryError as e:
        current_app.logger.warning(
            "Failed to send submission email (App ID %s, User %s): %s",
            application.id,
            session.get('username'),
            e
        )
        flash('Application submitted, but notification email failed to send.', category='warning')

    return redirect(url_for('forms.application', application_type=application_type))


@application.route('/application/<action>/<application_id>')
@login_required
def process(action, application_id):
    # 1. Input Validation
    if action not in ('approve', 'cancel'):
        current_app.logger.error("Invalid action '%s' by user '%s'", action, session.get('username'))
        flash('Unknown action', category='error')
        return render_template('base.html')

    if not application_id:
        current_app.logger.error("No application_id provided by user '%s'", session.get('username'))
        flash('No application id', category='error')
        return render_template('base.html')

    application = Applications.query.filter_by(id=application_id).first()
    if not application:
        current_app.logger.error("Application '%s' not found for user '%s'", application_id, session.get('username'))
        flash('Application not found', category='error')
        return render_template('base.html')

    # Determine scope view for redirects
    user_empid = session.get('empid')
    user_role = session.get('role')

    if user_empid == application.empid:
        application_for = 'self'
    elif user_role == 'Head':
        application_for = 'department'
    elif user_role in ('Supervisor', 'Manager'):
        application_for = 'team'
    else:
        application_for = 'self'

    # 2. Authorization & Self-Action Validation
    if user_empid == application.empid:
        if action == 'approve':
            current_app.logger.error("User '%s' attempted to approve own application '%s'", session.get('username'), application_id)
            flash('You cannot approve your own application', category='error')
            return redirect(url_for('application.search', application_for=application_for))

        if action == 'cancel' and application.status.lower() == 'approved':
            current_app.logger.error("User '%s' attempted to cancel own approved application '%s'", session.get('username'), application_id)
            flash('You cannot cancel your own approved application', category='error')
            return redirect(url_for('application.search', application_for=application_for))
    else:
        if not check_authorization(application):
            current_app.logger.error("Unauthorized user '%s' attempted to '%s' application '%s'", session.get('username'), action, application_id)
            flash(f'You are not authorized to {action} application "{application_id}"', category='error')
            return redirect(url_for('leave.search', application_for=application_for))

    # 3. Attendance Period Validation
    if check_attendance_summary(application.start_date, application.end_date):
        month_name = application.start_date.strftime("%B")
        flash(f'Attendance summary already prepared for {month_name}, {application.start_date.year}', category='error')
        return redirect(url_for('application.search', application_for=application_for))

    # 4. Database Operations (Approve / Cancel)
    try:
       if action == 'approve':
            # ✅ Fixed: Ruff SIM102 compliant with action check preserved
            if application.type in ('Casual', 'Medical') and not check_available_leave(application, 'update'):
                flash('Leave not available', category='error')
                return redirect(url_for('application.search', application_for=application_for))

            application.status = 'Approved'
            
            # Recalculate leaves on approval
            if application.type in ('Casual', 'Medical'):
                employee = Employee.query.get(application.empid)
                fy_start, fy_end = get_fiscal_year(application.start_date)
                update_available_leave(
                    EmployeeFiscalYear(
                        employee=employee, 
                        fiscal_year_start_date=fy_start, 
                        fiscal_year_end_date=fy_end
                    )
                )

            db.session.commit()
            success_msg = f'Application {application.id} approved'
       elif action == 'cancel':
            if application.type == 'Medical' and getattr(application, 'file_url', None):
                files = [f for f in application.file_url.split(';') if f]
                if files:
                    missing_files = delete_files(files)
                    if missing_files:
                        flash(f'Files not found in OS: {missing_files}', category='warning')

            employee = Employee.query.get(application.empid)
            fy_start, fy_end = get_fiscal_year(application.start_date)

            db.session.delete(application)
            db.session.commit()

            if application.type in ('Casual', 'Medical'):
                update_available_leave(
                    EmployeeFiscalYear(
                        employee=employee, 
                        fiscal_year_start_date=fy_start, 
                        fiscal_year_end_date=fy_end
                    )
                )

            success_msg = f'Application {application.id} cancelled'
    except (NoResultFound, SQLAlchemyError) as e:
        db.session.rollback()
        current_app.logger.exception("Database failure during '%s' on application '%s'", action, application_id)
        flash('A database error occurred while processing the request', category='error')
        return redirect(url_for('application.search', application_for=application_for))

    # 5. Retrieve Notification Recipients
    emails = get_emails(application, action)
    if emails.get('error'):
        current_app.logger.error("Failed to retrieve emails for application '%s' (%s)", application.id, action)
        flash('Application processed, but failed to retrieve recipient emails.', category='warning')
        flash(success_msg, category='info')
        return redirect(url_for('application.search', application_for=application_for))

    # Map parameters for mail dispatch
    mail_type = (
        'leave' if application.type in ('Casual', 'Medical', 'Casual adjust')
        else 'attendance' if application.type in ('In', 'Out', 'Both')
        else ''
    )
    past_action_label = 'approved' if action == 'approve' else 'cancelled'

    # 6. Dispatch Email
    try:
        send_mail(
            sender=emails['sender'],
            receiver=emails['receiver'],
            mail_type=mail_type,
            action=past_action_label,
            application=application,
            cc=emails.get('cc', [])
        )
    except MailDeliveryError as e:
        current_app.logger.warning(
            "Failed to send application notification email (App ID %s, Action %s): %s",
            application.id,
            past_action_label,
            e
        )
        flash('Application processed, but notification email failed to send.', category='warning')

    flash(success_msg, category='info')
    return redirect(url_for('application.search', application_for=application_for))


@application.route('/application/search/<application_for>', methods=['GET', 'POST'])
@login_required
def search(application_for):
    if application_for not in ('self', 'team', 'department', 'all'):
        current_app.logger.error(' search_application(): Unknown function argument "%s", user: %s', application_for, session['username'])
        flash('Failed to get search result', category='error')
        return render_template('base.html')
    
    if application_for != 'self':
        has_access = check_view_permission(application_for)
        if not has_access:
            current_app.logger.warning(' search_application(): %s trying to access %s data', session['username'], application_for)
            flash('You are not authorized to run this function', category='error')
            return redirect(url_for('forms.search_application', application_for=application_for))

    form = Searchapplication()

    if not form.validate_on_submit():
        return render_template('forms.html', type='search_application', application_for=application_for, form=form)

    if form.name.data:
        name_string = f'%{form.name.data}%'
    else:
        name_string = '%'

    if form.type.data == 'All':
        application_type_string = '%'
    else:
        application_type_string = f'{form.type.data}'
    
    if application_for == 'self':
            applications = Applications.query.join(Employee).with_entities(Employee.fullname, Applications.id, Applications.type, Applications.start_date, Applications.duration, Applications.status).filter(Applications.empid==session['empid'], extract('month', Applications.start_date)==form.month.data, extract('year', Applications.start_date)==form.year.data, Applications.type.like(application_type_string)).order_by(Applications.status, Applications.start_date.desc()).all()
        
    if application_for == 'team':
        teams = Team.query.filter_by(empid=session['empid']).all()
        
        applications = []

        for team in teams:
            if session['role'].lower() == 'supervisor': 
                team_applications = Applications.query.select_from(Applications).join(Employee).join(Team, Applications.empid==Team.empid).with_entities(Employee.fullname, Team.name.label('team'), Applications.id, Applications.type, Applications.start_date, Applications.duration, Applications.status).filter(Team.name==team.name, extract('month', Applications.start_date)==form.month.data, extract('year', Applications.start_date)==form.year.data, Employee.role!='Supervisor', Employee.role!='Manager', Applications.type.like(application_type_string), Employee.fullname.like(name_string)).order_by(Applications.status, Applications.start_date.desc()).all()
            elif session['role'].lower() == 'manager':
                team_applications = Applications.query.select_from(Applications).join(Employee).join(Team, Applications.empid==Team.empid).with_entities(Employee.fullname, Team.name.label('team'), Applications.id, Applications.type, Applications.start_date, Applications.duration, Applications.status).filter(Team.name==team.name, extract('month', Applications.start_date)==form.month.data, extract('year', Applications.start_date)==form.year.data, Employee.role!='Manager', Applications.type.like(application_type_string), Employee.fullname.like(name_string)).order_by(Applications.status, Applications.start_date.desc()).all()


            for team_application in team_applications:
                applications.append(team_application)

    if application_for == 'department':
        applications = Applications.query.join(Employee).join(Team, Applications.empid==Team.empid).with_entities(Employee.fullname, Team.name.label('team'), Applications.id, Applications.type, Applications.start_date, Applications.duration, Applications.status).filter(Employee.department==session['department'], extract('month', Applications.start_date)==form.month.data, extract('year', Applications.start_date)==form.year.data, Applications.empid!=session['empid'], Employee.fullname.like(name_string), Applications.type.like(application_type_string)).order_by(Applications.status, Applications.start_date.desc()).all()

    if application_for == 'all':
        applications = Applications.query.join(Employee).join(Team, Applications.empid==Team.empid).with_entities(Employee.fullname, Team.name.label('team'), Applications.id, Applications.type, Applications.start_date, Applications.duration, Applications.status).filter(Employee.fullname.like(name_string), extract('month', Applications.start_date)==form.month.data, extract('year', Applications.start_date)==form.year.data, Applications.type.like(application_type_string)).order_by(Applications.status, Applications.start_date.desc()).all()
    
    return render_template('data.html', type='application_search', application_for=application_for, applications=applications, form=form)


@application.route('/application/details/<application_id>')
@login_required
def details(application_id):
    application = Applications.query.join(Employee).filter(Applications.id==application_id).first()

    if session['empid'] != application.empid: # type: ignore
        has_access = check_data_access(application.empid) # type: ignore
        if not has_access:
            flash('You are not authorized to see this record', category='error')
            return render_template('base.html')

    return render_template('data.html', data_type='application_details', application=application)


@application.route('/application/files/<name>')
@login_required
def files(name):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], name)