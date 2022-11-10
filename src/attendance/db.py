from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

#Employee record
class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(16), unique=True, nullable=False)
    fullname = db.Column(db.String(24), nullable=False)
    password = db.Column(db.String, nullable=True)
    email = db.Column(db.String(64))
    phone = db.Column(db.String(16))
    department = db.Column(db.String(24), nullable=False)
    designation = db.Column(db.String(16), nullable=False)
    role = db.Column(db.String(12), nullable=False)
    access = db.Column(db.String(8))
    teams = db.relationship('Team', backref='employee', cascade='delete, merge, save-update', lazy=True)
    applications = db.relationship('Applications', cascade='delete, merge, save-update', backref='employee', lazy=True)
    leaveavailable = db.relationship('LeaveAvailable', cascade='delete, merge, save-update', backref='employee', lazy=True)
    attendance = db.relationship('Attendance', cascade='delete, merge, save-update', backref='employee', lazy=True)
    attendancesummary = db.relationship('AttendanceSummary', cascade='delete, merge, save-update', backref='employee', lazy=True)
    dutyschedule = db.relationship('DutySchedule', cascade='delete, merge, save-update', backref='employee', lazy=True)

#Employee team
class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empid = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    name = db.Column(db.String)

#Leave applications 
class Applications(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empid = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    type = db.Column(db.String(16), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    duration = db.Column(db.Integer, nullable=False)
    remark = db.Column(db.String(100))
    submission_date = db.Column(db.DateTime, nullable=False)
    approval_date = db.Column(db.DateTime)
    file_url = db.Column(db.String)
    status = db.Column(db.String(16))
    holiday_duty_type = db.Column(db.String(20))
    holiday_duty_start_date = db.Column(db.Date)
    holiday_duty_end_date = db.Column(db.Date)

#Leave summary of each employee for a particular year
class LeaveAvailable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empid = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    year_start = db.Column(db.Date, nullable=False)
    year_end = db.Column(db.Date, nullable=False)
    casual = db.Column(db.Integer, nullable=False)
    medical = db.Column(db.Integer, nullable=False)
    earned = db.Column(db.Integer, nullable=False)

#Date wise in and out time data from attendance machines
class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empid = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    in_time = db.Column(db.Time)
    out_time = db.Column(db.Time)

#Holiday dates
class Holidays(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    applications_holidays = db.relationship('ApplicationsHolidays', cascade='delete, merge, save-update', backref='holidays', lazy=True)
    
class DutyShift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team = db.Column(db.String, nullable=False)
    name = db.Column(db.String, nullable=False)
    in_time = db.Column(db.Time, nullable=False)
    out_time = db.Column(db.Time, nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    dutyschedule = db.relationship('DutySchedule', cascade='delete, merge, save-update', backref='dutyshift', lazy=True)

class DutySchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team = db.Column(db.String, nullable=False)
    empid = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    duty_shift = db.Column(db.Integer, db.ForeignKey('duty_shift.id'))

#Monthly leave deduction of each employee
class LeaveDeductionSummary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    empid = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    late_early = db.Column(db.Integer) #days leave deducted due to late & early days
    casual_overlap = db.Column(db.Integer) #days leave deducted due to casual before or after holidays
    salary_deduct = db.Column(db.Integer) #days salary deducted due to leave unavailable
    attendance_summary = db.Column(db.Integer, db.ForeignKey('attendance_summary.id'))

#Datewise approved Leave/Attendance applications and holidays
class ApplicationsHolidays(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    empid = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'))
    holiday_id = db.Column(db.Integer, db.ForeignKey('holidays.id'))
    weekend_id = db.Column(db.Integer)

#Monthly attendance summary 
class AttendanceSummary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empid = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    absent = db.Column(db.Integer)
    late = db.Column(db.Integer)
    early = db.Column(db.Integer)
    leave_deduction_summary = db.relationship('LeaveDeductionSummary', backref='attendancesummary', lazy=True)

#Office timing for special cases
class OfficeTime(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    in_time = db.Column(db.Time, nullable=False)
    out_time = db.Column(db.Time, nullable=False)
    in_grace_time = db.Column(db.Integer)
    out_grace_time = db.Column(db.Integer)