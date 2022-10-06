from calendar import monthrange
from crypt import methods
from curses.ascii import EM
from dataclasses import dataclass
from datetime import datetime, timedelta
import os
from re import search
from time import strftime
from flask import Blueprint, current_app, request, flash, redirect, render_template, send_from_directory, session, url_for
from sqlalchemy import and_, or_, extract, func, select
import pandas as pd
from attendance.leave import update_apprleaveattn
from .check import check_access, check_application_dates, check_attnsummary
from .mail import send_mail, send_mail2
from .forms import (Addholidays, Attnapplfiber, Attnquerydate, Attnqueryusername, Attndataupload, Attnapplication, Attnsummaryshow, Dutyshiftcreate, Attendancesummaryprepare, Attendancesummaryshow, Monthyear, Dutyscheduleupload)
from .db import *
from .auth import head_required, login_required, admin_required, manager_required, supervisor_required, team_leader_required
from .functions import check_edit_permission, check_holidays, convert_team_name, find_team_leader_email, get_concern_emails, update_applications_holidays, check_team_access, check_view_permission, convert_team_name2, check_data_access

# file extensions allowed to be uploaded
ALLOWED_EXTENSIONS = {'xls', 'xlsx'}

# Column names in SQL database
col_names = ['empid', 'date', 'in_time', 'out_time']

# Convert month names to number
def month_name_num(month):
    months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 
                'October', 'November', 'December']
    return months.index(month) + 1

attendance = Blueprint('attendance', __name__)

# Upload attendance data to database
@attendance.route('/attendance/upload', methods=['GET', 'POST'])
@login_required
@admin_required
def upload():
    form = Attndataupload()
    
    if form.validate_on_submit():
            df = pd.read_excel(form.file1.data, names=col_names)
           
            for i in range(len(df.index)):
                empid = int(df.iat[i, 0])
                date = datetime.strptime(df.iat[i, 1], "%m/%d/%Y").date()
                
                if pd.isna(df.iat[i, 2]):
                    df_in_time = '00:00'
                else:
                    df_in_time = df.iat[i, 2]

                in_time = datetime.strptime(str(df_in_time), "%H:%M").time()
                
                if pd.isna(df.iat[i, 3]):
                    df_out_time = '00:00'
                else:
                    df_out_time = df.iat[i, 3]

                out_time = datetime.strptime(str(df_out_time), "%H:%M").time()

                employee = Employee.query.filter_by(id=empid).first()
                if not employee:
                    error = 'Employee ID' + " '" + str(empid) + "' " + 'does not exists'
                    flash(error, category='error')
                    return redirect(request.url)
                
                record_exists = Attendance.query.filter(Attendance.empid==empid, Attendance.date==date).first()
                if record_exists:
                    error = f"Employee ID '{str(empid)}' & date '{date}' record already exists in database or duplicate data in uploaded file"
                    flash(error, category='error')
                    return redirect(request.url)
                
                application = Applications.query.filter(Applications.empid==empid, Applications.start_date<=date, 
                                Applications.end_date>=date, Applications.status=='Approved').first()
                
                team = Team.query.filter_by(empid=employee.id).first()
                if not team:
                    msg = f'Team name not found for {employee.fullname}'
                    flash(msg, category='error')
                    return redirect(url_for('forms.upload'))

                match = search(r'^Fiber', team.name)
                holiday = Holidays.query.filter(Holidays.start_date<=date, Holidays.end_date>=date).first()

                if application:
                    application_id = application.id
                else:
                    application_id = None

                if holiday:
                    holiday_id = holiday.id
                else:
                    holiday_id = None

                day_name = date.strftime("%A")
                if  day_name == 'Friday':
                    weekend_id = 7
                elif day_name == 'Saturday':
                    if not match:
                        weekend_id = 1
                    else:
                        weekend_id = None
                else:
                    weekend_id = None     

                applications_holidays = ApplicationsHolidays(empid=empid, date=date, application_id=application_id, holiday_id=holiday_id, weekend_id=weekend_id)
                db.session.add(applications_holidays)

                attendance = Attendance(empid=empid, date=date, in_time=in_time, out_time=out_time)
                db.session.add(attendance)

            db.session.commit()

            flash('Data uploaded successfully', category='message')
            
    return render_template('forms.html', form_type='attendance_upload', form=form)

##Attendance query menu for all#
@attendance.route('/attendance/query/menu')
@login_required
def query_menu():
    return render_template('attn_query.html')


@attendance.route('/attendance/files/<name>')
@login_required
@team_leader_required
def files(name):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], name)


##Attendance application##
@attendance.route('/attendance/application', methods=['GET', 'POST'])
@login_required
def application():
    form = Attnapplication()
    employee = Employee.query.filter_by(username=session['username']).first()
    
    if form.validate_on_submit():

        msg = check_application_dates(session['empid'], form.start_date.data, form.end_date.data)
        if msg:
            flash(msg, category='error')
            return redirect(url_for('forms.attn_application'))
        
        #submit application
        if form.end_date.data: 
            duration = (form.end_date.data - form.start_date.data).days + 1
        else:
            duration = 1
        
        if not form.end_date.data:
            form.end_date.data = form.start_date.data
        
        application = Applications(empid=employee.id, start_date=form.start_date.data, end_date=form.end_date.data, duration=duration, type=form.type.data, remark=form.remark.data, submission_date=datetime.now(), status='Approval Pending')
        db.session.add(application)
        db.session.commit()
        flash('Attendance application submitted')

        #Send mail to all concerned
        application = Applications.query.filter_by(start_date=form.start_date.data, end_date=form.end_date.data, type=form.type.data, empid=session['empid']).first()
       
        emails = get_concern_emails(application.empid)
        if emails['employee'] == '':
            flash('Failed to send mail', category='warning')
            return redirect(request.url)

        team_leader_email = find_team_leader_email(emails)
        if not team_leader_email:
            flash('Failed to send mail', category='warning')
            return redirect(request.url)
        
        rv = send_mail2(sender=emails['employee'], receiver=team_leader_email, type='attendance', application=application, action='submitted')
        
        if rv:
            current_app.logger.warning(rv)
            flash('Failed to send mail', category='warning')
            return redirect(request.url)
    else:
        return render_template('forms.html', type='attn_application', form=form)
    
    return redirect(url_for('forms.attn_application'))


##Attendance application details##
@attendance.route('/attendance/application/details/<application_id>')
@login_required
def application_details(application_id):
    rv = check_access(application_id)
    
    if not rv:
        flash('You are not authorized to see this record', category='error')
        return redirect(url_for('attendance.appl_status_self', type=type))

    details = Applications.query.join(Employee).filter(Applications.id==application_id).first()
    return render_template('data.html', type='attn_appl_details', details=details)


@attendance.route('/attendance/application/approval')
@login_required
@team_leader_required
def approval():
    application_id = request.args.get('application_id')
    
    if not check_team_access(application_id):
        flash('You are not authorized to perform this action', category='error')
        return redirect(url_for('attendance.appl_status_team'))

    application = Applications.query.filter_by(id=application_id).first()
    start_date = application.start_date
    end_date = application.end_date
    
    update_applications_holidays(application.empid, start_date, end_date, application_id)
    
    application.status = 'Approved'
    application.approval_date = datetime.now()
    db.session.commit()
    flash('Application approved')
    
    #Send mail to all concerned
    emails = get_concern_emails(application.empid)
    team_leader_email = find_team_leader_email(emails)
    cc = [session['email']]
    
    if emails['employee'] != '':
        cc.append(emails['employee'])
    
    if team_leader_email:
        cc.append(team_leader_email)

    rv = send_mail2(sender=session['email'], receiver=emails['admin'], cc=cc, type='attendance', action='approved', application=application)

    if rv:
        msg = 'Mail sending failed (' + str(rv) + ')' 
        flash(msg, category='warning')
    
    return redirect(url_for('attendance.application_status', application_for='team'))

##Attendance application approval for Department##
@attendance.route('/attendance/application/approval/department')
@login_required
@head_required
def approval_department():
    application_id = request.args.get('application_id')
    if not check_access(application_id):
        flash('You are not authorizes to perform this action', category='error')
        return redirect(url_for('attendance.appl_status_department'))

    application = Applications.query.filter_by(id=application_id).first()
    update_apprleaveattn(application.empid, application.start_date, application.end_date, request.args.get('type'))
    
    application.status = 'Approved'
    application.approval_date = datetime.now()
    db.session.commit()
    flash('Application approved')
    
    #Send mail to all concerned
    error = False

    if not session['email']:
        current_app.logger.warning('approval_department(): Head email not found for employee id: %s', application.employee.id)
        error = True

    admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
    if not admin:
        current_app.logger.warning('approval_department(): Admin email not found for employee id: %s', application.employee.id)
        error = True
    
    if application.employee.role == 'Team' or application.employee.role == 'Supervisor':
        team = Team.query.filter_by(empid=application.empid).first()
        manager = Employee.query.join(Team).filter(Team.name==team.name, Employee.role=='Manager').first()
    
        if not manager:
            manager_email = ''
        else:
            manager_email = manager.email
    else:
        manager_email = ''

    if error:
        flash('Failed to send mail', category='warning')
        return redirect(url_for('attendance.appl_status_department'))
    
    rv = send_mail(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], sender=session['email'], 
            receiver=admin.email, cc1=application.employee.email, cc2=manager_email, application=application, type='attendance', 
            action='approved')
    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')
        return redirect(url_for('attendance.appl_status_department'))

    return redirect(url_for('attendance.appl_status_department'))

#Update attn_summary table with attendance summary data for each employee
@attendance.route('/attendance/prepare_summary', methods=['GET', 'POST'])
@login_required
@admin_required
def prepare_summary():
    form = Attnquery()

    if form.validate_on_submit():
        current_month = datetime.now().month
        current_year = datetime.now().year

        if form.month.data >= current_month and current_year >= form.year.data:
            flash('You can only prepare attendance summary of previous month or before previous month', category='error')    
            return redirect(url_for('forms.attn_prepare_summary'))
            
        summary = AttendanceSummary.query.filter_by(year=form.year.data, month=form.month.data).first()
        if summary:
            flash('Summary data already exists for the year and month you submitted', category='error')
            return redirect(url_for('forms.attn_prepare_summary'))
    
        employees = Employee.query.all()

        count = 0
        for employee in employees:
            attendances = Attendance.query.with_entities(Attendance.date, Attendance.in_time, Attendance.out_time, ApplicationsHolidays.application_id, ApplicationsHolidays.holiday_id, ApplicationsHolidays.weekend_id).join(ApplicationsHolidays, and_(Attendance.empid==ApplicationsHolidays.empid, Attendance.date==ApplicationsHolidays.date)).filter(Attendance.empid==employee.id, extract('month', Attendance.date)==form.month.data, extract('year', Attendance.date)==form.year.data).all()
            
            absent_count = 0
            late_count = 0
            early_count = 0
            
            for attendance in attendances:
                if attendance.holiday_id:
                    continue
                
                if attendance.weekend_id:
                    continue

                if attendance.application_id:
                    application = Applications.query.filter_by(id=attendance.application_id).first()
                    if application.type in ('Casual', 'Medical', 'Both'):
                        continue
                    else:
                        application_type = application.type
                else:
                    application_type = ''

                duty_schedule = DutySchedule.query.join(DutyShift).filter(DutySchedule.empid==employee.id, DutySchedule.date==attendance.date).first()
                
                if duty_schedule:
                    standard_in_time = duty_schedule.dutyshift.in_time
                    standard_out_time = duty_schedule.dutyshift.out_time
                else:
                    standard_in_time = datetime.strptime(current_app.config['LATE'], '%H:%M:%S').time()
                    standard_out_time = datetime.strptime(current_app.config['EARLY'], '%H:%M:%S').time()

                no_attendance = datetime.strptime('00:00:00', '%H:%M:%S').time()
                if attendance.in_time == no_attendance:
                    absent_count += 1

                if attendance.in_time > standard_in_time and application_type != 'In':
                    late_count += 1

                if attendance.out_time < standard_out_time or attendance.out_time == no_attendance:
                    if application_type != 'Out':
                        early_count += 1

            if absent_count > 0 or late_count > 0 or early_count > 0:
                attnsummary = AttendanceSummary(empid=employee.id, year=form.year.data, month=form.month.data, absent=absent_count, late=late_count, early=early_count)
                db.session.add(attnsummary)
                count += 1
            
        if count == 0:
            flash('No late or absent in attendance data', category='warning')
        else:
            db.session.commit()
            flash('Attendance summary created', category='message')
    else:
        flash('Form data not correct', category='error')
    
    return redirect(url_for('forms.attn_prepare_summary')) 

##Casual and Medical attendance application submission for Fiber##
@attendance.route('/attendance/application/fiber', methods=['GET', 'POST'])
@login_required
@supervisor_required
def application_fiber():
    form = Attnapplfiber()

    if form.validate_on_submit():
        employee = Employee.query.filter_by(id=form.empid.data).first()
        if not employee:
            flash('Employee does not exists', category='error')
            return redirect(url_for('forms.attn_fiber'))
        
        msg = check_application_dates(employee.id, form.start_date.data, form.end_date.data)
        if msg:
            flash(msg, category='error')
            return redirect(url_for('forms.attn_fiber'))
            
        if not form.end_date.data:
            form.end_date.data = form.start_date.data

        duration = (form.end_date.data - form.start_date.data).days + 1

        application = Applications(empid=employee.id, start_date=form.start_date.data, end_date=form.end_date.data, duration=duration, type=form.type.data, remark=form.remark.data, submission_date=datetime.now(), status='Approved')
        db.session.add(application)
        db.session.commit()
        flash('Attendance application approved', category='message')
        
        application = Applications.query.filter_by(empid=employee.id, start_date=form.start_date.data, end_date=form.end_date.data, type=form.type.data).first()
        if not application:
            current_app.logger.error('Application employee: %s, type: %s, start_date: %s, end_date: %s not found', employee.id, form.start_date.data, form.end_date.data, form.type.data)
            return redirect(url_for('forms.attn_fiber'))

        update_applications_holidays(employee.id, form.start_date.data, form.end_date.data, application.id)
        db.session.commit()
        
        #Send mail to all concerned
        supervisor = Employee.query.join(Team).filter(Team.name==session['team'], Employee.role=='Supervisor').first()
        if supervisor:
            if not supervisor.email:
                current_app.logger.warning('application_fiber(): Supervisor email not found for %s', session['username'])
                rv = 'failed'
        else:
            current_app.logger.warning('application_fiber(): Supervisor email not found for %s', session['username'])
            rv = 'failed'

        manager = Employee.query.join(Team).filter(Team.name==session['team'], Employee.role=='Manager').first()
        if not manager:
            manager_email = ''
        else:
            manager_email = manager.email

        admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
        if not admin:
            current_app.logger.warning('application_fiber(): Admin email not found')
            rv = 'failed'

        head = Employee.query.filter(Employee.department==session['department'], Employee.role=='Head').first()
        if not head:
            current_app.logger.warning('application_fiber(): Dept. head email not found')
            rv = 'failed'
        
        if 'rv' in locals():
            flash('Failed to send mail', category='warning')
            return redirect(url_for('forms.attn_fiber'))
        
        host = current_app.config['SMTP_HOST']
        port = current_app.config['SMTP_PORT']
        rv = send_mail(host=host, port=port, sender=supervisor.email, receiver=admin.email, cc1=manager_email, cc2=head.email, application=application, type='attendance', action='approved')
        
        if rv:
            current_app.logger.warning(rv)
            flash('Failed to send mail', category='warning')
            return redirect(url_for('forms.attn_fiber'))

    else:
        return render_template('forms.html', type='leave', leave=type, team='fiber', form=form)

    return redirect(url_for('forms.attn_fiber'))


@attendance.route('/attendance/duty_schedule/<action>', methods=['GET', 'POST'])
@login_required
@team_leader_required
def duty_schedule(action):
    if action not in ('query', 'upload', 'delete'):
        current_app.logger.error(' duty_schedule() - action unknown')
        flash('Unknown action', category='error')
        return render_template('base.html')
       

    if action == 'query':
        form = Monthyear()

        if form.validate_on_submit():
            month = form.month.data
            year = form.year.data
        else:
            month = datetime.now().month
            year = datetime.now().year
        
        if session['role'] == 'Head':
            employees = Employee.query.join(Team).filter(Employee.department==session['department']).order_by(Team.name).all()
        elif session['access'] == 'Admin':
            employees = Employee.query.join(Team).filter(Employee.department=='Technical').order_by(Team.name).all()
        elif session['role'] in ('Supervisor', 'Manager'):
            team_name = convert_team_name()
            team_name_string = f'{team_name}' + '%'
            employees = Employee.query.join(Team).filter(Team.name.like(team_name_string)).all()
        else:
            flash('You are not authorized to access this function', category='error')
            return redirect(url_for('forms.duty_schedule', action='query'))

        schedules = []
        for employee in employees:
            team = Team.query.filter_by(empid=employee.id).first()

            dates = DutySchedule.query.join(DutyShift, isouter=True).with_entities(DutyShift.name.label('shift')).filter(DutySchedule.empid==employee.id, extract('month', DutySchedule.date)==month, extract('year', DutySchedule.date==year)).order_by(DutySchedule.date).all()
            
            if dates:
                individual_schedule = [employee.fullname, team.name]

                count = 0
                for date in dates:
                    if date.shift is not None:
                        count += 1
                    
                    individual_schedule.append(date.shift)
                
                if count > 0:
                    schedules.append(individual_schedule)

        month_days = monthrange(form.year.data,form.month.data)[1]
        return render_template('data.html', type='duty_schedule', month_days=month_days, schedules=schedules, form=form)

    if action == 'upload':
        form = Dutyscheduleupload()

        if not form.validate_on_submit():
            return render_template('forms.html', form_type='upload_duty_schedule', form=form)

        attnsummary_prepared = AttendanceSummary.query.filter_by(month=form.month.data, year=form.year.data).all()
        if attnsummary_prepared:
            msg = 'Cannot upload duty schedule. Attendance summary already prepared for {form.month.data}, {form.year.data}'
            return redirect(url_for('forms.duty_shcedule', action='upload'))
        
        if session['role'] in ('Supervisor', 'Manager'):
            team_leader = Employee.query.join(Team).filter(Employee.id==session['empid']).first()
            if not team_leader:
                current_app.logger.error(" duty_schedule(action='upload'): Employee details not found for %s", session['username'])
                msg = f"Employee details not found for '{session['username']}'"
                flash(msg, category='error')
                return redirect(url_for('forms.duty_shcedule', action='upload'))

            team_leader_teams = []
            for team in team_leader.teams:
                team_leader_teams.append(convert_team_name2(team.name))

        if session['role'] == 'Head':
            head = Employee.query.filter_by(id=session['empid']).first()

        df = pd.read_excel(form.file.data, header=None)
        days_of_month = monthrange(form.year.data, form.month.data)[1]
        
        if len(df.columns) != days_of_month + 1:
            msg = f'There should be name and {days_of_month} shifts in the excel file'
            flash(msg, category='error')
            return redirect(url_for('forms.duty_schedule', action='upload'))

        for i in range(len(df.index)):
            fullname = df.iat[i, 0]
            
            employee = Employee.query.join(Team).filter(Employee.fullname==fullname).first()
            if not employee:
                msg = f'Employee not found with name: {fullname}'
                flash(msg, category='error')
                return redirect(url_for('forms.duty_schedule', action='upload'))
            
            employee_team_name = convert_team_name2(employee.teams[0].name)

            if session['role'] in ('Supervisor', 'Manager'):
                if employee_team_name not in team_leader_teams:
                    msg = f'Employee "{fullname}" is not in your team'
                    flash(msg, category='error')
                    return redirect(url_for('forms.duty_schedule', action='upload'))

            if session['role'] == 'Head':
                if employee.department != head.department:
                    msg = f'Employee "{fullname}" is not in your department'
                    flash(msg, category='error')
                    return redirect(url_for('forms.duty_schedule', action='upload'))

            for j in range(len(df.columns)):
                if j == 0:
                    continue

                date = datetime(form.year.data, form.month.data, j).date()

                duty_schedule = DutySchedule.query.filter_by(empid=employee.id, date=date, team=team_name).first()
                if duty_schedule:
                    msg = f'Duty schedule exist for {fullname} on date {date}'
                    flash(msg, category='error')
                    return redirect(url_for('forms.duty_schedule', action='upload'))
                
                if pd.isna(df.iat[i, j]):
                    msg = f'Duty shift missing for {fullname} on date {j}'
                    flash(msg, category='error')
                    return redirect(url_for('forms.duty_schedule', action='upload'))

                duty_shift = DutyShift.query.filter_by(name=str(df.iat[i, j]).upper(), team=team_name).first()
                if not duty_shift:
                    msg = f'Duty shift "{df.iat[i, j]}" not found'
                    flash(msg, category='error')
                    return redirect(url_for('forms.duty_schedule', action='upload'))
                
                duty_schedule = DutySchedule(empid=employee.id, team=team_name, date=date, duty_shift=duty_shift.id)
                db.session.add(duty_schedule)

        db.session.commit()
        flash('Duty schedule uploaded')
        return redirect(url_for('attendance.duty_schedule', action='query'))
    
    if action == 'delete':
        form = Monthyear()

        if not form.validate_on_submit():
            return render_template('forms.html', type='duty_schedule', action='delete', form=form)

        attnsummary_prepared = AttendanceSummary.query.filter_by(month=form.month.data, year=form.year.data).all()
        if attnsummary_prepared:
            msg = 'Cannot delete duty schedule. Attendance summary already prepared for {form.month.data}, {form.year.data}'
            return redirect(url_for('forms.duty_schedule', action='delete'))
        
        duty_schedules = DutySchedule.query.filter(extract('month', DutySchedule.date)==form.month.data, extract('year', DutySchedule.date)==form.year.data, DutySchedule.team==team_name).all()
        
        if not duty_schedules:
            msg = f'Schedule does not exist for {form.month.data}, {form.year.data}'
            flash(msg, category='error')
            return redirect(url_for('forms.duty_schedule', action='delete'))
        
        for duty_schedule in duty_schedules:
            db.session.delete(duty_schedule)
 
        db.session.commit()
        
        flash('Duty schedule deleted', category='message')
        return redirect(url_for('attendance.duty_schedule', action='query'))


@attendance.route('/attendance/duty_shift/<action>', methods=['GET', 'POST'])
@login_required
@team_leader_required
def duty_shift(action):
    if action != 'query' and action != 'create' and action != 'delete':
        current_app.logger.error(' duty_shift() - action unknown')
        flash('Unknown action', category='error')
        return render_template('base.html')

    if action == 'query':
        if session['role'] == 'Head' or session['access'] == 'Admin':
            shifts = DutyShift.query.all()
        else:
            team_name = convert_team_name()
            shifts = DutyShift.query.filter(DutyShift.team==team_name).all() 
        
        return render_template('data.html', type='duty_shift', shifts=shifts)
    
    if action == 'create':
        form = Dutyshiftcreate()
        
        if form.validate_on_submit():
            shift_exist = DutyShift.query.filter(DutyShift.in_time==form.in_time.data, DutyShift.out_time==form.out_time.data, 
                            DutyShift.team==team_name).all()
            if shift_exist:
                flash('Shift exists', category='error')
                return redirect(url_for('forms.duty_shift_create', form=form))
        
            duty_shift = DutyShift(team=team_name, name=form.shift_name.data, in_time=form.in_time.data, 
                            out_time=form.out_time.data)
            db.session.add(duty_shift)
            db.session.commit()

            flash('Duty shift created', category='message')
            return redirect(url_for('attendance.duty_shift', action='query'))

    if action == 'delete':
        shift_id = request.args.get('shift_id')
        
        shift = DutyShift.query.filter_by(id=shift_id).one()
        if not shift:
            flash('Shift not found', category='error')
            current_app.logger.warning('duty_shift(action="delete"): Shift id not found')
            return redirect(url_for('attendance.duty_shift', action='query'))
        
        shift_exist = DutySchedule.query.filter_by(shift=shift.id).all()
        if shift_exist:
            flash('Shift exist in duty schedule', category='error')
            return redirect(url_for('attendance.duty_shift', action='query'))

        db.session.delete(shift)
        db.session.commit()

        flash('Duty shift deleted', category='message')
        return redirect(url_for('attendance.duty_shift', action='query'))


@attendance.route('/attendance/holidays/<action>', methods=['GET', 'POST'])
@login_required
@admin_required
def holidays(action):
    
    if action == 'show':
        holidays = Holidays.query.filter(extract('year', Holidays.start_date)==datetime.now().year, extract('year', Holidays.end_date)==datetime.now().year).all()
        return render_template('data.html', type='holidays', holidays=holidays)
    elif action == 'add':
        form = Addholidays()

        if form.validate_on_submit():
            if not form.end_date.data:
                form.end_date.data = form.start_date.data
            
            rv = check_attnsummary(form.start_date.data, form.end_date.data)
            if rv:
                flash(rv, category='error')
                return redirect(url_for('attendance.holidays', action='show'))
            
            holiday_exists = check_holidays(form.name.data, form.start_date.data, form.end_date.data)
            if holiday_exists:
                    flash(holiday_exists, category='error')
                    return redirect(url_for('attendance.holidays', action='show'))
            
            duration = (form.end_date.data - form.start_date.data).days + 1

            holiday = Holidays(name=form.name.data, start_date=form.start_date.data, end_date=form.end_date.data, duration=duration)
            db.session.add(holiday)
            db.session.commit()

            holiday = Holidays.query.filter_by(name=form.name.data, start_date=form.start_date.data, end_date=form.end_date.data).first()
            if holiday:
                dates = ApplicationsHolidays.query.filter(ApplicationsHolidays.date>=form.start_date.data, ApplicationsHolidays.date<=form.end_date.data).all()
                
                for date in dates:
                    date.holiday_id = holiday.id
                
                db.session.commit()
            else:
                current_app.logger.error("Holiday '%s' not found", form.name.data)
                msg = f'No holiday named {form.name.data}'
                flash(msg, category='error')

            return redirect(url_for('attendance.holidays', action='show'))

        return render_template('forms.html', type='add_holiday', form=form)
    elif action == 'delete':
        holiday_id = request.args.get('holiday_id')
        holiday = Holidays.query.filter_by(id=holiday_id).first()
        
        if not holiday:
            current_app.logger.error('Holiday id: %s not found in holidays table', holiday_id)
            flash('Holiday not found', category='error')
            return redirect(url_for('attendance.holidays', action='show'))

        rv = check_attnsummary(holiday.start_date, holiday.end_date)
        if rv:
            flash(rv, category='error')
            return redirect(url_for('attendance.holidays', action='show'))
        
        dates = ApplicationsHolidays.query.filter(ApplicationsHolidays.holiday_id==holiday_id).all()
        if dates:
            for date in dates:
                date.holiday_id = None
        else:
            current_app.logger.error('Holiday "%s" not found in applications_holidays table', holiday.name)
            flash('Holiday id not found', category='error')
            return redirect(url_for('attendance.holidays', action='show'))

        db.session.delete(holiday)
        
        db.session.commit()
    else:
        current_app.logger.error(' holidays(): unknown action %s', action)
        flash('Unknown action', category='error')
    
    return redirect(url_for('attendance.holidays', action='show'))


@attendance.route('/attendance/query/<query_for>', methods=['GET', 'POST'])
@login_required
def query(query_for):

    if query_for not in ('self', 'others'):
        current_app.logger.error(' query(): Unknown <query_for> "%s"', query_for)
        flash('Query failed', category='error')
        return render_template('base.html')
    
    if query_for == 'self':
        form = Monthyear()
    else:
        form = Attnqueryusername()

    if not form.validate_on_submit():
        return render_template('forms.html', type='attendance_query', query_for=query_for, form=form)
        
    if query_for == 'self':
        user_name = session['username']
    elif query_for == 'others':
        user_name = form.username.data

    employee = Employee.query.filter_by(username=user_name).first()
    if not employee:
        msg = f"Employee '{user_name}' not found"
        flash(msg, category='error')
        return redirect(url_for('forms.attendance_query', query_for=query_for))

    if query_for == 'others':
        has_access = check_data_access(employee.id)
        if not has_access:
            msg = f"You don't have access to '{employee.fullname}' attendance data"
            flash(msg, category='error')
            return redirect(url_for('forms.attendance_query', query_for=query_for))
    
    attendances = Attendance.query.filter(Attendance.empid==employee.id, extract('month', Attendance.date)==form.month.data, extract('year', Attendance.date)==form.year.data).order_by(Attendance.date).all()
    
    if not attendances:
        flash('No record found', category='warning')
        return redirect(url_for('forms.attendance_query', query_for=query_for))

    attendances_list = []
    summary = {'NI': 0, 'L': 0, 'NO': 0, 'E': 0}
    for attendance in attendances:
        attendance_list = {'date': attendance.date, 'in_time':attendance.in_time, 'out_time':attendance.out_time}
        
        attendance_list['day'] = datetime.strftime(attendance.date, "%A")

        in_time = datetime.strptime(current_app.config['IN_TIME'], "%H:%M:%S") + timedelta(minutes=current_app.config['GRACE_PERIOD'])
        out_time = datetime.strptime(current_app.config['OUT_TIME'], "%H:%M:%S") - timedelta(minutes=current_app.config['GRACE_PERIOD'])

        duty_schedule = DutySchedule.query.join(DutyShift).with_entities(DutyShift.name, DutyShift.in_time, DutyShift.out_time, DutySchedule.date).filter(DutySchedule.date==attendance.date, DutySchedule.empid==employee.id).first()
        if duty_schedule:
            attendance_list['duty_shift'] = duty_schedule.name

            if duty_schedule.name not in ('O', 'HO'):
                in_time = datetime.combine(duty_schedule.date, duty_schedule.in_time) + timedelta(minutes=current_app.config['GRACE_PERIOD'])
                out_time = datetime.combine(duty_schedule.date, duty_schedule.out_time) - timedelta(minutes=current_app.config['GRACE_PERIOD'])
        else:
            attendance_list['duty_shift'] = None

        application = Applications.query.filter(Applications.empid==employee.id, Applications.start_date<=attendance.date, Applications.end_date>=attendance.date).first()
        application_type = ''
        if  application:
            application_type = application.type
            attendance_list['application_type'] = application.type
            attendance_list['application_id'] = application.id
        else:
            attendance_list['application_type'] = None
            attendance_list['application_id'] = None

        holiday = Holidays.query.filter(Holidays.start_date<=attendance.date, Holidays.end_date>=attendance.date).first()
        holiday_name = ''
        if  holiday:
            holiday_name = holiday.name
            attendance_list['holiday'] = holiday.name
        else:
            attendance_list['holiday'] = None

        no_attendance = datetime.strptime('00:00:00', "%H:%M:%S").time()

        if application_type in ('Casual', 'Medical', 'Both') or attendance_list['duty_shift'] in ('O', 'HO') or holiday_name != '' or attendance_list['day'] in ('Friday', 'Saturday'):
            attendance_list['in_flag'] = None
            attendance_list['out_flag'] = None
        else:
            if application_type == 'In':
                attendance_list['in_flag'] = None
            elif attendance_list['in_time'] == no_attendance:
                attendance_list['in_flag'] = 'NI'
                summary['NI'] += 1
            elif attendance_list['in_time'] > in_time.time():
                attendance_list['in_flag'] = 'L'
                summary['L'] += 1
            else:
                attendance_list['in_flag'] = None

            if application_type == 'Out':
                attendance_list['out_flag'] = None
            elif attendance_list['out_time'] == no_attendance:
                attendance_list['out_flag'] = 'NO'
                summary['NO'] += 1
            elif attendance_list['out_time'] < out_time.time():
                attendance_list['out_flag'] = 'E'
                summary['E'] += 1
            else:
                attendance_list['out_flag'] = None

        attendances_list.append(attendance_list)  

    attendances = attendances_list
    
    return render_template('data.html', type='attendance_query', fullname=employee.fullname, form=form, attendances=attendances, summary=summary)
            

@attendance.route('/attendance/application/cancel/<application_for>,<application_id>')
@login_required
def cancel_application(application_for, application_id):
    application = Applications.query.filter_by(id=application_id).first()
    if not application:
        flash('Attendance application not found', category='error')
        return redirect(url_for('attendance.application_status', application_for=application_for))
    
    employee = Employee.query.join(Applications).filter(Applications.id==application_id).first()
    if not employee:
        current_app.logger.error(' cancel(): employee details not found for application:%s', application_id)
        flash('Employee details not found for this application', category='error')
        return redirect(url_for('attendance.application_status', application_for=application_for))
    
    can_edit = check_edit_permission(application, employee)
    if not can_edit:
        current_app.logger.error(' cancel(): User does not have permission to edit application, application_id: %s, username: %s, application_status: %s', application_id, employee.username, employee.applications[0].status)
        flash('You do not have permission to cancel this application', category='error')
        return redirect(url_for('attendance.application_status', application_for=application_for))
        
    if application.status == 'Approved':
        summary = AttendanceSummary.query.filter_by(year=application.start_date.year, month=application.start_date.strftime("%B"), empid=application.empid).first()
        
        if summary:
            msg = f'Attendance summary already prepared for {application.start_date.strftime("%B")},{application.start_date.year}' 
            flash(msg, category='error')
            return redirect(url_for('attendance.application_status', application_for=application_for))
        else:
            update_applications_holidays(employee.id, application.start_date, application.end_date)
    
    db.session.delete(application)
    db.session.commit()
    flash('Application cancelled', category='message')

    #Send mail to all concerned
    emails = get_concern_emails(employee.id)
    
    if application.status == 'Approval Pending':
        if session['username'] != employee.username:
            receiver_email = employee.email
        else:
            receiver_email = session['email']

        team_leader_email = find_team_leader_email(emails)
        if not team_leader_email:
            current_app.logger.error('Team leader email not found for application: %s', application_id)
            flash('Failed to send email', category='warning')
            return redirect(url_for('attendance.application_status', application_for=application_for))                

        rv = send_mail(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], sender=session['email'], receiver=receiver_email, cc1=team_leader_email, type='attendance', application=application, action='cancelled')
        
    if application.status == 'Approved':
        if session['role'] == 'Manager':
            cc2_email = ''
        else:
            cc2_email = emails['manager']

        if session['role'] == 'Head':
            cc3_email = ''
        else:
            cc3_email = emails['head']
        
        rv = send_mail(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], sender=session['email'], receiver=emails['admin_email'], cc1=emails['employee_email'], cc2=cc2_email, cc3=cc3_email, cc4=session['email'], type='attendance', application=application, action='cancelled')

    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')
    
    return redirect(url_for('attendance.application_status', application_for=application_for))


@attendance.route('/attendance/application/status/<application_for>')
@login_required
def application_status(application_for):

    if application_for not in ('self', 'team', 'all'):
        current_app.logger.error(' application_status(): Wrong application_for value "%s"', application_for)
        flash('Function not found', category='error')
        return render_template('base.html')
    
    if application_for == 'team' and session['role'] not in ('Supervisor', 'Manager', 'Head'):
        current_app.logger.error(' application_status(): session role "%s" does not have access to application_for="team"', session['role'])
        flash('You are not authorized to see team application status', category='error')
        return render_template('base.html')

    if application_for == 'all' and session['access'] != 'Admin':
        current_app.logger.error(' application_status(): session access "%s" does not have access to application_for="all"', session['access'])
        flash('You are not authorized to see all application status', category='error')
        return render_template('base.html')

    if application_for == 'self':
        applications = Applications.query.join(Employee).filter(Employee.username == session['username'], (and_(Applications.type!='Casual', Applications.type!='Medical'))).order_by(Applications.submission_date.desc()).all()
    
    if application_for == 'team':

        if session['role'] == 'Supervisor' or 'Manager': 
            teams = Team.query.join(Employee).filter(Employee.username==session['username']).all()
            
            all_teams_applications = []
            for team in teams:
                team_applications = Applications.query.select_from(Applications).join(Team, Applications.empid==Team.empid).filter(Team.name == team.name, Applications.empid!=session['empid'], and_(Applications.type!='Casual', Applications.type!='Medical')).order_by(Applications.status, Applications.submission_date.desc()).all()
            
                all_teams_applications += team_applications
            
            applications = all_teams_applications
        
        if session['role'] == 'Head':
            applications = Applications.query.join(Employee).filter(Employee.department==session['department'], and_(Applications.type!='Casual', Applications.type!='Medical')).order_by(Applications.status, Applications.submission_date.desc()).all()

    if application_for  == 'all':
        applications = Applications.query.filter(and_(Applications.type!='Casual', Applications.type!='Medical')).order_by(Applications.status).all()

    return render_template('data.html', type='attendance_application_status', application_for=application_for, applications=applications)


@attendance.route('/attendance/summary/<action>', methods=['GET', 'POST'])
@login_required
def summary(action):

    if action == 'show':
        summary_for = request.args.get('summary_for')
        
        if summary_for not in ('self', 'team', 'department', 'all'):
            current_app.logger.error(' summary(): Unknown summary_for %s', summary_for)
            flash('Failed to run this function', category='error')
        
        if summary_for != 'self':
            has_permission = check_view_permission(summary_for)
            if not has_permission:
                flash('You are not authorized to run this function', category='error')
                return redirect(url_for('forms.attendance_summary', action='show'))

    if action == 'prepare' and session['access'] != 'Admin':    
        flash('You are not authorized to run this function', category='error')
        return redirect(url_for('forms.attendance_summary', action='show'))

    if action == 'show':
        form = Attendancesummaryshow()
    elif action == 'prepare':
        form = Attendancesummaryprepare()
    else:
        current_app.logger.error(' summary(): function argument unknown %s', action)
        flash('Failed to execute function', category='error')
        return render_template('base.html')

    if form.validate_on_submit():

        if action == 'show':
            if summary_for == 'self':
                attendance_summary = AttendanceSummary.query.join(Employee).with_entities(Employee.fullname, AttendanceSummary.absent,AttendanceSummary.late, AttendanceSummary.early, AttendanceSummary.extra_absent, AttendanceSummary.leave_deducted).filter(Employee.id==session['empid'], AttendanceSummary.month==form.month.data, AttendanceSummary.year==form.year.data).all()
            
            if summary_for == 'team':
                if session['role'] in ('Supervisor', 'Manager'):
                    teams = Team.query.filter_by(empid=session['empid']).all()
                    
                    attendance_summary_list = []
                    for team in teams:
                        attendance_summary = AttendanceSummary.query.join(Employee).join(Team, AttendanceSummary.empid==Team.empid). with_entities(Employee.fullname, Team.name, AttendanceSummary.absent,AttendanceSummary.late, AttendanceSummary.early, AttendanceSummary.extra_absent, AttendanceSummary.leave_deducted).filter(Team.name==team.name, AttendanceSummary.month==form.month.data, AttendanceSummary.year==form.year.data).all()

                        attendance_summary_list.append(attendance_summary)
                    
                    attendance_summary = attendance_summary_list
                
            if summary_for == 'department':
                attendance_summary = AttendanceSummary.query.join(Employee).join(Team, AttendanceSummary.empid==Team.empid). with_entities(Employee.fullname, Team.name, AttendanceSummary.absent,AttendanceSummary.late, AttendanceSummary.early, AttendanceSummary.extra_absent, AttendanceSummary.leave_deducted).filter(Employee.department==session['department'], AttendanceSummary.month==form.month.data, AttendanceSummary.year==form.year.data).all()

            if summary_for == 'all':
                attendance_summary = AttendanceSummary.query.join(Employee).with_entities(Employee.fullname, AttendanceSummary.absent,AttendanceSummary.late, AttendanceSummary.early, AttendanceSummary.extra_absent, AttendanceSummary.leave_deducted).filter(AttendanceSummary.month==form.month.data, AttendanceSummary.year==form.year.data).all()

            if not attendance_summary:
                flash('No record found')

            return render_template('data.html', type='show_attendance_summary', form=form, attendance_summary=attendance_summary)

        if action == 'prepare':
            current_month = datetime.now().month
            current_year = datetime.now().year

            if form.month.data >= current_month and current_year >= form.year.data:
                flash('You can only prepare attendance summary of previous month or before previous month', category='error')    
                return redirect(url_for('forms.attendance_summary', action='prepare'))
                
            summary = AttendanceSummary.query.filter_by(year=form.year.data, month=form.month.data).first()
            if summary:
                flash('Summary data already exists for the year and month you submitted', category='error')
                return redirect(url_for('forms.attendance_summary', action='prepare'))
        
            employees = Employee.query.all()

            count = 0
            for employee in employees:
                attendances = Attendance.query.with_entities(Attendance.date, Attendance.in_time, Attendance.out_time, ApplicationsHolidays.application_id, ApplicationsHolidays.holiday_id, ApplicationsHolidays.weekend_id).join(ApplicationsHolidays, and_(Attendance.empid==ApplicationsHolidays.empid, Attendance.date==ApplicationsHolidays.date)).filter(Attendance.empid==employee.id, extract('month', Attendance.date)==form.month.data, extract('year', Attendance.date)==form.year.data).all()
                
                absent_count = 0
                late_count = 0
                early_count = 0
                
                for attendance in attendances:
                    if attendance.holiday_id:
                        continue
                    
                    if attendance.weekend_id:
                        continue

                    if attendance.application_id:
                        application = Applications.query.filter_by(id=attendance.application_id).first()
                        if application.type in ('Casual', 'Medical', 'Both'):
                            continue
                        else:
                            application_type = application.type
                    else:
                        application_type = ''

                    duty_schedule = DutySchedule.query.join(DutyShift).filter(DutySchedule.empid==employee.id, DutySchedule.date==attendance.date).first()
                    
                    if duty_schedule:
                        standard_in_time = duty_schedule.dutyshift.in_time
                        standard_out_time = duty_schedule.dutyshift.out_time
                    else:
                        standard_in_time = datetime.strptime(current_app.config['LATE'], '%H:%M:%S').time()
                        standard_out_time = datetime.strptime(current_app.config['EARLY'], '%H:%M:%S').time()

                    no_attendance = datetime.strptime('00:00:00', '%H:%M:%S').time()
                    if attendance.in_time == no_attendance:
                        if application_type not in ('In', 'Both'):
                            absent_count += 1
                            continue

                    if attendance.in_time > standard_in_time: 
                        if application_type not in ('In', 'Both'):
                            late_count += 1

                    if attendance.out_time < standard_out_time or attendance.out_time == no_attendance:
                        if application_type not in ('Out', 'Both'):
                            early_count += 1

                if absent_count > 0 or late_count > 0 or early_count > 0:
                    attnsummary = AttendanceSummary(empid=employee.id, year=form.year.data, month=form.month.data, absent=absent_count, late=late_count, early=early_count)
                    db.session.add(attnsummary)
                    count += 1
                
            if count == 0:
                flash('No late or absent in attendance data', category='warning')
            else:
                db.session.commit()
                flash('Attendance summary created', category='message')
    
    else:
        flash('Form data not correct', category='error')
    
    return redirect(url_for('forms.attendance_summary', action='prepare'))
