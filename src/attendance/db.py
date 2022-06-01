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
    approved = db.relationship('ApprLeaveAttn', cascade='delete, merge, save-update', backref='employee', lazy=True)
    attnsummary = db.relationship('AttnSummary', cascade='delete, merge, save-update', backref='employee', lazy=True)

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
    end_date = db.Column(db.Date, nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    remark = db.Column(db.String(100))
    submission_date = db.Column(db.DateTime, nullable=False)
    approval_date = db.Column(db.DateTime)
    file_url = db.Column(db.String)
    status = db.Column(db.String(16))

#Leave summary of each employee
class LeaveAvailable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empid = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    from_year = db.Column(db.Integer, nullable=False)
    to_year = db.Column(db.Integer, nullable=False)
    casual = db.Column(db.Integer, nullable=False)
    medical = db.Column(db.Integer, nullable=False)
    earned =db.Column(db.Integer, nullable=False)

#Date wise in and out time data from attendance machines
class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empid = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    in_time = db.Column(db.Time)
    out_time = db.Column(db.Time)

#Date wise approved leave and attendance status of each employee
class ApprLeaveAttn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empid = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    approved = db.Column(db.String)

#Attendance summary
class AttnSummary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empid = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.String, nullable=False)
    absent = db.Column(db.Integer)
    late = db.Column(db.Integer)
    late_absent = db.Column(db.Integer)
    deducted = db.Column(db.Integer)

#Leave deduction log
class LeaveDeduction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.String, nullable=False)
    month = db.Column(db.String, nullable=False)
    date = db.Column(db.DateTime, nullable=False)

