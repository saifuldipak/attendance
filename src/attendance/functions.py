from datetime import datetime, timedelta, date
import re
from flask import session, current_app
from sqlalchemy import extract, func, or_
import os
from werkzeug.utils import secure_filename
from email.message import EmailMessage
from smtplib import SMTP, SMTPException
import socket
from math import ceil
from typing import Tuple, Optional
from attendance.db import db, Employee, ApplicationsHolidays, Holidays, Applications, Team, Attendance, DutySchedule, DutyShift, AttendanceSummary, LeaveAvailable, OfficeTime, LeaveDeductionSummary, LeaveAllocation
from attendance.schemas import AnnualLeave
from attendance.schemas import EmployeeFiscalYear
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, NoResultFound

#Check holiday in holidays table
def check_holidays(name, start_date, end_date=None):
    holiday_name_exists = Holidays.query.filter_by(name=name).all()
    if holiday_name_exists:
        return 'Holiday name exists'
        
    holiday_start_date_exists = Holidays.query.filter(Holidays.start_date<=start_date, Holidays.end_date>=start_date).first()
    if holiday_start_date_exists:
        return 'Holiday start date overlaps with another holiday'
    
    if end_date:
        if start_date != end_date:
            holiday_end_date_exists = Holidays.query.filter(Holidays.start_date<=end_date, Holidays.end_date>=end_date).first()
            if holiday_end_date_exists:
                return 'Holiday end date overlaps with another holiday'

            any_date_exists = Holidays.query.filter(Holidays.start_date>start_date, Holidays.end_date<end_date).first()
            if any_date_exists:
                return 'Holiday start and/or end dates overlaps with other holidays'

def update_applications_holidays(empid, start_date, end_date, application_id=None):
    while start_date <= end_date:
        attendance = ApplicationsHolidays.query.filter(ApplicationsHolidays.date==start_date, ApplicationsHolidays.empid==empid).first()
        
        if attendance:
            attendance.application_id = application_id
        
        start_date += timedelta(days=1)

#check whether session user is the team leader of the employee of the supplied application_id 
def check_team_access(application_id):
    employee = Employee.query.join(Applications, Team).filter(Applications.id==application_id).first()
    
    supervisor = Employee.query.join(Team).filter(Employee.username==session['username'], Team.name==employee.teams[0].name, Employee.role=='Supervisor').first()
    if supervisor:
        return True

    manager = Employee.query.join(Team).filter(Employee.username==session['username'], Team.name==employee.teams[0].name, Employee.role=='Manager').first()
    if manager:
        return True

    head = Employee.query.filter_by(username=session['username'], department=employee.department, role='Head').first()
    if head:
        return True

    return False

def check_edit_permission(application, employee):
    team = Team.query.filter_by(empid=employee.id).first()
    supervisor = Employee.query.join(Team).filter(Employee.username==session['username'], Team.name==team.name, Employee.role=='Supervisor').first()
    manager = Employee.query.join(Team).filter(Employee.username==session['username'], Team.name==team.name, Employee.role=='Manager').first()
    head = Employee.query.filter_by(username=session['username'], department=employee.department, role='Head').first()
    
    if application.status == 'Approval Pending':
        if session['username'] == employee.username:
            return True
    
    if employee.role == 'Team':
        if session['role'] == 'Supervisor' and supervisor:
            return True
        elif session['role'] == 'Manager' and manager:
            return True
        elif session['role'] == 'Head' and head:
            return True
    
    if employee.role == 'Supervisor':
        if session['role'] == 'Manager' and manager:
            return True
        elif session['role'] == 'Head' and head:
            return True

    if employee.role == 'Manager':
        if session['role'] == 'Head' and head:
            return True

    return False

def check_edit_permission2(action, application, employee):
    team = Team.query.filter_by(empid=employee.id).first()
    supervisor = Employee.query.join(Team).filter(Employee.username==session['username'], Team.name==team.name, Employee.role=='Supervisor').first()
    manager = Employee.query.join(Team).filter(Employee.username==session['username'], Team.name==team.name, Employee.role=='Manager').first()
    head = Employee.query.filter_by(username=session['username'], department=employee.department, role='Head').first()
    
    if session['username'] == employee.username:
        if action == 'cancel' and application.status == 'Approval Pending': 
            return True
    
    if employee.role == 'Team':
        if session['role'] == 'Supervisor' and supervisor:
            return True
        elif session['role'] == 'Manager' and manager:
            return True
        elif session['role'] == 'Head' and head:
            return True
    
    if employee.role == 'Supervisor':
        if session['role'] == 'Manager' and manager:
            return True
        elif session['role'] == 'Head' and head:
            return True

    if employee.role == 'Manager':
        if session['role'] == 'Head' and head:
            return True

    return False

def check_view_permission(show_type):
    if show_type == 'all' and session['access'] == 'Admin':
        return True
    
    if show_type == 'team' and session['role'] in ('Supervisor', 'Manager'):
        return True

    if show_type == 'department' and session['role'] == 'Head':
        return True
    
    return False

#Convert all team names of Fiber & Support to generic name
def convert_team_name(team_name):    
    match = re.search('^Fiber', team_name)
    if match:
        team_name = 'Fiber'

    match = re.search('^Support', team_name)
    if match:
        team_name = 'Support'
    
    return team_name

#check whether session user is the team leader or department head of the employee
def check_data_access(employee_id):
    employee = Employee.query.join(Team).filter(Employee.id==employee_id).first()
    
    supervisor = Employee.query.join(Team).filter(Employee.id==session['empid'], Team.name==employee.teams[0].name, Employee.role=='Supervisor').first()
    if supervisor:
        return True

    manager = Employee.query.join(Team).filter(Employee.id==session['empid'], Team.name==employee.teams[0].name, Employee.role=='Manager').first()
    if manager:
        return True

    head = Employee.query.filter_by(id=session['empid'], department=employee.department, role='Head').first()
    if head:
        return True
    
    admin = Employee.query.filter_by(id=session['empid'], access='Admin').first()
    if admin:
        return True

    return False


def get_attendance_data(empid, month, year):
    if not empid:
        current_app.logger.error(' get_attendance_date(): empid not given')
        return False

    if not month:
        current_app.logger.error(' get_attendance_date(): month not given')
        return False

    if not year:
        current_app.logger.error(' get_attendance_date(): year not given')
        return False

    employee = Employee.query.filter_by(id=empid).first()
    if not employee:
        current_app.logger.warning(' get_attendance_date(): employee not found for %s', empid)
        return False

    if not employee.teams:
        current_app.logger.warning(' get_attendance_date(): employee team not found for %s', employee.username)
        return False

    fiber_team = re.search('^Fiber', employee.teams[0].name)

    attendances = Attendance.query.filter(Attendance.empid==empid, extract('month', Attendance.date)==month, extract('year', Attendance.date)==year).order_by(Attendance.date).all()
    if not attendances:
        return False
    
    return_values = {}
    attendances_list = []
    summary = {'NI': 0, 'L': 0, 'NO': 0, 'E': 0}
    
    for attendance in attendances:
        in_time = datetime.combine(attendance.date, attendance.in_time)
        out_time = datetime.combine(attendance.date, attendance.out_time)

        attendance_list = {'date': attendance.date, 'in_time' : in_time, 'out_time' : out_time} 
        attendance_list['day'] = datetime.strftime(attendance.date, "%A")

        office_time = OfficeTime.query.filter(OfficeTime.start_date<=attendance.date, OfficeTime.end_date>=attendance.date).first()
        if office_time:
            if not office_time.in_grace_time:
                in_grace_time = 0
            else:
                in_grace_time = office_time.in_grace_time
            
            if not office_time.out_grace_time:
                out_grace_time = 0
            else:
                out_grace_time = office_time.out_grace_time

            in_time = datetime.combine(attendance.date, office_time.in_time) + timedelta(minutes=in_grace_time)
            out_time = datetime.combine(attendance.date, office_time.out_time) - timedelta(minutes=out_grace_time)
        else:
            in_grace_time = current_app.config['IN_GRACE_TIME']
            out_grace_time = current_app.config['OUT_GRACE_TIME']

            in_time = datetime.strptime(current_app.config['IN_TIME'], "%H:%M:%S") + timedelta(minutes=in_grace_time)
            out_time = datetime.strptime(current_app.config['OUT_TIME'], "%H:%M:%S") - timedelta(minutes=out_grace_time)

        duty_schedule = DutySchedule.query.join(DutyShift).with_entities(DutyShift.name, DutyShift.in_time, DutyShift.out_time, DutySchedule.date).filter(DutySchedule.date==attendance.date, DutySchedule.empid==empid).first()
        attendance_list['duty_shift'] = None
        if duty_schedule:
            attendance_list['duty_shift'] = duty_schedule.name

            if duty_schedule.name not in ('O', 'HO'):
                in_time = datetime.combine(duty_schedule.date, duty_schedule.in_time) + timedelta(minutes=in_grace_time)
                
                if duty_schedule.name == 'N':
                    duty_schedule_date = duty_schedule.date + timedelta(days=1)
                    out_time = datetime.combine(duty_schedule_date, duty_schedule.out_time) - timedelta(minutes=out_grace_time)
                else:
                    out_time = datetime.combine(duty_schedule.date, duty_schedule.out_time) - timedelta(minutes=out_grace_time)

        application = Applications.query.filter(Applications.empid==empid, Applications.start_date<=attendance.date, Applications.end_date>=attendance.date).first()
        application_type = ''
        if  application:
            if application.status.lower() == 'approved': 
                application_type = application.type
                attendance_list['application_type'] = application.type
                attendance_list['application_id'] = application.id
            else:
                attendance_list['application_type'] = None
                attendance_list['application_id'] = None
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

        no_time = datetime.strptime('00:00:00', "%H:%M:%S").time()
        no_attendance = datetime.combine(attendance.date, no_time)

        if application_type in ('Casual', 'Medical', 'Both', 'Casual adjust') and application.status.lower() == 'approved':
            attendance_list['in_flag'] = None
            attendance_list['out_flag'] = None
        elif attendance_list['duty_shift'] in ('O', 'HO'):
            attendance_list['in_flag'] = None
            attendance_list['out_flag'] = None
        elif holiday_name != '' and not attendance_list['duty_shift']: 
            attendance_list['in_flag'] = None
            attendance_list['out_flag'] = None
        elif attendance_list['day'] == 'Friday' and not attendance_list['duty_shift']:
            attendance_list['in_flag'] = None
            attendance_list['out_flag'] = None
        elif attendance_list['day'] == 'Saturday' and not attendance_list['duty_shift'] and not fiber_team:
            attendance_list['in_flag'] = None
            attendance_list['out_flag'] = None
        else:
            if application_type == 'In' and application.status.lower() == 'approved':
                attendance_list['in_flag'] = None
            elif attendance_list['in_time'] == no_attendance:
                attendance_list['in_flag'] = 'NI'
                summary['NI'] += 1
            elif attendance_list['in_time'] > in_time:
                attendance_list['in_flag'] = 'L'
                summary['L'] += 1
            else:
                attendance_list['in_flag'] = None

            if attendance_list['duty_shift'] == 'N':
                next_date = attendance.date + timedelta(days=1)
                attendance = Attendance.query.filter_by(empid=empid, date=next_date).first()
                if not attendance:
                    attendance_list['out_time'] = no_attendance
                else:
                    attendance_list['out_time'] = datetime.combine(attendance.date, attendance.out_time)

            if application_type == 'Out' and application.status.lower() == 'approved':
                attendance_list['out_flag'] = None
            elif attendance_list['out_time'] == no_attendance:
                #to avoid counting no out('NO') if the person is absent
                if attendance_list['in_flag'] != 'NI':
                    attendance_list['out_flag'] = 'NO'
                    summary['NO'] += 1
            elif attendance_list['out_time'] < out_time:
                attendance_list['out_flag'] = 'E'
                summary['E'] += 1
            else:
                attendance_list['out_flag'] = None

        attendance_list['in_time'] = attendance_list['in_time'].time()
        attendance_list['out_time'] = attendance_list['out_time'].time()
        attendances_list.append(attendance_list)  

    attendances = attendances_list
    return_values['attendances'] = attendances
    return_values['summary'] = summary

    return return_values


def get_fiscal_year_start_end():
    current_year = date.today().year
    current_month = date.today().month
    
    if current_month <= 6:
        year_start = date((current_year - 1), 7, 1)
        year_end = date(current_year, 6, 30)
    else:
        year_start = date(current_year, 7, 1)
        year_end = date((current_year + 1), 6, 30)
    
    return year_start, year_end


def check_attendance_summary(start_date, end_date=None):
    start_date_in_summary = AttendanceSummary.query.filter(AttendanceSummary.year==start_date.year, AttendanceSummary.month==start_date.month).first()
    
    found = False
    if start_date_in_summary:
        month = start_date.strftime("%B")
        year = start_date.year
        found = True
        
    if end_date:
        end_date_in_summary = AttendanceSummary.query.filter(AttendanceSummary.year==end_date.year, AttendanceSummary.month==end_date.month).first()
        if end_date_in_summary:
            month = end_date.strftime("%B")
            year = end_date.year
            found = True
    
    if found:
        msg = f'Attendance summary already prepared for {month}, {year}'
        return msg
    
    return False


def check_available_leave(application, update=None):
    success_message = 'Leave available'
    failed_messaage = 'Leave not available'
    error_message = 'Leave record not found'

    if not application:
        current_app.logger.warning('check_available_leave(): argument named "application" missing, user: %s', session['username'])
        return error_message
    
    leave_available = LeaveAvailable.query.filter(LeaveAvailable.empid==application.empid, LeaveAvailable.year_start <= application.start_date, LeaveAvailable.year_end >= application.end_date).first()
    if not leave_available:
        current_app.logger.warning('check_available_leave(): leave_available record not found in table, user: %s (either record not created for a fiscal year or application start and end dates are in two different fiscal year)', session['username'])
        return error_message

    if application.type == 'Casual':
        if leave_available.casual >= application.duration:
            if update:
                casual = leave_available.casual - application.duration
                leave_available.casual = casual
                db.session.commit()
            return success_message
        else:
            total = leave_available.casual + leave_available.earned
            if total >= application.duration:
                if update:
                    earned = total - application.duration
                    leave_available.casual = 0
                    leave_available.earned = earned
                    db.session.commit()
                return success_message

    if application.type == 'Medical':
        if leave_available.medical >= application.duration:
            if update:
                medical = leave_available.medical - application.duration
                leave_available.medical = medical
                db.session.commit()
            return success_message
        else:
            total = leave_available.medical + leave_available.casual         
            if total >= application.duration:
                if update:
                    casual = total - application.duration
                    leave_available.medical = 0
                    leave_available.casual = casual
                    db.session.commit()
                return success_message
            else:
                total = total + leave_available.earned
                if total >= application.duration:
                    if update:
                        earned = total - application.duration
                        leave_available.medical = 0
                        leave_available.casual = 0
                        leave_available.earned = earned
                        db.session.commit()
                    return success_message
                
    return failed_messaage


def check_authorization(application):
    employee = Employee.query.filter_by(id=application.empid).first()
    
    if employee.role == 'Team':
        supervisor = Employee.query.join(Team).filter(Employee.id==session['empid'], Team.name==employee.teams[0].name, Employee.role=='Supervisor').first()
        if supervisor:
            return True
        
        manager = Employee.query.join(Team).filter(Employee.id==session['empid'], Team.name==employee.teams[0].name, Employee.role=='Manager').first()
        if manager:
            return True

        head = Employee.query.filter_by(id=session['empid'], department=employee.department, role='Head').first()
        if head:
            return True

    if employee.role == 'Supervisor':
        manager = Employee.query.join(Team).filter(Employee.id==session['empid'], Team.name==employee.teams[0].name, Employee.role=='Manager').first()
        if manager:
            return True

        head = Employee.query.filter_by(id=session['empid'], department=employee.department, role='Head').first()
        if head:
            return True
        
    if employee.role == 'Manager':
        head = Employee.query.filter_by(id=session['empid'], department=employee.department, role='Head').first()
        if head:
            return True

    return False


def get_emails(application, action):
    emails = {}
    
    employee = Employee.query.filter_by(id=application.empid).first()
    if not employee:
        current_app.logger.error(' get_emails(): employee record not found for application "%s" and user "%s"', application.id, application.empid)
        emails['error'] = True
        return emails

    admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR', Employee.email!=None).first()
    supervisor = Employee.query.join(Team).filter(Employee.role=='Supervisor', Team.name==employee.teams[0].name, Employee.email!=None).first()
    manager = Employee.query.join(Team).filter(Employee.role=='Manager', Team.name==employee.teams[0].name, Employee.email!=None).first()
    head = Employee.query.filter(Employee.department==employee.department, Employee.role=='Head', Employee.email!=None).first()

    cc = []

    if session['email']:
        emails['sender'] = session['email']
    else:
        current_app.logger.error(' get_emails(): session email not found for "%s"', session['username'])
        emails['error'] = True
        return emails
    
    if action == 'submit':
        if supervisor and session['role'] != 'Supervisor':
            emails['receiver'] = supervisor.email
        elif manager and session['role'] != 'Manager':
            emails['receiver'] = manager.email
        elif head and session['role'] != 'Head':
            emails['receiver'] = head.email
        else:
            emails['error'] = True
            return emails        
    elif action == 'cancel'and application.status.lower() == 'approval pending':
        if session['empid'] == application.empid:
            if employee.role.lower() == 'team':
                if supervisor:
                    if supervisor.email:
                        emails['receiver'] = supervisor.email
                    else:
                        current_app.logger.error(' get_emails: supervisor email not found')
                        emails['error'] = True
                        return emails
                elif manager:
                    if manager.email:
                        emails['receiver'] = manager.email
                    else:
                        current_app.logger.error(' get_emails: manager email not found')
                        emails['error'] = True
                        return emails
                elif head:
                    if head.email:
                        emails['receiver'] = head.email
                    else:
                        current_app.logger.error(' get_emails: head email not found')
                        emails['error'] = True
                        return emails
                else:
                    current_app.logger.error(' get_emails: team leader email not found')
                    emails['error'] = True
                    return emails
            elif employee.role.lower() == 'supervisor':
                if manager:
                    if manager.email:
                        emails['receiver'] = manager.email
                    else:
                        current_app.logger.error(' get_emails: manager email not found')
                        emails['error'] = True
                        return emails
                elif head:
                    if head.email:
                        emails['receiver'] = head.email
                    else:
                        current_app.logger.error(' get_emails: head email not found')
                        emails['error'] = True
                        return emails
                else:
                    current_app.logger.error(' get_emails: team leader email not found')
                    emails['error'] = True
                    return emails
            elif employee.role.lower() == 'manager':
                if head:
                    if head.email:
                        emails['receiver'] = head.email
                    else:
                        current_app.logger.error(' get_emails: head email not found')
                        emails['error'] = True
                        return emails
                else:
                    current_app.logger.error(' get_emails: team leader email not found')
                    emails['error'] = True
                    return emails
        else:
            if employee.email:
                emails['receiver'] = employee.email
            else:
                current_app.logger.error(' get_emails(): employee email not found for application "%s" and employee "%s"', application.id, application.empid)
                emails['error'] = True
                return emails
    else:
        if admin:
            emails['receiver'] = admin.email
        else:
            current_app.logger.error(' get_emails(): admin email not found for application "%s" and user "%s"', application.id, application.empid)
            emails['error'] = True
            return emails
        
        if employee.email:
                cc.append(employee.email)

        if session['role'] == 'Supervisor':
            if manager:
                cc.append(manager.email)
            elif head:
                cc.append(head.email)
            
        if session['role'] == 'Manager':
            if employee.role == 'Team':
                if supervisor:
                    cc.append(supervisor.email)
            if head:
                cc.append(head.email)
        
        if session['role'] == 'Head':
            if employee.role == 'Team':
                if supervisor:
                    cc.append(supervisor.email)
                if manager:
                    cc.append(manager.email)
            
            if employee.role == 'Supervisor':
                if manager:
                    cc.append(manager.email)
    
    cc.append(session['email'])
    emails['cc'] = cc  
    emails['error']  = False
    return emails


def return_leave(application):
    leave = LeaveAvailable.query.filter_by(empid=application.employee.id).first()
    if not leave:
        current_app.logger.warning(' cancel(): no data found in leave_available table for %s', application.employee.username)
        msg = f'No leave available for {application.employee.username}'
        return msg
    
    yearly_casual = current_app.config['CASUAL']
    yearly_medical = current_app.config['MEDICAL']

    if application.type == 'Casual':
        leave.casual = leave.casual + application.duration        
        if leave.casual > yearly_casual:
            extra_casual = leave.casual - yearly_casual
            leave.casual = yearly_casual
            leave.earned = leave.earned + extra_casual

    if application.type == 'Medical':
        leave.medical = leave.medical + application.duration
        if leave.medical > yearly_medical:
            extra_medical = leave.medical - yearly_medical
            leave.medical = yearly_medical

            leave.casual = leave.casual + extra_medical
            if leave.casual > yearly_casual:
                extra_casual = leave.casual - yearly_casual
                leave.earned = leave.earned + extra_casual
                leave.casual = yearly_casual

    db.session.commit()


def delete_files(files):
    file_list = ''

    for file in files:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file)

        if os.path.exists(file_path):
            os.remove(file_path)
        else:
            file_list += file_path

    return file_list

def check_application_dates(form, application_type):
    if re.search('^fiber', application_type):
        employee_id = form.empid.data
    else:
        employee_id = session['empid']

    if not form.start_date.data:
        return 'Start date must be given'

    start_date_exists = Applications.query.filter(Applications.start_date<=form.start_date.data, Applications.end_date>=form.start_date.data, Applications.empid==employee_id).first()
    if start_date_exists:
        return 'Start date overlaps with another application'

    if form.end_date.data:
        end_date_exists = Applications.query.filter(Applications.start_date<=form.end_date.data, Applications.end_date>=form.end_date.data, Applications.empid==employee_id).first()
        if end_date_exists:
            return 'End date overlaps with another application'

        any_date_exists = Applications.query.filter(Applications.start_date>form.start_date.data, Applications.end_date<form.end_date.data, Applications.empid==employee_id).first()
        if any_date_exists:
            return 'Start and/or end dates overlaps with other application'

def check_holiday_dates(form, application_type):
    if not form.holiday_duty_start_date.data:
        current_app.logger.error(' check_holiday_dates(): holiday_duty_start_date not given user "%s"', session['username'])
        return f'Holiday date check failed'
    
    if not application_type:
        current_app.logger.error(' check_holiday_dates(): application_type not given user "%s"', session['username'])
        return f'Holiday date check failed'

    if re.search('^fiber', application_type):
        employee_id = form.empid.data
    else:
        employee_id = session['empid']

    if not form.holiday_duty_end_date.data:
        form.holiday_duty_end_date.data = form.holiday_duty_start_date.data

    #Check whether holiday duty dates exists in any other application
    holiday_duty_start_date_exists = Applications.query.filter(Applications.holiday_duty_start_date<=form.holiday_duty_start_date.data, Applications.holiday_duty_end_date>=form.holiday_duty_start_date.data, Applications.empid==employee_id).first()
    if holiday_duty_start_date_exists:
        return 'Holiday duty start date overlaps with another application'
    
    if form.holiday_duty_start_date.data != form.holiday_duty_end_date.data:
        holiday_duty_end_date_exists = Applications.query.filter(Applications.start_date<=form.holiday_duty_end_date.data, Applications.end_date>=form.holiday_duty_end_date.data, Applications.empid==employee_id).first()
        if holiday_duty_end_date_exists:
            return 'Holiday duty end date overlaps with another application'

        any_date_exists = Applications.query.filter(Applications.start_date>form.holiday_duty_start_date.data, Applications.end_date<form.holiday_duty_end_date.data, Applications.empid==employee_id).first()
        if any_date_exists:
            return 'Holiday duty start and/or end dates overlaps with other application'

    #Check whether holidays added or not
    holiday = Holidays.query.filter(Holidays.start_date<=form.holiday_duty_start_date.data, Holidays.end_date>=form.holiday_duty_end_date.data).first()
    if not holiday:
        return f'One or more days not holiday between dates {form.holiday_duty_start_date.data} & {form.holiday_duty_end_date.data}'
    
    #Check whether attendance data is uploaded
    if form.holiday_duty_type.data == 'On site':
        holiday_duty_duration = (form.holiday_duty_end_date.data - form.holiday_duty_start_date.data).days + 1
        attendance = Attendance.query.with_entities(func.count(Attendance.id).label('count')).filter(Attendance.empid==employee_id, Attendance.date>=form.holiday_duty_start_date.data, Attendance.date<=form.holiday_duty_end_date.data).first()
        if holiday_duty_duration != attendance.count:
            return f'Attendance not found for one or more days between dates {form.holiday_duty_start_date.data} & {form.holiday_duty_end_date.data}'

        attendances = Attendance.query.filter(Attendance.empid==employee_id, Attendance.date>=form.holiday_duty_start_date.data, Attendance.date<=form.holiday_duty_end_date.data).all()
        no_attendance = datetime.strptime('00:00:00', "%H:%M:%S").time() 
        
        for attendance in attendances:
            if attendance.in_time == no_attendance:
                approved_attendance = Applications.query.filter(Applications.empid==employee_id, Applications.start_date<=attendance.date, Applications.end_date>=attendance.date, or_(Applications.type=='In', Applications.type=='Both')).first()
                if not approved_attendance:
                    return f'No attendance "In time" for date {attendance.date}'
                        
            if attendance.out_time == no_attendance:
                approved_attendance = Applications.query.filter(Applications.empid==employee_id, Applications.start_date<=attendance.date, Applications.end_date>=attendance.date, or_(Applications.type=='Out', Applications.type=='Both')).first()
                if not approved_attendance:
                    return f'No attendance "Out time" for date {attendance.date}'

# renaming original uploaded files and saving to disk, also creating a string 
# with all the file names for storing in database 
def save_files(files, username):
    file_names = ''
    file_id = datetime.now().strftime("%Y%m%d%H%M%S")
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


def send_mail(sender, receiver, type, **kwargs): 
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
            name = f"Leave: {application.type}"

        if type == 'attendance':
            name = f"Attendance: {application.type}"

        body = f"""
        Application ID: {application.id}
        Name: {application.employee.fullname}
        {name}
        Start date: {application.start_date}
        End date: {application.end_date}"""

        if application.holiday_duty_start_date:
            body += f"""
        Holiday duty start: {application.holiday_duty_start_date}
        Holiday duty end: {application.holiday_duty_end_date}"""
        
        body += f"""
        Remark: {application.remark} 
        Status: {application.status}"""

    
    #creating email body for password reset
    if type == 'reset':
        if 'extra' not in kwargs:
            return 'If "type" argument is "reset", you must provide "extra" argument'
        else:
            body = f"New password : {kwargs['extra']}"
    
    #creating email with header and body
    msg = EmailMessage()
    msg.add_header('from', sender)
    msg.add_header('to', receiver)
    
    if type == 'leave' or type == 'attendance':
        if 'cc' in kwargs:
            cc_list = ','.join(kwargs['cc'])
            msg.add_header('cc', cc_list)
    
    msg.add_header('date', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    msg.add_header('subject', subject)
    msg.set_content(body)
    
    #connecting to host
    try: 
        server = SMTP(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], local_hostname=None, timeout=5)
    except socket.timeout:
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


def check_office_time_dates(form):
    if not form.start_date.data:
        return 'Start date must be given'

    if not form.end_date.data:
        form.end_date.data = form.start_date.data

    start_date_exists = OfficeTime.query.filter(OfficeTime.start_date<=form.start_date.data, OfficeTime.end_date>=form.start_date.data).first()
    if start_date_exists:
        return 'Start date overlaps with another application'

    if form.end_date.data:
        end_date_exists = OfficeTime.query.filter(OfficeTime.start_date<=form.end_date.data, OfficeTime.end_date>=form.end_date.data).first()
        if end_date_exists:
            return 'End date overlaps with another application'

        any_date_exists = OfficeTime.query.filter(OfficeTime.start_date>form.start_date.data, OfficeTime.end_date<form.end_date.data).first()
        if any_date_exists:
            return 'Start and/or end dates overlaps with other application'


def update_available_leave(data: EmployeeFiscalYear) -> str:
    try:
        leave_available = LeaveAvailable.query.filter(LeaveAvailable.empid==data.employee.id, LeaveAvailable.fiscal_year_start_date <= data.fiscal_year_start_date, LeaveAvailable.fiscal_year_end_date >= data.fiscal_year_end_date).one() # type: ignore
    except NoResultFound as e:
        raise e
    except IntegrityError as e:
        current_app.logger.error('update_available_leave(): %s', e)
        raise e
    except SQLAlchemyError as e:
        current_app.logger.error('update_available_leave(): %s', e)
        raise e
    
    try:
        leave_allocated = LeaveAllocation.query.filter(LeaveAllocation.empid==data.employee.id, LeaveAllocation.fiscal_year_start_date <= data.fiscal_year_start_date, LeaveAllocation.fiscal_year_end_date >= data.fiscal_year_end_date).one() # type: ignore
    except NoResultFound as e:
        raise e
    except IntegrityError as e:
        current_app.logger.error('update_available_leave(): %s', e)
        raise e
    except SQLAlchemyError as e:
        current_app.logger.error('update_available_leave(): %s', e)
        raise e
    
    casual_approved = Applications.query.with_entities(db.func.sum(Applications.duration).label('days')).filter(Applications.start_date>=data.fiscal_year_start_date, Applications.start_date<=data.fiscal_year_end_date, Applications.empid==data.employee.id, Applications.type=='Casual', Applications.status=='Approved').first() # type: ignore
    if not casual_approved.days: # type: ignore
        casual_approved_days = 0
    else:
        casual_approved_days = casual_approved.days # type: ignore

    medical_approved = Applications.query.with_entities(db.func.sum(Applications.duration).label('days')).filter(Applications.start_date>=data.fiscal_year_start_date, Applications.start_date<=data.fiscal_year_end_date, Applications.empid==data.employee.id, Applications.type=='Medical', Applications.status=='Approved').first() # type: ignore
    if not medical_approved.days: # type: ignore
        medical_approved_days = 0
    else:
        medical_approved_days = medical_approved.days # type: ignore

    casual_deducted_1 = LeaveDeductionSummary.query.with_entities(db.func.sum(LeaveDeductionSummary.leave_deducted).label('days')).filter(LeaveDeductionSummary.empid==data.employee.id, LeaveDeductionSummary.year==data.fiscal_year_start_date.year, LeaveDeductionSummary.month>=7, LeaveDeductionSummary.month<=12).first() # type: ignore
    if not casual_deducted_1.days: # type: ignore
        casual_deducted_1_days = 0
    else:
        casual_deducted_1_days = casual_deducted_1.days # type: ignore

    casual_deducted_2 = LeaveDeductionSummary.query.with_entities(db.func.sum(LeaveDeductionSummary.leave_deducted).label('days')).filter(LeaveDeductionSummary.empid==data.employee.id, LeaveDeductionSummary.year==data.fiscal_year_end_date.year, LeaveDeductionSummary.month>=1, LeaveDeductionSummary.month<=6).first() # type: ignore
    if not casual_deducted_2.days: # type: ignore
        casual_deducted_2_days = 0
    else:
        casual_deducted_2_days = casual_deducted_2.days # type: ignore

    casual_deducted_days = casual_deducted_1_days + casual_deducted_2_days
    
    leave_available.casual = leave_allocated.casual
    leave_available.earned = leave_allocated.earned
    leave_available.medical = leave_allocated.medical
    leave_available_casual_earned = leave_available.casual + leave_available.earned
    casual_consumed = casual_approved_days + casual_deducted_days
    salary_deduct = 0
    if casual_consumed > 0:
        if casual_consumed <= leave_available.casual:
            leave_available.casual -= casual_consumed
        elif casual_consumed > leave_available.casual and casual_consumed <= leave_available_casual_earned:
            leave_available.earned = leave_available_casual_earned - casual_consumed
            leave_available.casual = 0
        else:
            leave_available.casual = 0
            leave_available.earned = 0
            salary_deduct = casual_consumed - leave_available_casual_earned
    
    leave_available_medical_casual = leave_available.medical + leave_available.casual
    leave_available_all = leave_available_medical_casual + leave_available.earned
    if medical_approved_days > 0:
        if medical_approved_days <= leave_available.medical:
            leave_available.medical -= medical_approved_days
        elif medical_approved_days > leave_available.medical and medical_approved_days <= leave_available_medical_casual:
            leave_available.medical = 0
            leave_available.casual = leave_available_medical_casual - medical_approved_days
        elif medical_approved_days > leave_available_medical_casual and medical_approved_days <= leave_available_all:
            leave_available.earned = leave_available_all - medical_approved_days
            leave_available.medical = 0
            leave_available.casual = 0
        else:
            leave_available.medical = 0
            leave_available.casual = 0
            leave_available.earned = 0
            salary_deduct = casual_consumed - leave_available_all

    db.session.commit()

    salary_deduct_message = ''
    if salary_deduct > 0:
        salary_deduct_message = f"(Salary deduct: {salary_deduct} days)"
    
    return f"Available leave updated {salary_deduct_message}"
    
def get_fiscal_year_start_end_2(supplied_date):
    year = supplied_date.year
    month = supplied_date.month
    
    if month <= 6:
        year_start_date = date((year - 1), 7, 1)
        year_end_date = date(year, 6, 30)
    else:
        year_start_date = date(year, 7, 1)
        year_end_date = date((year + 1), 6, 30)
    
    return year_start_date, year_end_date


def find_holiday_leaves(employee_id, attendances):
    if not attendances:
        raise Exception('Must provide attendances of an employee')
    
    class DateAroundHolidays():
        def __init__(self, date_before_holiday, date_after_holiday):
            self.date_before_holiday = date_before_holiday
            self.date_after_holiday = date_after_holiday

    #Creating holiday date list
    dates_around_holidays= []
    holiday_start_date = False
    for attendance in attendances:        
        if attendance['duty_shift']:
            if attendance['duty_shift'] == 'O' and attendance['application_type'] is None:
                if not holiday_start_date:
                    holiday_start_date = attendance['date']
            else:
                if holiday_start_date:
                    holiday_end_date = attendance['date']
                    date_around_holiday = DateAroundHolidays(holiday_start_date - timedelta(1), holiday_end_date)
                    dates_around_holidays.append(date_around_holiday)
                    holiday_start_date = False
        else: 
            if (attendance['day'] in ('Friday', 'Saturday') or attendance['holiday']) and attendance['application_type'] is None:
                if not holiday_start_date:
                    holiday_start_date = attendance['date']
            else:
                if holiday_start_date:
                    holiday_end_date = attendance['date']
                    date_around_holiday = DateAroundHolidays(holiday_start_date - timedelta(1), holiday_end_date)
                    dates_around_holidays.append(date_around_holiday)
                    holiday_start_date = False

    #Finding leave around holidays
    holiday_leave_days = 0
    for date_around_holiday in dates_around_holidays:
        leave_after_holiday_found = False
        leave_before_holiay_found = False
        for attendance in attendances:
            if attendance['date'] == date_around_holiday.date_before_holiday:
                if attendance['application_type'] in ('Casual', 'Medical') or attendance['in_flag'] == 'NI':
                    leave_before_holiay_found = True

            if attendance['date'] == date_around_holiday.date_after_holiday:
                if attendance['application_type'] in ('Casual', 'Medical') or attendance['in_flag'] == 'NI':
                    leave_after_holiday_found = True

            if leave_before_holiay_found and leave_after_holiday_found:
                leave_duration = (date_around_holiday.date_after_holiday - date_around_holiday.date_before_holiday).days - 1 #remove count of date_after_holiday
                holiday_leave_days += leave_duration
                break
                
    return holiday_leave_days

def get_fiscal_year(supplied_date: date) -> Tuple[date, date]:
    """
    Calculate the start and end dates of the fiscal year based on the provided date.

    Args:
        supplied_date (datetime.date): The date to calculate the fiscal year for.

    Returns:
        Tuple[datetime.date, datetime.date]: A tuple containing the start and end dates of the fiscal year.

    Raises:
        TypeError: If the supplied date is None.

    """
    if supplied_date.month <= 6:
        fiscal_year_start_date = date((supplied_date.year - 1), 7, 1)
        fiscal_year_end_date = date(supplied_date.year, 6, 30)
    else:
        fiscal_year_start_date = date(supplied_date.year, 7, 1)
        fiscal_year_end_date = date((supplied_date.year + 1), 6, 30)
    
    return fiscal_year_start_date, fiscal_year_end_date

def calculate_annual_leave(data: AnnualLeave) -> Tuple[int, int, int]:
    """
    Calculate the annual leave for an employee based on their joining date and the new fiscal year start date.

    Args:
        joining_date (date): The date the employee joined the company.
        new_fiscal_year_start_date (Optional[date]): The start date of the new fiscal year. If not provided, the current fiscal year will be used.

    Returns:
        Tuple[int, int, int]: A tuple containing the number of casual leave, medical leave, and earned leave for the employee.

    Raises:
        TypeError: If the joining_date is None.

    """
    (joining_fiscal_year_start_date, joining_fiscal_year_end_date) = get_fiscal_year(data.joining_date)
    
    if joining_fiscal_year_start_date == data.new_fiscal_year_start_date or not data.new_fiscal_year_start_date: # type: ignore
        casual_leave = ceil(current_app.config['CASUAL'] * (joining_fiscal_year_end_date - data.joining_date).days / 365)
        medical_leave = ceil(current_app.config['MEDICAL'] * (joining_fiscal_year_end_date - data.joining_date).days / 365)
        earned_leave = 0
    else:
        casual_leave = current_app.config['CASUAL']
        medical_leave = current_app.config['MEDICAL']
        work_duration = (data.new_fiscal_year_start_date - data.joining_date).days
        if work_duration > 365:
            earned_leave = current_app.config['EARNED']
        else:
            earned_leave = ceil(current_app.config['EARNED'] * (joining_fiscal_year_end_date - data.joining_date).days / 365)  

    return casual_leave, medical_leave, earned_leave