""" from .db import Applications, ApprLeaveAttn, Employee, Team, AttendanceSummary, Attendance, Holidays
from flask import current_app, session
from sqlalchemy import func, or_ """

""" def check_application_dates(empid, start_date, end_date):
    if not start_date:
        return 'Start date must be given'

    start_date_exists = Applications.query.filter(Applications.start_date<=start_date, Applications.end_date>=start_date, 
                            Applications.empid==empid).first()
    if start_date_exists:
        return 'Start date overlaps with another application'

    if end_date:
        end_date_exists = Applications.query.filter(Applications.start_date<=end_date, Applications.end_date>=end_date, 
                        Applications.empid==empid).first()
        if end_date_exists:
            return 'End date overlaps with another application'

        any_date_exists = Applications.query.filter(Applications.start_date>start_date, Applications.end_date<end_date, 
                            Applications.empid==empid).first()
        if any_date_exists:
            return 'Start and/or end dates overlaps with other application' """


""" def check_holiday_dates(empid, holiday_duty_start_date, holiday_duty_end_date):
    if not holiday_duty_end_date:
        holiday_duty_end_date = holiday_duty_start_date

    #Check whether holiday duty dates exists in any other application
    holiday_duty_start_date_exists = Applications.query.filter(Applications.holiday_duty_start_date<=holiday_duty_start_date, 
                                        Applications.holiday_duty_end_date>=holiday_duty_start_date, 
                                        Applications.empid==empid).first()
    if holiday_duty_start_date_exists:
        return 'Holiday duty start date overlaps with another application'
    
    if holiday_duty_start_date != holiday_duty_end_date:
        holiday_duty_end_date_exists = Applications.query.filter(Applications.start_date<=holiday_duty_end_date, 
                                        Applications.end_date>=holiday_duty_end_date, Applications.empid==empid).first()
        if holiday_duty_end_date_exists:
            return 'Holiday duty end date overlaps with another application'

        any_date_exists = Applications.query.filter(Applications.start_date>holiday_duty_start_date, 
                            Applications.end_date<holiday_duty_end_date, Applications.empid==empid).first()
        if any_date_exists:
            return 'Holiday duty start and/or end dates overlaps with other application'

    #Check whether holidays added or not
    holiday_duty_duration = (holiday_duty_end_date - holiday_duty_start_date).days + 1
    holiday = Holidays.query.filter(Holidays.date>=holiday_duty_start_date, Holidays.date<=holiday_duty_end_date).\
                with_entities(func.count(Holidays.id).label('count')).one()
   
    if holiday_duty_duration != holiday.count:
        if holiday_duty_end_date != holiday_duty_start_date:
            return f'One or more days not holiday between dates {holiday_duty_start_date} & {holiday_duty_end_date}'
        else:
            return f'Date {holiday_duty_start_date} is not a holiday'

    #Check whether attendance data is uploaded
    attendances = Attendance.query.filter(Attendance.empid==empid, Attendance.date>=holiday_duty_start_date, 
                    Attendance.date<=holiday_duty_end_date).all()
    if not attendances:
        return f'Attendance not found for one or more days between dates {holiday_duty_start_date} & {holiday_duty_end_date}'
        
    for attendance in attendances:
        current_app.logger.warning('%s, %s, %s', empid, type(attendance.in_time), attendance.date)
        if attendance.in_time.strftime('%H:%M:%S') == '00:00:00':
            approved_attendance = ApprLeaveAttn.query.filter(ApprLeaveAttn.empid==empid, ApprLeaveAttn.date==attendance.date, 
                                    or_(ApprLeaveAttn.approved=='In', ApprLeaveAttn.approved=='Both')).first()
            if not approved_attendance:
                return f'No attendance "In time" for date {attendance.date}'
                       
        if attendance.out_time.strftime('%H:%M:%S') == '00:00:00':
            approved_attendance = ApprLeaveAttn.query.filter(ApprLeaveAttn.empid==empid, ApprLeaveAttn.date==attendance.date, 
                                    or_(ApprLeaveAttn.approved=='Out', ApprLeaveAttn.approved=='Both')).one()
            if not approved_attendance:
                return f'No attendance "Out time" for date {attendance.date}' """


""" def check_access(application_id):
    employee = Employee.query.join(Applications, Team).filter(Applications.id==application_id).first()
    supervisor = Employee.query.join(Team).filter(Team.name==employee.teams[0].name, Employee.role=='Supervisor').first()
    manager = Employee.query.join(Team).filter(Team.name==employee.teams[0].name, Employee.role=='Manager').first()
    head = Employee.query.filter_by(department=session['department'], role='Head').first()

    if employee.username == session['username']:
        return True
    elif supervisor or manager or head:
        return True
    elif session['access'] == 'Admin':
        return True
    else:
        return False """


""" def check_attnsummary(start_date, end_date=None):
    start_date_in_summary = AttendanceSummary.query.filter(AttendanceSummary.year==start_date.year, 
                                AttendanceSummary.month==start_date.strftime("%B")).first()
    
    found = False
    if start_date_in_summary:
        month = start_date.strftime("%B")
        year = start_date.year
        found = True
        
    if end_date:
        end_date_in_summary = AttendanceSummary.query.filter(AttendanceSummary.year==end_date.year, 
                                AttendanceSummary.month==end_date.strftime("%B")).first()
        if end_date_in_summary:
            month = end_date.strftime("%B")
            year = end_date.year
            found = True
    
    if found:
        msg = f'Attendance summary already prepared for {month}, {year}'
        return msg
    
    return False """