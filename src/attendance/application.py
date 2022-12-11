from .forms import ApplicationCasual, ApplicationFiberAttendance, ApplicationFiberCasual, ApplicationMedical, ApplicationFiberMedical, ApplicationAttendance, Searchapplication
from flask import Blueprint, flash, render_template, url_for, session, redirect, current_app, request, send_from_directory
from .auth import login_required
from .db import LeaveAvailable, db, Applications, Employee, Team
from .functions import check_authorization, check_attendance_summary, check_available_leave, get_emails, return_leave, delete_files, check_application_dates, check_holiday_dates, save_files, check_view_permission, check_data_access, send_mail, get_fiscal_year_start_end_2, update_leave_summary
import datetime
import re
from sqlalchemy import extract

application = Blueprint('application', __name__)

@application.route('/application/submit/<application_type>', methods=['GET', 'POST'])
@login_required
def submit(application_type):
    #Checks
    if application_type == 'casual':
        form = ApplicationCasual()
    elif application_type == 'fiber_casual':
        form = ApplicationFiberCasual()
    elif application_type == 'medical':
        form = ApplicationMedical()
    elif application_type == 'fiber_medical':
        form = ApplicationFiberMedical()
    elif application_type == 'attendance':
        form = ApplicationAttendance()
    elif application_type == 'fiber_attendance':
        form = ApplicationFiberAttendance()
    else:
        current_app.logger.error(' submit(): <application_type> value %s unknown, session user %s', application_type, session['username'])
        flash('Unknown application type', category='error')
        return render_template('base.html')

    if not form.validate_on_submit():
        return render_template('forms.html', type='application', application_type=application_type, form=form)


    application_dates_exist = check_application_dates(form, application_type)
    if application_dates_exist:
        flash(application_dates_exist, category='error')
        return render_template('forms.html', type='application', application_type=application_type, form=form)
    
    if application_type in ('casual', 'fiber_casual') and form.holiday_duty_type.data != 'No':
        holiday_dates_exist = check_holiday_dates(form, application_type)
        if holiday_dates_exist:
            flash(holiday_dates_exist, category='error')
            return render_template('forms.html', type='application', application_type=application_type, form=form)
    
    attendance_summary_exist = check_attendance_summary(form.start_date.data, form.end_date.data)
    if attendance_summary_exist:
        msg = f'Attendance summary prepared. You cannot submit leave for {form.start_date.data.strftime("%B")},{form.start_date.data.year}' 
        flash(msg, category='error')
        return redirect(request.url)

    if not form.end_date.data:
        form.end_date.data = form.start_date.data
    
    leave_duration = (form.end_date.data - form.start_date.data).days + 1
    
    if application_type in ('fiber_casual', 'fiber_medical', 'fiber_attendance'):
        if re.search('^Fiber', session['team']) and session['role'] == 'Supervisor':
            employee_id = form.empid.data
            status = 'Approved'
        else:
            current_app.logger.error(' submit(): "%s" trying to approve fiber team application', session['username'])
            flash('You are not authorized to submit & approve Fiber team applications')
            return redirect(url_for('forms.application', type=application_type, form=form))
    else:
        employee_id = session['empid']
        status = 'Approval Pending'

    if application_type in ('attendance', 'fiber_attendance'):
        application = Applications(empid=employee_id, type=form.type.data, start_date=form.start_date.data, end_date=form.end_date.data, duration=leave_duration, remark=form.remark.data, submission_date=datetime.datetime.now(), status=status)
    elif application_type in ('casual', 'fiber_casual'):
        application = Applications(empid=employee_id, type=form.type.data, start_date=form.start_date.data, end_date=form.end_date.data, duration=leave_duration, remark=form.remark.data, holiday_duty_type=form.holiday_duty_type.data, holiday_duty_start_date=form.holiday_duty_start_date.data, holiday_duty_end_date=form.holiday_duty_end_date.data, submission_date=datetime.datetime.now(), status=status)
    elif application_type in ('medical', 'fiber_medical'):
        application = Applications(empid=employee_id, type=form.type.data, start_date=form.start_date.data, end_date=form.end_date.data, duration=leave_duration, remark=form.remark.data, submission_date=datetime.datetime.now(), status=status)
    
    if application_type in ('casual', 'fiber_casual') and form.holiday_duty_type.data == 'No':
        if application_type == 'casual':
            available = check_available_leave(application)
        elif application_type == 'fiber_casual':
            available = check_available_leave(application, 'update')

        if not available:
            flash('Leave not available, please check leave summary', category='error')
            return redirect(request.url)
    
    if application_type in ('medical', 'fiber_medical'):
        if application_type == 'medical':
            available = check_available_leave(application)
        elif application_type == 'fiber_medical':
            available = check_available_leave(application, 'update')

        if not available:
            flash('Leave not available, please check leave summary', category='error')
            return redirect(request.url)
    
    if application_type in ('medical', 'fiber_medical'):
        files = [form.file1.data]
        if form.file2.data is not None:
            files.append(form.file2.data)
        if form.file3.data is not None:
            files.append(form.file3.data)

        filenames = save_files(files, session['username'])
        application.file_url = filenames

    db.session.add(application)
    flash('Application submitted', category='message')

    #Send mail to all concerned
    if application_type in ('fiber_casual', 'fiber_medical', 'fiber_attendance'):
        emails = get_emails(application, action='approve')
    else:
        emails = get_emails(application, action='submit')
    
    if emails['error']:
        current_app.logger.error('Failed to get emails for submitted application for "%s"', session['username'])
        flash('Failed to get email addresses for sending email', category='error')
        return redirect(url_for('forms.application', type=application_type))

    if application_type not in ('attendance', 'fiber_attendance'):
        type = 'leave'
        if application_type in ('fiber_casual', 'fiber_medical'):
            action = 'approved'
        else:
            action = 'submitted'
            
        if application_type in ('casual', 'fiber_casual'):
            if form.holiday_duty_type.data != 'No':
                application.type = 'Casual adjust'
    else:
        type = 'attendance'
        if application_type == 'fiber_attendance':
            action = 'approved'
        else:
            action = 'submitted'
    
    rv = send_mail(sender=emails['sender'], receiver=emails['receiver'], cc=emails['cc'], application=application, type=type, action=action)
    if rv:
        current_app.logger.warning(' submit(): %s',rv)
        flash('Failed to send mail', category='warning')

    db.session.commit()
    return redirect(url_for('forms.application', application_type=application_type, form=form))


@application.route('/application/<action>/<application_id>')
@login_required
def process(action, application_id=None):
    #Checks
    if action not in ('approve', 'cancel', 'submit'):
        current_app.logger.error('<action> value %s unknown, session user %s', action, session['username'])
        flash('Failed to execute the function', category='error')
        return render_template('base.html')
    
    application = Applications.query.filter_by(id=application_id).first()

    if session['empid'] == application.empid:
        application_for = 'self'
    elif session['role'] == 'Head':
        application_for = 'department'
    elif session['role'] in ('Supervisor', 'Manager'):
        application_for = 'team'

    if action in ('approve', 'cancel') and session['empid'] != application.empid:
        has_authorization = check_authorization(application)
        if not has_authorization:
            current_app.logger.error(' process(): "%s" trying to approve application "%s"', session['username'], application_id)
            msg = f'You are not authorized to "{action}" this application "{application_id}"'
            flash(msg, category='error')
            return redirect(url_for('leave.search', application_for=application_for))
    elif action in ('approve', 'cancel') and session['empid'] == application.empid:
        if action == 'approve':
            current_app.logger.error(' process(): "%s" trying to approve own application "%s"', session['username'], application_id)
            flash('You cannot approve your own application', category='error')
            return redirect(url_for('application.search', application_for=application_for))
        
        if action == 'cancel':
            if application.status.lower() == 'approved':
                current_app.logger.error(' process(): "%s" trying to cancel own approved application "%s"', session['username'], application_id)
                flash('You cannot cancel your own approved application', category='error')
                return redirect(url_for('application.search', application_for=application_for))
    

    attendance_summary = check_attendance_summary(application.start_date, application.end_date)
    if attendance_summary:
        msg = f'Attendance summary already prepared for {application.start_date.strftime("%B")},{application.start_date.year}' 
        flash(msg, category='error')
        return redirect(url_for('application.search', application_for=application_for))

    #Approve application
    if action == 'approve':            
        if application.type == 'Casual' or application.type == 'Medical':
            available = check_available_leave(application, 'update')
            if not available:
                flash('Leave not available', category='error')
                return redirect(url_for('application.search', application_for=application_for))
    
        application.status = 'Approved'
        msg = f'Application "{application_id}" approved'
    
    #Cancel application
    if action == 'cancel':
        if application.status == 'Approved':
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

            application_start_date = application.start_date
            employees = Employee.query.filter_by(id=application.empid).all()

            db.session.delete(application)
            db.session.commit()

            if application.type in ('Casual', 'Medical'):
                (year_start_date, year_end_date) = get_fiscal_year_start_end_2(application_start_date)
                rv = update_leave_summary(employees, year_start_date, year_end_date)
                if rv:
                    flash('Failed to update leave summary', category='warning')
                    return redirect(url_for('application.search', application_for=application_for))

        msg = f'Application "{application_id}" cancelled'
    
    #Send mail to all concerned
    emails = get_emails(application, action)
    if emails['error']:
        current_app.logger.error('Failed to get emails for application "%s" %s', application.id, action)
        flash('Failed to get email addresses for sending email', category=error)
        return redirect(url_for('application.search', application_for=application_for))
    
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

    rv = send_mail(sender=emails['sender'], receiver=emails['receiver'], cc=emails['cc'], application=application, type=type, action=action)
    if rv:
        current_app.logger.warning(' process():', rv)
        flash('Failed to send mail', category='warning')

    db.session.commit()
    flash(msg, category='message')
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
        name_string = f'%'

    if form.type.data == 'All':
        application_type_string = f'%'
    else:
        application_type_string = f'{form.type.data}'
    
    if application_for == 'self':
            applications = Applications.query.join(Employee).with_entities(Employee.fullname, Applications.id, Applications.type, Applications.start_date, Applications.duration, Applications.status).filter(Applications.empid==session['empid'], extract('month', Applications.start_date)==form.month.data, extract('year', Applications.start_date)==form.year.data, Applications.type.like(application_type_string)).order_by(Applications.status, Applications.start_date.desc()).all()
        
    if application_for == 'team':
        teams = Team.query.filter_by(empid=session['empid']).all()
        applications = []

        for team in teams:
            team_applications = Applications.query.select_from(Applications).join(Employee).join(Team, Applications.empid==Team.empid).with_entities(Employee.fullname, Team.name.label('team'), Applications.id, Applications.type, Applications.start_date, Applications.duration, Applications.status).filter(Team.name==team.name, extract('month', Applications.start_date)==form.month.data, extract('year', Applications.start_date)==form.year.data, Applications.empid!=session['empid'], Applications.type.like(application_type_string), Employee.fullname.like(name_string)).order_by(Applications.status, Applications.start_date.desc()).all()

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

    if session['empid'] != application.empid:
        has_access = check_data_access(application.empid)
        if not has_access:
            flash('You are not authorized to see this record', category='error')
            return render_template('base.html')

    return render_template('data.html', data_type='application_details', application=application)


@application.route('/application/files/<name>')
@login_required
def files(name):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], name)