from calendar import monthrange
from datetime import datetime
import os
from flask import Blueprint, current_app, request, flash, redirect, render_template, send_from_directory, session, url_for
from sqlalchemy import extract, select
import pandas as pd
from .forms import (Addholidays, Attnqueryfullname, Attndataupload, Dutyshiftcreate, Attendancesummaryshow, Monthyear, Dutyscheduleupload, Officetime, Deleteattendance, Dutyscheduledelete)
from .db import *
from .auth import login_required, admin_required, team_leader_required
from .functions import check_holidays, get_attendance_data, check_view_permission, convert_team_name, check_data_access, check_attendance_summary, check_office_time_dates, find_holiday_leaves

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
                if pd.isna(df.iat[i, 0]):
                    msg = f'Employee id not found on row {i + 2}'
                    flash(msg, category='error')
                    return render_template('forms.html', form_type='attendance_upload', form=form)
                    
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


@attendance.route('/attendance/duty_schedule/<action>', methods=['GET', 'POST'])
@login_required
def duty_schedule(action):
    if action not in ('query', 'upload', 'delete'):
        current_app.logger.error(' duty_schedule() - action unknown')
        flash('Unknown action', category='error')
        return render_template('base.html')
    
    if session['role'] == 'Team' and session['access'] != 'Admin':
        flash('You are not authorized to access this function', category='error')
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
            employees = Employee.query.join(Team).order_by(Team.name).all()
        elif session['role'] in ('Supervisor', 'Manager'):
            team_leader = Employee.query.filter_by(id=session['empid']).first()
            employees = []
            for team in team_leader.teams:
                team_employees = Employee.query.join(Team).filter(Team.name==team.name).all()
                employees.extend(team_employees)
        else:
            flash('You are not authorized to access this function', category='error')
            return redirect(url_for('forms.duty_schedule', action='query'))

        schedules = []
        for employee in employees:
            team = Team.query.filter_by(empid=employee.id).first()
            dates = DutySchedule.query.join(DutyShift).with_entities(DutyShift.name.label('shift')).filter(DutySchedule.empid==employee.id, extract('month', DutySchedule.date)==month, extract('year', DutySchedule.date)==year).order_by(DutySchedule.date).all()
           
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
            return redirect(url_for('forms.duty_schedule', action='upload'))
        
        if session['role'] in ('Supervisor', 'Manager'):
            team_leader = Employee.query.join(Team).filter(Employee.id==session['empid']).first()
            if not team_leader:
                current_app.logger.error(" duty_schedule(action='upload'): Employee details not found for %s", session['username'])
                msg = f"Employee details not found for '{session['username']}'"
                flash(msg, category='error')
                return redirect(url_for('forms.duty_schedule', action='upload'))

            team_leader_teams = []
            for team in team_leader.teams:
                team_leader_teams.append(team.name)

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
                msg = f'Employee not found with name: {fullname} on row {i+1}'
                flash(msg, category='error')
                return redirect(url_for('forms.duty_schedule', action='upload'))
            
            if session['role'] in ('Supervisor', 'Manager'):
                if employee.teams[0].name not in team_leader_teams:
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

                duty_schedule = DutySchedule.query.filter_by(empid=employee.id, date=date, team=employee.teams[0].name).first()
                if duty_schedule:
                    msg = f'Duty schedule exist for {fullname} on date {date}'
                    flash(msg, category='error')
                    return redirect(url_for('forms.duty_schedule', action='upload'))
                
                if pd.isna(df.iat[i, j]):
                    msg = f'Duty shift missing for {fullname} on date {j}'
                    flash(msg, category='error')
                    return redirect(url_for('forms.duty_schedule', action='upload'))

                duty_shift = DutyShift.query.filter(DutyShift.name==str(df.iat[i, j]).upper(), DutyShift.team==employee.teams[0].name, DutyShift.start_date<=date, DutyShift.end_date>=date).first()
                if not duty_shift:
                    duty_shift = DutyShift.query.filter(DutyShift.name==str(df.iat[i, j]).upper(), DutyShift.team==employee.teams[0].name, DutyShift.start_date==None, DutyShift.end_date==None).first()
                    if not duty_shift:
                        msg = f'Duty shift "{df.iat[i, j]}" for team "{employee.teams[0].name}" for date "{date}" not found'
                        flash(msg, category='error')
                        return redirect(url_for('forms.duty_schedule', action='upload'))
                
                duty_schedule = DutySchedule(empid=employee.id, team=employee.teams[0].name, date=date, duty_shift=duty_shift.id)
                db.session.add(duty_schedule)

        db.session.commit()
        flash('Duty schedule uploaded')
        return redirect(url_for('attendance.duty_schedule', action='query'))
    
    if action == 'delete':
        form = Dutyscheduledelete()

        if not form.validate_on_submit():
            return render_template('forms.html', type='duty_schedule', action='delete', form=form)

        attnsummary_prepared = AttendanceSummary.query.filter_by(month=form.month.data, year=form.year.data).all()
        if attnsummary_prepared:
            msg = f'Cannot delete duty schedule. Attendance summary already prepared for {form.month.data}, {form.year.data}'
            flash(msg, category='error')
            return redirect(url_for('forms.duty_schedule', action='delete'))

        team_leader = Team.query.filter_by(empid=session['empid'], name=form.teams.data).first()
        if not team_leader:
            msg = f'You are not the team leader of "{form.teams.data}"'
            flash(msg, category='error')
            return redirect(url_for('forms.duty_schedule', action='delete'))

        duty_schedules = DutySchedule.query.filter(extract('month', DutySchedule.date)==form.month.data, extract('year', DutySchedule.date)==form.year.data, DutySchedule.team==form.teams.data).all()
        if not duty_schedules:
            msg = f'Schedule does not exist for Month:{form.month.data}, Year:{form.year.data} and Team:{form.teams.data}'
            flash(msg, category='error')
            return redirect(url_for('forms.duty_schedule', action='delete'))
        
        for duty_schedule in duty_schedules:
            db.session.delete(duty_schedule)
 
        db.session.commit()
        
        flash('Duty schedule deleted', category='message')
        return redirect(url_for('attendance.duty_schedule', action='query'))


@attendance.route('/attendance/duty_shift/<action>', methods=['GET', 'POST'])
@login_required
def duty_shift(action):
    if action not in ('query', 'create', 'delete'):
        current_app.logger.error(' duty_shift() - action unknown')
        flash('Unknown action', category='error')
        return render_template('base.html')

    employee = Employee.query.filter_by(id=session['empid']).first()

    if action == 'query':
        if session['role'] == 'Head' or session['access'] == 'Admin':
            shifts = DutyShift.query.all()
        elif session['role'] in ('Supervisor', 'Manager'):
            shifts = []
            for team in employee.teams:
                team_shifts = DutyShift.query.filter(DutyShift.team==team.name).all()
                shifts.extend(team_shifts)
        else:
            flash('You are not authorized to access this function', category='error')
            return render_template('base.html')

        return render_template('data.html', type='duty_shift', shifts=shifts)
    
    if action == 'create':
        if session['role'] not in ('Supervisor', 'Manager', 'Head'):
            flash('You are not authorized to access this function', category='error')
            return render_template('base.html')
        
        form = Dutyshiftcreate()
        if not form.validate_on_submit():
            return render_template('forms.html', type='duty_shift_create', form=form)

        if form.start_date.data and not form.end_date.data:
            form.end_date.data = form.start_date.data

        if not form.start_date.data:
            shift_exists = DutyShift.query.filter_by(team=form.team.data, name=form.shift_name.data, start_date=None, end_date=None).first()
            if shift_exists:
                flash('Shift exists', category='error')
                return redirect(url_for('forms.duty_shift_create', form=form))
        else:
            start_date_exists = DutyShift.query.filter(DutyShift.team==form.team.data, DutyShift.name==form.shift_name.data, DutyShift.start_date<=form.start_date.data, DutyShift.end_date>=form.start_date.data).first()
            if start_date_exists:
                flash('Start date exists', category='error')
                return redirect(url_for('forms.duty_shift_create', form=form))

            end_date_exists = DutyShift.query.filter(DutyShift.team==form.team.data, DutyShift.name==form.shift_name.data, DutyShift.start_date<=form.end_date.data, DutyShift.end_date>=form.end_date.data).first()
            if end_date_exists:
                flash('End date exists', category='error')
                return redirect(url_for('forms.duty_shift_create', form=form))

            any_date_exists = DutyShift.query.filter(DutyShift.team==form.team.data, DutyShift.name==form.shift_name.data, DutyShift.start_date>=form.start_date.data, DutyShift.end_date<=form.end_date.data).first()

            if any_date_exists:
                flash('Start date and end date overlaps with other shifts', category='error')
                return redirect(url_for('forms.duty_shift_create', form=form))

        duty_shift = DutyShift(team=form.team.data, name=form.shift_name.data, in_time=form.in_time.data, out_time=form.out_time.data, start_date=form.start_date.data, end_date=form.end_date.data)
        
        db.session.add(duty_shift)
        db.session.commit()

        flash('Duty shift created', category='message')
        return redirect(url_for('attendance.duty_shift', action='query'))

    if action == 'delete':
        if session['role'] not in ('Supervisor', 'Manager', 'Head'):
            flash('You are not authorized to access this function', category='error')
            return render_template('base.html')

        shift_id = request.args.get('shift_id')
        
        shift = DutyShift.query.filter_by(id=shift_id).first()
        if not shift:
            flash('Shift not found', category='error')
            current_app.logger.warning('duty_shift(action="delete"): Shift id not found')
            return redirect(url_for('attendance.duty_shift', action='query'))
        
        shift_exist = DutySchedule.query.filter_by(duty_shift=shift.id).all()
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
            
            rv = check_attendance_summary(form.start_date.data, form.end_date.data)
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

        rv = check_attendance_summary(holiday.start_date, holiday.end_date)
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
        form = Attnqueryfullname()

    if not form.validate_on_submit():
        return render_template('forms.html', type='attendance_query', query_for=query_for, form=form)
        
    if query_for == 'self':
        fullname = session['fullname']
    elif query_for == 'others':
        fullname = form.fullname.data

    fullname_string = f'%{fullname}%'
    employee = Employee.query.filter(Employee.fullname.like(fullname_string)).first()
    if not employee:
        msg = f"Employee '{fullname}' not found"
        flash(msg, category='error')
        return redirect(url_for('forms.attendance_query', query_for=query_for))

    if query_for == 'others':
        has_access = check_data_access(employee.id)
        if not has_access:
            msg = f"You don't have access to '{employee.fullname}' attendance data"
            flash(msg, category='error')
            return redirect(url_for('forms.attendance_query', query_for=query_for))

    attendances = get_attendance_data(employee.id, form.month.data, form.year.data)

    return render_template('data.html', type='attendance_query', fullname=employee.fullname, form=form, attendances=attendances)
            

@attendance.route('/attendance/summary/<action>', methods=['GET', 'POST'])
@login_required
def summary(action):
    if action not in ('show', 'prepare', 'delete'):
        current_app.logger.error(' summary(): Unknown <action> %s', action)
        flash('Failed to perform this action', category='error')
        return redirect(url_for('forms.attendance_summary', action='show'))

    if action == 'show':
        summary_for = request.args.get('summary_for')
        
        if summary_for not in ('self', 'team', 'department', 'all'):
            current_app.logger.error(' summary(): Unknown summary_for %s', summary_for)
            flash('Failed to run this function', category='error')
            return redirect(url_for('forms.attendance_summary', action='show'))

        
        if summary_for != 'self':
            has_permission = check_view_permission(summary_for)
            if not has_permission:
                flash('You are not authorized to run this function', category='error')
                return redirect(url_for('forms.attendance_summary', action='show'))

    if action in ('prepare', 'delete') and session['access'] != 'Admin':    
        flash('You are not authorized to run this function', category='error')
        return redirect(url_for('forms.attendance_summary', action='show'))

    if action == 'show':
        form = Attendancesummaryshow()
    elif action in ('prepare', 'delete'):
        form = Monthyear()

    if not form.validate_on_submit():
        if action == 'show':
            return render_template('forms.html', type='show_attendance_summary', summary_for=summary_for, form=form)
        
        if action in ('prepare', 'delete'):
            return render_template('forms.html', type='attendance_summary', action=action, form=form)

    if action == 'show':
        file_name = ''

        if summary_for == 'self':
            attendance_summary = AttendanceSummary.query.join(Employee).join(LeaveDeductionSummary, AttendanceSummary.id==LeaveDeductionSummary.attendance_summary, isouter=True).with_entities(Employee.fullname, AttendanceSummary.absent,AttendanceSummary.late, AttendanceSummary.early, AttendanceSummary.holiday_leave, LeaveDeductionSummary.leave_deducted, LeaveDeductionSummary.salary_deducted).filter(Employee.id==session['empid'], AttendanceSummary.month==form.month.data, AttendanceSummary.year==form.year.data).all()
        
        if summary_for == 'team':
            teams = Team.query.filter_by(empid=session['empid']).all()
            attendance_summary_list = []
            
            for team in teams:
                team_attendance_summary = AttendanceSummary.query.join(Employee).join(LeaveDeductionSummary, AttendanceSummary.id==LeaveDeductionSummary.attendance_summary, isouter=True).join(Team, AttendanceSummary.empid==Team.empid, isouter=True).with_entities(Employee.fullname, Team.name.label('team'), AttendanceSummary.absent,AttendanceSummary.late, AttendanceSummary.early, AttendanceSummary.holiday_leave, LeaveDeductionSummary.leave_deducted, LeaveDeductionSummary.salary_deducted).filter(Team.name==team.name, AttendanceSummary.month==form.month.data, AttendanceSummary.year==form.year.data).order_by(Employee.fullname).all()

                for attendance_summary in team_attendance_summary:
                    attendance_summary_list.append(attendance_summary)
            
            attendance_summary = attendance_summary_list

        if summary_for == 'department':
            attendance_summary = AttendanceSummary.query.join(LeaveDeductionSummary, AttendanceSummary.id==LeaveDeductionSummary.attendance_summary, isouter=True).join(Employee, Team, isouter=True).with_entities(Employee.fullname, Team.name.label('team'), AttendanceSummary.absent,AttendanceSummary.late, AttendanceSummary.early, AttendanceSummary.holiday_leave, LeaveDeductionSummary.leave_deducted, LeaveDeductionSummary.salary_deducted).filter(Employee.department==session['department'], AttendanceSummary.month==form.month.data, AttendanceSummary.year==form.year.data).order_by(Team.name, Employee.fullname).all()

        if summary_for == 'all':
            stmt = select(Employee.fullname, AttendanceSummary.absent, AttendanceSummary.late, AttendanceSummary.early, AttendanceSummary.holiday_leave, LeaveDeductionSummary.leave_deducted, LeaveDeductionSummary.salary_deducted).select_from(AttendanceSummary).join(Employee).join(LeaveDeductionSummary, AttendanceSummary.id==LeaveDeductionSummary.attendance_summary, isouter=True).where(AttendanceSummary.month==form.month.data, AttendanceSummary.year==form.year.data)
            
            attendance_summary = db.session.execute(stmt).all()

            if form.download.data:
                df = pd.read_sql(stmt, db.session.bind)
                file_name = f'attendance-summary-{form.month.data}-{form.year.data}.csv'
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file_name)
                df.to_csv(file_path, index=False)

        return render_template('data.html', type='show_attendance_summary', form=form, attendance_summary=attendance_summary, file=file_name)

    if action == 'prepare':
        current_month = datetime.now().month
        current_year = datetime.now().year

        if form.month.data >= current_month and form.year.data >= current_year:
            flash('You can only prepare attendance summary of previous month or before previous month', category='error')    
            return redirect(url_for('forms.attendance_summary', action='prepare'))
            
        summary = AttendanceSummary.query.filter_by(year=form.year.data, month=form.month.data).first()
        if summary:
            flash('Summary data already exists for the year and month you submitted', category='error')
            return redirect(url_for('forms.attendance_summary', action='prepare'))

        employees = Employee.query.all()

        count = 0
        for employee in employees:
            attendance = get_attendance_data(employee.id, form.month.data, form.year.data)
            if attendance:
                holiday_leave = find_holiday_leaves(employee.id, attendance['attendances'])
                absent = attendance['summary']['NO'] + attendance['summary']['NI']

                attendance_summary = AttendanceSummary(empid=employee.id, year=form.year.data, month=form.month.data, absent=absent, late=attendance['summary']['L'], early=attendance['summary']['E'], holiday_leave=holiday_leave)
                db.session.add(attendance_summary)
                count += 1
    
        if count > 0:
            db.session.commit()
            msg = f'Attendance summary prepared for {form.month.data}, {form.year.data}. Added record {count}'
        else:
            msg = f'No record found for {form.month.data}, {form.year.data}'
        
        flash(msg)
        return redirect(url_for('forms.attendance_summary', action='prepare'))
    
    if action == 'delete':
        summary_all = AttendanceSummary.query.filter_by(year=form.year.data, month=form.month.data).all()
        if not summary_all:
            msg = f'Attendance summary not found for {form.month.data}, {form.year.data}'
            flash(msg, category='error')
            return redirect(url_for('forms.attendance_summary', action='delete', form=form))

        leave_deducted = LeaveDeductionSummary.query.filter_by(month=form.month.data, year=form.year.data).all()
        if leave_deducted:
            msg = f'You must reverse leave deduction of {form.month.data}, {form.year.data} before deleting attendance summary'
            flash(msg, category='error')
            return redirect(url_for('forms.attendance_summary', action='delete', form=form))

        for summary in summary_all:
            db.session.delete(summary)

        db.session.commit()
        msg = f'Attendance summary deleted for {form.month.data}, {form.year.data}'
        flash(msg)
        return redirect(url_for('forms.attendance_summary', action='delete'))
                

@attendance.route('/attendance/office_time/<action>', methods=['GET', 'POST'])
@login_required
@admin_required
def office_time(action):
    if action not in ('add', 'delete', 'search'):
        current_app.logger.error(' office_time(): unknown <action>, user: %s', session['username'])
        flash('Unknow <action> type', category='error')
        return render_template('base.html')
    
    if action == 'search':
        office_times = OfficeTime.query.all()
        return render_template('data.html', type='office_time', office_times=office_times)

    if action == 'add':
        form = Officetime()
        
        if not form.validate_on_submit():
            return render_template('forms.html', type='add_office_time', form=form)

        date_exists = check_office_time_dates(form)
        if date_exists:
            flash(date_exists, category='error')
            return render_template('base.html')
        
        office_time = OfficeTime(start_date=form.start_date.data, end_date=form.end_date.data, in_time=form.in_time.data, out_time=form.out_time.data, in_grace_time=form.in_grace_time.data, out_grace_time=form.out_grace_time.data)

        db.session.add(office_time)
        db.session.commit()
        return redirect(url_for('attendance.office_time', action='search'))

    if action == 'delete':
        office_time_id = request.args.get('office_time_id')
        if not office_time_id:
            flash('Office time id not found', category='error')
            return redirect(url_for('attendance.office_time', action='search'))

        office_time = OfficeTime.query.filter_by(id=office_time_id).first()
        if not office_time:
            flash('No office time record found', category='error')
            return redirect(url_for('attendance.office_time', action='search'))
        
        db.session.delete(office_time)
        db.session.commit()
        return redirect(url_for('attendance.office_time', action='search'))
    


@attendance.route('/attendance/delete', methods=['GET', 'POST'])
@login_required
@admin_required
def delete_attendance():
    form = Deleteattendance()

    if not form.validate_on_submit():
        return render_template('forms.html', type='delete_attendance', form=form)
    
    if not form.end_date.data:
        form.end_date.data = form.start_date.data
    
    attendances = Attendance.query.filter(Attendance.date>=form.start_date.data, Attendance.date<=form.end_date.data).all()
    if not attendances:
        msg = f'No attendance found from {form.start_date.data} to {form.end_date.data}'
        flash(msg, category='error')
        return redirect(url_for('forms.delete_attendance'))
    
    for attendance in attendances:
        db.session.delete(attendance)

    db.session.commit()
    msg = f'Attendnace deleted from {form.start_date.data} to {form.end_date.data}'    
    flash(msg)
    return redirect(url_for('forms.delete_attendance'))