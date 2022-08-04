from flask import (Blueprint, current_app, redirect, render_template, request, send_from_directory, 
                    session, flash, url_for)
from sqlalchemy import and_, or_
from .check import check_access, check_holiday_dates, check_application_dates
from .db import (ApprLeaveAttn, Attendance, AttnSummary, LeaveDeduction, db, Employee, Team, Applications, 
                    LeaveAvailable, AttnSummary)
from .mail import send_mail
from .auth import admin_required, login_required, manager_required, head_required, supervisor_required, team_leader_required
from werkzeug.utils import secure_filename
import os
from .forms import (Createleave, Employeedelete, LeaveMedical, Leavecasual, Leavededuction, Leavefibercasual, Leavefibermedical)
import datetime


# renaming original uploaded files and saving to disk, also creating a string 
# with all the file names for storing in database 
def save_files(files, username):
    file_names = ''
    file_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    file_count = 1
                
    for file in files:
        file_name = secure_filename(file.filename)
        ext = os.path.splitext(file_name)[1]
        file_name = username + "_" + file_id + str(file_count) + ext
        file_url = os.path.join(current_app.config['UPLOAD_FOLDER'], file_name)
        file.save(file_url)
        file_names += file_name + ';'
        file_count += 1
    
    file_names = file_names[:-1]
    return file_names

# delete files uploaded with Medical leave application
def delete_files(files):
    file_list = ''
    
    for file in files:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file)

        if os.path.exists(file_path):
            os.remove(file_path)
        else:
            file_list += file_path
    
    return file_list

#Checking and updating leave
def check_available_leave(empid, start_date, duration, type, update=None):
    
    leave = LeaveAvailable.query.filter(LeaveAvailable.empid==empid, 
                and_(LeaveAvailable.year_start < start_date, 
                LeaveAvailable.year_end > start_date)).first()
    if not leave:
        current_app.logger.warning('check_leave(): no data found in leave_available table for employee %s', empid)
        return False

    if type == 'Casual':
        if leave.casual > duration:
            if update:
                casual = leave.casual - duration
                leave.casual = casual
        else:
            total = leave.casual + leave.earned
            if total > duration:
                if update:
                    earned = total - duration
                    leave.casual = 0
                    leave.earned = earned
            else:
                return False

    if type == 'Medical':
        if leave.medical > duration:
            if update:
                medical = leave.medical - duration
                leave.medical = medical
        else:
            total = leave.medical + leave.casual
            
            if total > leave.duration:
                if update:
                    casual = total - duration
                    leave.medical = 0
                    leave.casual = casual
            else:
                total = total + leave.earned
                if total > duration:
                    if update:
                        earned = total - duration
                        leave.medical = 0
                        leave.casual = 0
                        leave.earned = earned
                else:
                    return False
                
    return True
 
#update 'appr_leave_attn' table
def update_apprleaveattn(empid, start_date, end_date, approved):
    while start_date <= end_date:
        attendance = ApprLeaveAttn.query.filter(ApprLeaveAttn.date==start_date, ApprLeaveAttn.empid==empid).first()
        if attendance:
            attendance.approved = approved
        start_date += datetime.timedelta(days=1)
    db.session.commit()

#return leave when leave is cancelled
def return_available_leave(empid, start_date, duration):
    summary = AttnSummary.query.filter_by(year=application.start_date.year, month=application.start_date.strftime("%B"), 
                    empid=application.empid).first()
    if summary:
        return f'Attendance summary already prepared for {application.start_date.strftime("%B")},{application.start_date.year}' 
                
    leave = LeaveAvailable.query.filter_by(empid=employee.id).first()
    if not leave:
        current_app.logger.warning(' cancel_team(): no data found in leave_available table for %s', employee.username)
        return f'No leave available for {employee.username}'
            
    if application.type == 'Casual':
        leave.casual = leave.casual + application.duration

    if application.type == 'Medical':
        leave.medical = leave.medical + application.duration


leave = Blueprint('leave', __name__)

##Casual and Medical leave application submission##
@leave.route('/leave/application/<type>', methods=['GET', 'POST'])
@login_required
def application(type):

    if type == 'Casual':
        form = Leavecasual()
    elif type == 'Medical':
        form = LeaveMedical()

    if form.validate_on_submit():
        leave_dates_exist = check_application_dates(session['empid'], form.start_date.data, form.end_date.data)
        if leave_dates_exist:
            flash(leave_dates_exist, category='error')
            return render_template('forms.html', type='leave', leave=type, form=form)
        
        if form.holiday_duty_type.data == 'On site':
            holiday_dates_exist = check_holiday_dates(session['empid'], form.holiday_duty_start_date.data, form.holiday_duty_end_date.data)
            if holiday_dates_exist:
                flash(holiday_dates_exist, category='error')
                return render_template('forms.html', type='leave', leave=type, form=form)

        summary = AttnSummary.query.filter_by(year=form.start_date.data.year, month=form.start_date.data.strftime("%B"), 
                    empid=session['empid']).first()
        if summary:
            msg = f'You cannot submit leave for {form.start_date.data.strftime("%B")},{form.start_date.data.year}' 
            flash(msg, category='error')
            return redirect(request.url)

        if not form.end_date.data:
            form.end_date.data = form.start_date.data
        
        leave_duration = (form.end_date.data - form.start_date.data).days + 1

        if form.holiday_duty_type.data == 'No':
            available = check_available_leave(session['empid'], form.start_date.data, leave_duration, type)
            if not available:
                flash('Leave not available, please check leave summary', category='error')
                return redirect(request.url)
        
        if type == 'Casual':
            if form.holiday_duty_type.data != 'No':
                type = 'Casual adjust'
            
            if form.holiday_duty_start_date.data and not form.holiday_duty_end_date.data:
                form.holiday_duty_end_date.data = form.holiday_duty_start_date.data
            
            leave = Applications(empid=session['empid'], type=type, start_date=form.start_date.data, end_date=form.end_date.data, 
                        duration=leave_duration, remark=form.remark.data, holiday_duty_type=form.holiday_duty_type.data, 
                        holiday_duty_start_date=form.holiday_duty_start_date.data,
                        holiday_duty_end_date=form.holiday_duty_end_date.data, submission_date=datetime.datetime.now(), 
                        status='Approval Pending')
        
        if type == 'Medical':
            #creating a list of file names
            files = [form.file1.data]
            if form.file2.data is not None:
                files.append(form.file2.data)
            if form.file3.data is not None:
                files.append(form.file3.data)

            filenames = save_files(files, session['username'])

            leave = Applications(empid=session['empid'], type=type, start_date=form.start_date.data, end_date=form.end_date.data, 
                        duration=leave_duration, remark=form.remark.data, submission_date=datetime.datetime.now(), file_url=filenames, 
                        status='Approval Pending')
        
        db.session.add(leave)
        db.session.commit()
        flash('Leave submitted', category='message')
        
        #Send mail to all concerned
        application = Applications.query.filter_by(start_date=form.start_date.data, 
                            end_date=form.end_date.data, empid=session['empid']).first()
        
        supervisor = None
        if session['role'] == 'Team':
            supervisor = Employee.query.join(Team).filter(Team.name==session['team'], Employee.role=='Supervisor').first()
            if supervisor:
                receiver_email = supervisor.email

        manager = None
        if not supervisor or session['role'] == 'Supervisor':
            manager = Employee.query.join(Team).filter(Team.name==session['team'], Employee.role=='Manager').first()
            if manager:
                receiver_email = manager.email
        
        message = ''
        if not manager or session['role'] == 'Manager':
            head = Employee.query.join(Team).filter(Employee.department==session['department'], Employee.role=='Head').first()
            if head:
                receiver_email = head.email
            else:
                current_app.logger.warning('leave.application() - Supervisor, Manager, Head none found for %s', session['username'])
                message = 'failed'
                
        if message != '':
            flash('Failed to send mail', category='warning')
            return redirect(request.url)

        employee = Employee.query.filter_by(id=session['empid']).first()
        
        host = current_app.config['SMTP_HOST']
        port = current_app.config['SMTP_PORT']
        rv = send_mail(host=host, port=port, sender=employee.email, receiver=receiver_email, cc1=employee.email, 
                        type='leave', application=application, action='submitted')
        
        if rv:
            current_app.logger.warning(rv)
            flash('Failed to send mail', category='warning')
            return redirect(request.url)
    else:
        return render_template('forms.html', type='leave', leave=type, form=form)
    
    return redirect(request.url)

#Casual and Medical leave application submission for Fiber
@leave.route('/leave/application/fiber/<type>', methods=['GET', 'POST'])
@login_required
@supervisor_required
def application_fiber(type):
    
    if type == 'Casual':
        form = Leavefibercasual()
    elif type == 'Medical':
        form = Leavefibermedical()

    if form.validate_on_submit():
        employee = Employee.query.filter_by(id=form.empid.data).first()
        if not employee:
            flash('Employee does not exists', category='error')
            return redirect(url_for('forms.leave', type=type))
        
        leave_dates_exist = check_application_dates(employee.id, form.start_date.data, form.end_date.data)
        if leave_dates_exist:
            flash(leave_dates_exist, category='error')
            return redirect(url_for('forms.leave', type=type))
        
        if form.holiday_duty_type.data == 'On site':
            holiday_dates_exist = check_holiday_dates(employee.id, form.holiday_duty_start_date.data, form.holiday_duty_end_date.data)
            if holiday_dates_exist:
                flash(holiday_dates_exist, category='error')
                return render_template('forms.html', type='leave', leave=type, form=form)

        summary = AttnSummary.query.filter_by(year=form.start_date.data.year, month=form.start_date.data.strftime("%B"), 
                empid=form.empid.data).first()
        if summary:
            msg = f'Attendance summary already prepared for {form.start_date.data.strftime("%B")},{form.start_date.data.year}' 
            flash(msg, category='error')
            return redirect(request.url)
        
        if not form.end_date.data:
            form.end_date.data = form.start_date.data
        
        leave_duration = (form.end_date.data - form.start_date.data).days + 1
        
        if form.holiday_duty_type.data == 'No':
            available = check_available_leave(employee.id, form.start_date.data, leave_duration, type, 'update')
            if not available:
                flash('Leave not available, please check leave summary', category='error')
                return redirect(request.url)
        
        if type == 'Casual':
            if form.holiday_duty_type.data != 'No':
                type = 'Casual adjust'
            
            if form.holiday_duty_start_date.data and not form.holiday_duty_end_date.data:
                form.holiday_duty_end_date.data = form.holiday_duty_start_date.data

            leave = Applications(empid=employee.id, type=type, start_date=form.start_date.data, end_date=form.end_date.data, 
                        duration=leave_duration, remark=form.remark.data, holiday_duty_type=form.holiday_duty_type.data, 
                        holiday_duty_start_date=form.holiday_duty_start_date.data, 
                        holiday_duty_end_date=form.holiday_duty_end_date.data, submission_date=datetime.datetime.now(), 
                        approval_date=datetime.datetime.now(), status='Approved') 

        if form.holiday_duty_type.data != 'No':
            type = 'Casual adjust'
            update_apprleaveattn(employee.id, form.holiday_duty_start_date.data, form.holiday_duty_end_date.data, '') 
            
        if type == 'Medical':
            #creating a list of file names
            files = [form.file1.data]
            if form.file2.data is not None:
                files.append(form.file2.data)
            if form.file3.data is not None:
                files.append(form.file3.data)

            filenames = save_files(files, employee.username)

            leave = Applications(empid=employee.id, type=type, start_date=form.start_date.data, end_date=form.end_date.data, 
                        duration=leave_duration,remark=form.remark.data, submission_date=datetime.datetime.now(), 
                        file_url=filenames, status='Approved')

        db.session.add(leave)
        update_apprleaveattn(employee.id, form.start_date.data, form.end_date.data, type)
        flash('Leave approved', category='message')
        
        #Send mail to all concerned
        application = Applications.query.filter_by(start_date=form.start_date.data, 
                            end_date=form.end_date.data, empid=form.empid.data).first()
        
        manager = Employee.query.filter_by(id=session['empid']).first()
        if not manager:
            current_app.logger.warning('application_fiber(): Team Manager email not found')
            rv = 'failed'

        admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
        if not admin:
            current_app.logger.warning('application_fiber(): Admin email not found')
            rv = 'failed'

        head = Employee.query.join(Team).filter(Employee.department==session['department'], 
                    Employee.role=='Head').first()
        if not head:
            current_app.logger.warning('application_fiber(): Dept. Head email not found')
            rv = 'failed'
        
        if 'rv' in locals():
            flash('Failed to send mail', category='warning')
            return redirect(request.url)

        employee = Employee.query.filter_by(id=session['empid']).first()
        
        host = current_app.config['SMTP_HOST']
        port = current_app.config['SMTP_PORT']
        rv = send_mail(host=host, port=port, sender=manager.email, receiver=admin.email, cc1=manager.email, 
                        cc2=head.email, type='leave', application=application, action='approved')
        
        if rv:
            current_app.logger.warning(rv)
            flash('Failed to send mail', category='warning')
            return redirect(request.url)
    else:
        return render_template('forms.html', type='leave', leave=type, team='fiber', form=form)

    return redirect(request.url)

#Leave application status for individual 
@leave.route('/leave/application/status/self')
@login_required
def application_status_self():
    applications = Applications.query.join(Employee).filter(Employee.id==session['empid'], 
                    or_(Applications.type.like("Casual%"), Applications.type=='Medical')).\
                    order_by(Applications.submission_date.desc()).all()

    return render_template('data.html', type='leave_application_status', data='self', applications=applications)

#Leave application status for team 
@leave.route('/leave/application/status/team')
@login_required
@team_leader_required
def application_status_team():
    teams = Team.query.join(Employee).filter_by(id=session['empid']).all()
    applications = []
    
    for team in teams:
        team_applications = Applications.query.select_from(Applications).join(Team, Applications.empid==Team.empid).\
                                filter(Team.name==team.name, Applications.empid!=session['empid'], 
                                or_(Applications.type.like("Casual%"), Applications.type=='Medical')).order_by(Applications.status, 
                                Applications.submission_date.desc()).all()

        applications += team_applications

    return render_template('data.html', type='leave_application_status', data='team', applications=applications)

@leave.route('/leave/application/status/team/fiber')
@login_required
@supervisor_required
def application_status_team_fiber():
    teams = Team.query.join(Employee).filter_by(id=session['empid']).all()
    applications = []
    
    for team in teams:
        team_applications = Applications.query.select_from(Applications).join(Team, Applications.empid==Team.empid).\
                                filter(Team.name==team.name, Applications.empid!=session['empid'], 
                                or_(Applications.type.like("Casual%"), Applications.type=='Medical')).order_by(Applications.status, 
                                Applications.submission_date.desc()).all()

        applications += team_applications

    return render_template('data.html', type='leave_application_status', data='team_fiber', applications=applications)

#Leave application status for department
@leave.route('/leave/application/status/department')
@login_required
@head_required
def application_status_department():
    applications = Applications.query.join(Employee).\
                    filter(Employee.department==session['department'], or_(Applications.type.like("Casual%"), 
                    Applications.type=='Medical'), Applications.empid!=session['empid']).\
                    order_by(Applications.status, Applications.submission_date.desc()).all()

    return render_template('data.html', type='leave_application_status', data='department', applications=applications)

#Leave application status for all
@leave.route('/leave/application/status/all')
@login_required
@admin_required
def application_status_all():
    applications  = Applications.query.join(Employee).filter(or_(Applications.type.like("Casual%"), 
                    Applications.type=='Medical')).order_by(Applications.status).all()
    
    return render_template('data.html', type='leave_application_status', applications=applications)

## Query & show details of each leave application using application id ##
@leave.route('/leave/details/<application_id>')
@login_required
def details(application_id):
    rv = check_access(application_id)
    
    if not rv:
        flash('You are not authorized to see this record', category='error')
        return redirect(url_for('leave.application_status_team', type=type))

    details = Applications.query.join(Employee).filter(Applications.id==application_id).first()
    return render_template('data.html', data_type='leave_application_details', details=details)    


##Leave application cancel function##
@leave.route('/leave/cancel/<application_id>')
@login_required
def cancel(application_id):
    
    application = Applications.query.join(Employee).\
            filter(and_(Employee.id==session['empid'], Applications.id==application_id)).first()

    if not application:
        flash('Leave application not found', category='error')
    elif application.status == 'Approved':
        flash('Cancel request sent to Team Manager', category='message')
    else:
        error = ''
        # delete files attached with Medical leave
        if application.type == 'Medical':
            files = application.file_url.split(';')
            
            if not files:
                error = 'File name not found in database'
            else:
                file_list = delete_files(files)
                if file_list != '':
                    error = 'Files not found in OS: ' + file_list
            
            if error != '':
                flash(error, category='error')
        
    #Send mail to all concerned
    if session['role'] == 'Team':
        manager = Employee.query.join(Team).filter(Team.name==session['team'], 
                                                Employee.role=='Manager').first()
        if not manager:
            current_app.logger.warning('Team Manager email not found')
        else:            
            receiver_email = manager.email

    if session['role'] == 'Manager' or not manager:
        head = Employee.query.join(Team).filter(Employee.department==session['department'], 
                                                Employee.role=='Head').first()
        if not head:
            current_app.logger.warning('Dept. Head email not found')
            rv = 'failed'
        else:
            receiver_email = head.email

    if 'rv' in locals():
        flash('Failed to send mail', category='warning')
        return redirect(request.url)

    employee = Employee.query.filter_by(id=session['empid']).first()
    
    host = current_app.config['SMTP_HOST']
    port = current_app.config['SMTP_PORT']
    rv = send_mail(host=host, port=port, sender=employee.email, receiver=receiver_email, cc1=employee.email, cc2=employee.email, 
                    type='leave', application=application, action='cancelled')
    
    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')
        return redirect(request.url)
    
    #delete Leave record from database        
    if error == '':
        db.session.delete(application)
        db.session.commit()
        flash('Leave cancelled', category='message')
    
    return redirect(url_for('leave.application_status_self'))

##Leave application cancel function for team##
@leave.route('/leave/cancel/team/<application_id>')
@login_required
@manager_required
def cancel_team(application_id):
    application = Applications.query.filter_by(id=application_id).first()
    if not application:
        flash('Leave application not found', category='error')
        return redirect(url_for('leave.status_team'))
    
    employee = Employee.query.join(Applications).filter(Applications.id==application_id).first()
    if not employee:
        current_app.logger.warning(' cancel_team(): employee details not found for application:%s', application_id)
        flash('Employee details not found for this application', category='error')
        return redirect(url_for('leave.status_team'))
    
    team = Team.query.filter_by(empid=application.empid).first()
    if not team:
        flash('Employee team not found for this application', category='error')
        current_app.logger.warning(' cancel_team(): team not found for %s', application.empid)
        return redirect(url_for('leave.status_team'))

    manager = Employee.query.join(Team).filter(Employee.id==session['empid'], Employee.role=='Manager', 
                Team.name==team.name).first()
    if not manager:
        flash('You are not authorized', category='error')
        current_app.logger.warning(' cancel_team(): not the manager of %s', team.name)
        return redirect(url_for('leave.status_team'))
    
    if application.status == 'Approved':
        if application.type == 'Casual' and application.type == 'Medical':
            summary = AttnSummary.query.filter_by(year=application.start_date.year, month=application.start_date.strftime("%B"), 
                    empid=application.empid).first()
            if summary:
                msg = f'Attendance summary already prepared for {application.start_date.strftime("%B")},{application.start_date.year}' 
                flash(msg, category='error')
                return redirect(url_for('leave.status_team'))

            leave = LeaveAvailable.query.filter_by(empid=employee.id).first()
            if not leave:
                current_app.logger.warning(' cancel_team(): no data found in leave_available table for %s', employee.username)
                msg = f'No leave available for {employee.username}'
                flash(msg, category='error')
                return redirect(url_for('leave.status_team'))
            
            if application.type == 'Casual':
                leave.casual = leave.casual + application.duration

            if application.type == 'Medical':
                leave.medical = leave.medical + application.duration
        
        if application.type == 'Casual adjust':
            update_apprleaveattn(employee.id, application.holiday_duty_start_date, application.holiday_duty_end_date, 'Holiday')

    #delete files attached with medical leave application
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
    
    update_apprleaveattn(employee.id, application.start_date, application.end_date, '')
    db.session.delete(application)
    db.session.commit()
    flash('Leave cancelled', category='message')

    #Send mail to all concerned
    email_found = True
    
    if not manager.email:
        current_app.logger.warning(' cancel_team(): Team Manager email not found for %s', employee.username)
        email_found = False

    if application.status == 'Approved':
        admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
        if not admin:
            current_app.logger.warning(' cancel_team(): Admin email not found')
            email_found = False

        head = Employee.query.join(Team).filter(Employee.department==employee.department, Employee.role=='Head').first()
        if not head:
            current_app.logger.warning('Dept. Head email not found')
            email_found = False
    
    if not email_found:
        flash('Failed to send mail', category='warning')
        return redirect(url_for('leave.status_team'))
    
    if application.status == 'Approved':
        rv = send_mail(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], sender=manager.email, 
                    receiver=admin.email, cc1=head.email, cc2=employee.email, cc3=manager.email, type='leave', 
                    application=application, action='cancelled')
    
    if application.status == 'Approval Pending':
        rv = send_mail(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], sender=manager.email, 
                    receiver=employee.email, cc1=manager.email, cc2=manager.email, type='leave', application=application, 
                    action='cancelled')

    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')
    
    return redirect(url_for('leave.application_status_team'))


@leave.route('/leave/cancel/team/fiber/<application_id>')
@login_required
@supervisor_required
def cancel_team_fiber(application_id):
    application = Applications.query.filter_by(id=application_id).first()
    if not application:
        flash('Leave application not found', category='error')
        return redirect(url_for('leave.status_team'))
    
    employee = Employee.query.join(Applications).filter(Applications.id==application_id).first()
    if not employee:
        current_app.logger.warning(' cancel_team(): employee details not found for application:%s', application_id)
        flash('Employee details not found for this application', category='error')
        return redirect(url_for('leave.status_team'))
    
    team = Team.query.filter_by(empid=application.empid).first()
    if not team:
        flash('Employee team not found for this application', category='error')
        current_app.logger.warning(' cancel_team(): team not found for %s', application.empid)
        return redirect(url_for('leave.application_status_team'))

    supervisor = Employee.query.join(Team).filter(Employee.id==session['empid'], Employee.role=='Supervisor', 
                Team.name==team.name).first()
    if not supervisor:
        flash('You are not authorized', category='error')
        current_app.logger.warning(' cancel_team(): not the supervisor of %s', team.name)
        return redirect(url_for('leave.application_status_team'))
    
    if application.status == 'Approved':
        if application.type == 'Casual' and application.type == 'Medical':
            leave_return_error = return_available_leave(employee.id, application.start_date, application.duration)
            if leave_return_error:
                flash(leave_return_error, category='error')
                return redirect(url_for('leave.application_status_team'))      
        
        if application.type == 'Casual adjust':
            update_apprleaveattn(employee.id, application.holiday_duty_start_date, application.holiday_duty_end_date, 'Holiday')

    #delete files attached with medical leave application
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
    
    update_apprleaveattn(employee.id, application.start_date, application.end_date, '')
    db.session.delete(application)
    db.session.commit()
    flash('Leave cancelled', category='message')

    #Send mail to all concerned
    email_found = True
    
    if not supervisor.email:
        current_app.logger.warning(' cancel_team(): Team Supervisor email not found for %s', employee.username)
        email_found = False

    if application.status == 'Approved':
        admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
        if not admin:
            current_app.logger.warning(' cancel_team(): Admin email not found')
            email_found = False

        manager = Employee.query.join(Team).filter(Employee.id==session['empid'], Employee.role=='Manager', 
                        Team.name==team.name).first()
        if not manager:
            manager_email = ''
        else:
            manager_email = manager.email

        head = Employee.query.join(Team).filter(Employee.department==employee.department, Employee.role=='Head').first()
        if not head:
            current_app.logger.warning('Dept. Head email not found')
            email_found = False
    
    if not email_found:
        flash('Failed to send mail', category='warning')
        return redirect(url_for('leave.application_status_team'))

    if application.status == 'Approved':
        rv = send_mail(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], sender=supervisor.email, 
                    receiver=admin.email, cc1=head.email, cc2=supervisor.email, cc3=manager_email, type='leave', 
                    application=application, action='cancelled')

    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')
    
    return redirect(url_for('leave.application_status_team'))

##Leave application cancel function for department##
@leave.route('/leave/cancel/department/<application_id>')
@login_required
@head_required
def cancel_department(application_id):
    application = Applications.query.filter_by(id=application_id).first()
    if not application:
        flash('Leave application not found', category='error')
        return redirect(url_for('leave.application_status_department'))
    
    employee = Employee.query.join(Applications).filter(Applications.id==application_id).first()
    if not employee:
        current_app.logger.warning(' cancel_department(): employee details not found for application:%s', application_id)
        flash('Employee details not found for this application', category='error')
        return redirect(url_for('leave.application_status_department'))

    head = Employee.query.filter_by(department=employee.department, id=session['empid'], role='Head').first()
    if not head:
        flash('You are not authorized', category='error')
        current_app.logger.warning(' cancel_department(): not the head of %s', employee.department)
        return redirect(url_for('leave.application_status_department'))
    
    if application.status == 'Approved':
        if application.type == 'Casual' and application.type == 'Medical':
            summary = AttnSummary.query.filter_by(year=application.start_date.year, month=application.start_date.strftime("%B"), 
                    empid=application.empid).first()
            if summary:
                msg = f'Attendance summary already prepared for {application.start_date.strftime("%B")},{application.start_date.year}' 
                flash(msg, category='error')
                return redirect(url_for('leave.application_status_department'))

            leave = LeaveAvailable.query.filter_by(empid=employee.id).first()
            if not leave:
                current_app.logger.warning(' cancel_department(): no data found in leave_available table for %s', employee.username)
                msg = f'No leave available for {employee.username}'
                flash(msg, category='error')
                return redirect(url_for('leave.application_status_department'))
        
            if application.type == 'Casual':
                leave.casual = leave.casual + application.duration

            if application.type == 'Medical':
                leave.medical = leave.medical + application.duration
        
        if application.type == 'Casual adjust':
            update_apprleaveattn(employee.id, application.holiday_duty_start_date, application.holiday_duty_end_date, 'Holiday')

    #delete files attached with medical leave application
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

    update_apprleaveattn(employee.id, application.start_date, application.end_date, '')
    db.session.delete(application)
    db.session.commit()
    flash('Leave cancelled', category='message')

    #Send mail to all concerned
    email_found = True

    if employee.role == 'Team':
        manager = Employee.query.join(Team).filter(Team.name==employee.teams[0].name, Employee.role=='Manager').first()
        if not manager.email:
            current_app.logger.warning(' cancel_department(): Team Manager email not found for %s', employee.username)
            email_found = False

    if application.status == 'Approved':
        admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
        if not admin:
            current_app.logger.warning(' cancel_department(): Admin email not found')
            email_found = False

        head = Employee.query.join(Team).filter(Employee.department==employee.department, Employee.role=='Head').first()
        if not head:
            current_app.logger.warning('Dept. Head email not found')
            email_found = False
    
    if not email_found:
        flash('Failed to send mail', category='warning')
        return redirect(url_for('leave.application_status_department'))
    
    if employee.role != 'Team':
            manager.email = None

    if application.status == 'Approved': 
        rv = send_mail(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], sender=head.email, 
                    receiver=admin.email, cc1=employee.email, cc2=manager.email, cc3=head.email, type='leave', 
                    application=application, action='cancelled')
    
    if application.status == 'Approval Pending':
        rv = send_mail(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], sender=head.email, 
                    receiver=employee.email, cc2=manager.email, cc3=head.email, type='leave', application=application, 
                    action='cancelled')

    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')
    
    return redirect(url_for('leave.application_status_department'))

##Leave summary personal##
@leave.route('/leave/summary/self')
@login_required     
def summary_self():
    leaves = LeaveAvailable.query.join(Employee).filter(Employee.id==session['empid'], 
                and_(LeaveAvailable.year_start < datetime.datetime.now().date(), 
                LeaveAvailable.year_end > datetime.datetime.now().date())).all()
    if not leaves:
        current_app.logger.warning('summary_self(): No data found in leave_available table for %s', session['empid'])
        flash('No leave summary record found', category='warning')

    return render_template('data.html', data_type='leave_summary', leaves=leaves)

##Leave summary team##
@leave.route('/leave/summary/team')
@login_required
@manager_required     
def summary_team():
    teams = Team.query.filter_by(empid=session['empid']).all()
    team_leaves = []
    
    for team in teams:
        leaves = LeaveAvailable.query.join(Employee, Team).filter(Team.name==team.name, Employee.id!=session['empid'], 
                and_(LeaveAvailable.year_start < datetime.datetime.now().date(), 
                LeaveAvailable.year_end > datetime.datetime.now().date())).all()
        team_leaves += leaves
    
    leaves = team_leaves
    
    if not leaves:
        current_app.logger.warning('summary_team(): No data found in leave_available table')
        flash('No leave summary record found', category='warning')

    return render_template('data.html', data_type='leave_summary', leaves=leaves)

##Leave summary department##
@leave.route('/leave/summary/department')
@login_required
@head_required     
def summary_department():
    leaves = LeaveAvailable.query.join(Employee).\
                filter(Employee.department==session['department'], Employee.id!=session['empid'],  
                and_(LeaveAvailable.year_start < datetime.datetime.now().date(), 
                LeaveAvailable.year_end > datetime.datetime.now().date())).all()
    
    if not leaves:
        current_app.logger.warning('summary_department(): No data found in leave_available table')
        flash('No leave summary record found', category='warning')

    return render_template('data.html', data_type='leave_summary', leaves=leaves)

##Leave summary all##
@leave.route('/leave/summary/all')
@login_required     
def summary_all():
    leaves = LeaveAvailable.query.join(Employee).filter(or_(LeaveAvailable.year_start < datetime.datetime.now().date(), 
                LeaveAvailable.year_end > datetime.datetime.now().date())).all()
                
    if not leaves:
        current_app.logger.warning('summary_self(): No data found in leave_available table for %s', session['empid'])
        flash('No leave summary record found', category='warning')

    return render_template('data.html', data_type='leave_summary', leaves=leaves)

@leave.route('/leave/files/<name>')
@login_required
def files(name):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], name)

##Leave approval for Teams##
@leave.route('/leave/approval/team')
@login_required
@manager_required
def approval_team():
    application_id = request.args.get('application_id')
    
    application = Applications.query.filter_by(id=application_id).one()
    team = Team.query.filter_by(empid=application.empid).first()
    
    manager = Employee.query.join(Team).filter(Team.name==team.name, Employee.role=='Manager').one()
    if manager.username != session['username']:
        flash('You are not authorized', category='error')
        return redirect(url_for('leave.applicatio_status_team'))

    summary = AttnSummary.query.filter_by(year=application.start_date.year, month=application.start_date.strftime("%B"), 
                empid=application.empid).first()
    if summary:
        msg = f'Attendance summary already prepared for {application.start_date.strftime("%B")},{application.start_date.year}' 
        flash(msg, category='error')
        return redirect(url_for('leave.application_status_team'))

    if application.type == 'Casual' or application.type == 'Medical':
        available = check_available_leave(application.empid, application.start_date, application.duration, application.type, 'update')
        if not available:
            flash('Leave not available, please check leave summary', category='error')
            return redirect(url_for('leave.applicaion_status_team'))
    
    if application.type == 'Casual adjust' and application.holiday_duty_type == 'On site':
        update_apprleaveattn(application.empid, application.holiday_duty_start_date, application.holiday_duty_end_date, '')

    application = Applications.query.filter_by(id=application_id).first()
    application.status = 'Approved'

    update_apprleaveattn(application.empid, application.start_date, application.end_date, application.type)
    flash('Leave approved', category='message')
    
    #Send mail to all concerned
    admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
    if not admin:
        current_app.logger.warning('approval(): Admin email not found for employee id: %s', application.employee.id)
        rv = 'failed'
    
    head = Employee.query.filter(Employee.department==manager.department, Employee.role=='Head').first()
    if not head:
        current_app.logger.warning('approval(): Dept. head email not found for employee id: %s', application.employee.id)
        rv = 'failed'
    
    if 'rv' in locals():
        flash('Failed to send mail', category='warning')
        return redirect(url_for('leave.application_status_team'))

    host = current_app.config['SMTP_HOST']
    port = current_app.config['SMTP_PORT'] 
    rv = send_mail(host=host, port=port, sender=manager.email, receiver=admin.email, cc1=application.employee.email, 
            cc2=head.email, cc3=manager.email, application=application, type='leave', action='approved')
    
    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')
    
    return redirect(url_for('leave.application_status_team'))

##Leave approval for Department by Head##
@leave.route('/leave/approval/department')
@login_required
@head_required
def approval_department():
    application_id = request.args.get('application_id')

    application = Applications.query.join(Employee).filter(Applications.id==application_id).first()
   
    department_head = Employee.query.filter(Employee.id==session['empid'], Employee.department==application.employee.department, 
                        Employee.role=='Head').one()
    if not department_head:
        flash('You are not authorized', category='error')
        return redirect(url_for('leave.application_status_department'))
    
    summary = AttnSummary.query.filter_by(year=application.start_date.year, month=application.start_date.strftime("%B"), 
                empid=application.empid).first()
    if summary:
        msg = f'Attendance summary already prepared for {application.start_date.strftime("%B")},{application.start_date.year}' 
        flash(msg, category='error')
        return redirect(url_for('leave.application_status_department'))

    if application.type == 'Casual' or application.type == 'Medical':
        available = check_available_leave(application.empid, application.start_date, application.duration, application.type, 'update')
        if not available:
            flash('Leave not available, please check leave summary', category='error')
            return redirect(request.url)

    if application.type == 'Casual adjust' and application.holiday_duty_type == 'On site':
        update_apprleaveattn(application.empid, application.holiday_duty_start_date, application.holiday_duty_end_date, '')
    
    application.status = 'Approved'
    update_apprleaveattn(application.empid, application.start_date, application.end_date, application.type)
    flash('Application approved', category='message')
    
    #Send mail to all concerned
    error = False
    
    admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
    if not admin:
        current_app.logger.warning('approval_department(): Admin email not found for employee id: %s', application.employee.id)
        error = True
    
    if application.employee.role == 'Team':
        team = Team.query.filter_by(empid=application.empid).first()
        manager = Employee.query.join(Team).filter(Team.name==team.name, Employee.role=='Manager').first()
        if not manager:
            current_app.logger.warning('approval_department(): manager email not found for employee %s', application.employee.username)
            error = True

    if error:
        flash('Failed to send mail', category='warning')
        return redirect(url_for('leave.application_status_department'))
    
    if application.employee.role != 'Team':
        manager.email = None

    rv = send_mail(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], sender=department_head.email, 
            receiver=admin.email, cc1=application.employee.email, cc2=manager.email, cc3=department_head.email, 
            application=application, type='leave', action='approved')
    
    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')
    
    return redirect(url_for('leave.application_status_department'))

## Leave deduction function ##
@leave.route('/leave/deduction', methods=['GET', 'POST'])
@login_required
@admin_required
def deduction():
    form = Leavededuction()

    month = datetime.datetime.strptime(form.month.data, '%B').month
    cur_month = datetime.datetime.now().month
    cur_year = datetime.datetime.now().year

    if month >= cur_month and int(form.year.data) >= cur_year:
        flash('You can only deduct leave for attendance of previous month or before previous month', category='error')    
        return redirect(url_for('forms.leave_deduction'))
    
    deducted = LeaveDeduction.query.filter_by(month=form.month.data, year=form.year.data).first()
    if deducted:
        flash('You have already deducted leave for this month', category='error')
        return redirect(url_for('forms.leave_deduction'))

    summary = AttnSummary.query.filter(AttnSummary.year==form.year.data).filter(AttnSummary.month==form.month.data).all()
    if summary:
        for employee in summary:
            if employee.late >= 3 or employee.early >= 3:
                summary = AttnSummary.query.filter_by(empid=employee.empid, year=form.year.data, 
                            month=form.month.data).first()
                leave = LeaveAvailable.query.filter(LeaveAvailable.empid==employee.empid).first()
                total_leave = leave.casual + leave.earned
                total_deduct = round(employee.late/3) + round(employee.early/3)
                
                if leave.casual >= total_deduct:
                    leave.casual = leave.casual - total_deduct
                    summary.extra_absent = 0
                    summary.leave_deducted = total_deduct
                elif total_leave >= total_deduct:
                    leave.earned = leave.earned + leave.casual - total_deduct
                    leave.casual = 0
                    summary.extra_absent = 0
                    summary.leave_deducted = total_deduct
                else:    
                    summary.extra_absent = total_deduct - total_leave
                    leave.casual = 0
                    leave.earned = 0
                    summary.leave_deducted = total_leave
         
        deduction = LeaveDeduction(year=form.year.data, month=form.month.data, date=datetime.datetime.now())
        
        db.session.add(deduction)
        db.session.commit()
        flash('Leave deducted')
    else:
        flash('No record found in attendance summary', category='warning')
    
    return redirect(url_for('forms.leave_deduction'))

@leave.route('/leave/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_leave():
    form = Createleave()
    
    if form.validate_on_submit():
        year_start = datetime.date(form.year_start.data, 7, 1)
        year_end = datetime.date(form.year_start.data + 1, 6, 30)

        employees = Employee.query.all()
        count = 0
        for employee in employees:
            leave_available = LeaveAvailable.query.filter(LeaveAvailable.year_start <= year_start, 
                                LeaveAvailable.year_end >= year_end, LeaveAvailable.empid==employee.id).first()
            if leave_available:
                message = f'Leave exists for {employee.fullname} year: {leave_available.year_start} - {leave_available.year_end}'
                flash(message, category='warning')
            else:
                leave_available = LeaveAvailable(empid=employee.id, year_start=year_start, year_end=year_end, 
                                    casual=current_app.config['CASUAL'], medical=current_app.config['MEDICAL'], 
                                    earned=current_app.config['EARNED'])
                db.session.add(leave_available)
                count += 1
        
        if count:
            db.session.commit()
            form.year_end.data = form.year_start.data + 1
            message = f'Leave added for {count} employees for {form.year_start.data}-{form.year_end.data}'
            flash(message, category='message')
        else:
            flash('No leave added', category='error')

        return render_template('base.html')
    else:
        return render_template('forms.html', type='create_leave', form=form)