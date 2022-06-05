from flask import Blueprint, render_template, session
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import validators
from wtforms.fields import (DateField, TextAreaField, IntegerField, StringField, PasswordField, 
                        EmailField, TelField, SelectField) 
from wtforms.validators import InputRequired, ValidationError, EqualTo, InputRequired, Email
from .auth import admin_required, login_required, manager_required
from .db import Employee, Team
from werkzeug.security import check_password_hash


departments = ['Accounts', 'Sales', 'Technical']
teams = ['Customer Care', 'Support-Dhanmondi', 'Support-Gulshan', 'Support-Motijheel', 
                'Support-Nationwide', 'Support-Uttara','Implementation', 'Fiber-Dhanmondi', 
                'Fiber-Gulshan', 'Fiber-Motijheel', 'NS', 'NOC', 'NTN', 'WAN', 'HR', 'Billing', 
                'Accounts']
roles = ['Team', 'Manager', 'Head', 'Admin']
months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 
            'October', 'November', 'December']
attendance = ['No In', 'No Out', 'Late', 'Early Out']
years = ['2022', '2023', '2024', '2025']
actions = ['Add', 'Delete']
designations = ['GM', 'DGM', 'AGM', 'Sr. Manager', 'Manager', 'Dy. Manager', 'Asst. Manager', 'Sr. Network Engineer', 'Sr. Executive', 'Network Engineer', 'Executive', 'Jr. Network Engineer', 'Jr. Executive', 'Sr. Asst. Engineer', 'Asst. Engineer', 'Jr. Asst. Engineer']
roles = ['Team', 'Manager', 'Head']
access = ['User', 'Admin']

#validator function to check file size
def file_length_check(form, field):
    max_bytes = 1 * 1024 * 1024
    if field.data:
        if len(field.data.read()) > max_bytes:
            raise ValidationError('File size can be max 1MB')
        field.data.seek(0)

#Casual leave
class LeaveCasual(FlaskForm):
    start_date = DateField('Start Date',
                            format='%Y-%m-%d', 
                            render_kw={'class': 'input-field'},
                            validators=[InputRequired()])
    end_date = DateField('End Date',
                            format='%Y-%m-%d', 
                            render_kw={'class': 'input-field'},
                            validators=[InputRequired()])
    remark = TextAreaField('Remark',
                            render_kw={'class': 'input-field'})
    
    # extra validator added to check End date value with Start date value
    def validate(self):
        rv = FlaskForm.validate(self)
        if not rv:
            return False

        if self.start_date.data > self.end_date.data:
            self.end_date.errors.append('End date must be same or later than Start date')
            return False
        return True

#Casual leave for fiber team
class Leavefibercasual(LeaveCasual):
    empid = SelectField('Name', render_kw={'class' : 'input-field'}, choices=[], coerce=int, validate_choice=False)

#Medical leave
class LeaveMedical(LeaveCasual):
    file1 = FileField('Upload File 1', validators=[FileAllowed(['jpeg', 'jpg', 'png', 'gif'], 'Images only!'),
                                FileRequired(), file_length_check])
    file2 = FileField('Upload File 2', validators=[FileAllowed(['jpeg', 'jpg', 'png', 'gif'], 'Images only!'),
                                                file_length_check])
    file3 = FileField('Upload File 3', validators=[FileAllowed(['jpeg', 'jpg', 'png', 'gif'], 'Images only!'),
                                                file_length_check])
#Medical leave for fiber team
class Leavefibermedical(LeaveMedical, Leavefibercasual):
    pass

#Create employee record
class Employeecreate(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    fullname = StringField('Full Name', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    password = PasswordField('Password', 
                                render_kw={'class': 'input-field'}, 
                                validators=[InputRequired(), 
                                EqualTo('rpassword', message='Password must match')])
    rpassword = PasswordField('Retype Password', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    email = EmailField('Email', render_kw={'class': 'input-field'})
    phone = StringField('Phone', render_kw={'class': 'input-field'})
    department = SelectField('Department', render_kw={'class': 'input-field'},
                            choices=departments)
    designation = SelectField('Designation', render_kw={'class': 'input-field'}, 
                            choices=designations)
    team = SelectField('Team',      
                        render_kw={'class': 'input-field'},
                        choices=teams)
    role = SelectField('Role',
                            render_kw={'class': 'input-field'},
                            choices=roles)
    access = SelectField('Acess',
                        render_kw={'class': 'input-field'},
                        choices=access)

#Delete employee record
class Employeedelete(FlaskForm):
    empid = IntegerField('Employee ID', render_kw={'class': 'input-field'}, validators=[InputRequired()])

#Update employee record
class Employeeupdate(FlaskForm):
    empid = StringField('Employee ID', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    team = SelectField('Team Add', 
                        render_kw={'class': 'input-field'},
                        choices=teams)

#Attendance file upload
class Attndataupload(FlaskForm):
    file1 = FileField('Upload File 1', 
                        validators=[FileAllowed(['xls', 'xlsx'], '.xls & .xlsx only!'), FileRequired()])

#Attendance query for all 
class Attnqueryall(FlaskForm):
    month = SelectField('Month', render_kw={'class': 'input-field'}, choices=months)
    type = SelectField('Type', render_kw={'class': 'input-field'}, choices=['Summary', 'Details'])
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                                        validators=[validators.Optional()])
    
    # extra validator added to check username given if type is selected  'Details' by user
    def validate(self):
        rv = FlaskForm.validate(self)
        if not rv:
            return False

        if self.type.data == 'Details' and not self.username.data:
            self.type.errors.append('Must give "Username" if type is "Details"')
            return False
        return True

#Attendance query by admin datewise
class Attnqueryalldate(FlaskForm):
    date = DateField('Date', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    
#Attendance query by admin userwise 
class Attnqueryallusername(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    month = SelectField('Month', render_kw={'class': 'input-field'}, choices=months)

#Attendance query for self
class Attnqueryself(FlaskForm):
    month = SelectField('Month', render_kw={'class': 'input-field'}, choices=months)

#Attendance approval application
class Attnapplication(FlaskForm):
    start_date = DateField('Start Date',
                            format='%Y-%m-%d', 
                            render_kw={'class': 'input-field'},
                            validators=[InputRequired()])
    end_date = DateField('End Date',
                            format='%Y-%m-%d', 
                            render_kw={'class': 'input-field'},
                            validators=[InputRequired()])
    remark = TextAreaField('Remark',
                            render_kw={'class': 'input-field'},
                            validators=[InputRequired()])
    
    # extra validator added to check End date value with Start date value
    def validate(self):
        rv = FlaskForm.validate(self)
        if not rv:
            return False

        if self.start_date.data > self.end_date.data:
            self.end_date.errors.append('End date must be same or later than Start date')
            return False
        return True

#Attendance summary
class Attnsummary(FlaskForm):
    year = SelectField('Year', render_kw={'class': 'input-field'}, choices=years)
    month = SelectField('Month', render_kw={'class': 'input-field'}, choices=months)

#Attendance summary
class Leavededuction(FlaskForm):
    year = SelectField('Year', render_kw={'class': 'input-field'}, choices=years)
    month = SelectField('Month', render_kw={'class': 'input-field'}, choices=months)

#Self password change
class Changeselfpass(FlaskForm):
    password = PasswordField('Password', 
                                render_kw={'class': 'input-field'}, 
                                validators=[InputRequired(), 
                                EqualTo('rpassword', message='Password must match')])
    rpassword = PasswordField('Retype Password', 
                                render_kw={'class': 'input-field'}, 
                                validators=[InputRequired()])

    #extra validators
    def validate(self):
        rv = FlaskForm.validate(self)
        if not rv:
            return False

        employee = Employee.query.filter_by(username=session['username']).first()
        match = check_password_hash(employee.password, self.password.data)
        
        if match:
            self.password.errors.append('old password and new password cannot be same')
            return False

        if len(self.password.data) < 8:
            self.password.errors.append('length must be at least 8 characters')
            return False
        
        #if not re.search('[A-Z0-9]', self.password.data):
        #    self.password.errors.append('password must contain at least one capital letter and one number')
        #    return False

        return True

#Update employee email 
class Updateemail(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])
    email = EmailField('Email', render_kw={'class': 'input-field'}, 
                        validators=[InputRequired(), Email(message='Email not correct')])

#Update employee phone
class Updatephone(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])
    phone = TelField('Phone', render_kw={'class': 'input-field'}, 
                        validators=[InputRequired()])

#Update team
class Updateteam(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])
    team = SelectField('Team', render_kw={'class': 'input-field'}, choices=teams)
    action = SelectField('Action', render_kw={'class': 'input-field'}, choices=actions)

#Update department
class Updatedept(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])
    dept = SelectField('Team', render_kw={'class': 'input-field'}, choices=departments)
    

#Reset password
class Resetpass(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])

#Update role
class Updaterole(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])
    role = SelectField('Role', render_kw={'class': 'input-field'}, choices=roles)

forms = Blueprint('forms', __name__)

#Leave application
@forms.route('/forms/leave/<type>', methods=['GET', 'POST'])
@login_required
def leave(type):

    if type == 'Casual':
        form = LeaveCasual()
    elif type == 'Medical':
        form = LeaveMedical()
    
    return render_template('forms.html', type='leave', leave=type, form=form)

#Employee create
@forms.route('/forms/employee/<action>', methods=['GET', 'POST'])
@login_required
@admin_required
def employee(action):

    if action == 'create':
        form = Employeecreate()
        form_type = 'employee_create'
    elif action == 'delete':
        form = Employeedelete()
        form_type = 'employee_delete'
    elif action == 'update':
        form = Employeeupdate()
        form_type = 'employee_update'
    
    return render_template('forms.html', form_type=form_type, form=form)

#Attendance file upload 
@forms.route('/forms/attendance/upload', methods=['GET', 'POST'])
@login_required
def upload():
    form = Attndataupload()
    return render_template('forms.html', form_type='attendance_upload', form=form)

#Attendance query for all by admin user
@forms.route('/forms/attendance/query/all/<type>', methods=['GET', 'POST'])
@login_required
@admin_required
def attnquery_all(type):
    if type == 'date':
        form = Attnqueryalldate()
    elif type == 'username':
        form = Attnqueryallusername()
    
    return render_template('attn_query.html', type=type, form=form)

#Attendance query for team by manager
@forms.route('/forms/attendance/query/team', methods=['GET', 'POST'])
@login_required
@manager_required
def attnquery_team():
    form = Attnqueryall()
    return render_template('forms.html', type='attnquery', user='team', form=form)

#Attendance query for self
@forms.route('/forms/attendance/query/self', methods=['GET', 'POST'])
@login_required
def attnquery_self():
    form = Attnqueryself()
    return render_template('forms.html', type='attnquery', user='self', form=form)

#Attendance application
@forms.route('/forms/attendance/application')
@login_required
def attn_application():
    form = Attnapplication()
    return render_template('forms.html', type='attn_application', form=form)

#Attendance summary 
@forms.route('/forms/attendance/summary')
@login_required
@admin_required
def attn_summary():
    form = Attnsummary()
    return render_template('forms.html', type='attn_summary', form=form)

#Leave deduction
@forms.route('/forms/leave/deduction')
@login_required
@admin_required
def leave_deduction():
    form = Leavededuction()
    return render_template('forms.html', type='leave_deduction', form=form)

#password change
@forms.route('/forms/employee/password/self')
@login_required
def password_self():
    form = Changeselfpass()
    return render_template('forms.html', type='change_pass', user='self', form=form)

#update email
@forms.route('/forms/employee/update_email')
@login_required
@admin_required
def update_email():
    form = Updateemail()
    return render_template('emp_update.html', type='email', form=form)

#update phone
@forms.route('/forms/employee/update_phone')
@login_required
@admin_required
def update_phone():
    form = Updatephone()
    return render_template('emp_update.html', type='phone', form=form)

#delete or add team
@forms.route('/forms/employee/update_team')
@login_required
@admin_required
def update_team():
    form = Updateteam()
    return render_template('emp_update.html', type='team', form=form)

#modify department
@forms.route('/forms/employee/update_dept')
@login_required
@admin_required
def update_dept():
    form = Updatedept()
    return render_template('emp_update.html', type='dept', form=form)

#reset password
@forms.route('/forms/employee/reset_pass')
@login_required
@admin_required
def reset_pass():
    form = Resetpass()
    return render_template('emp_update.html', type='pass', form=form)

#update role
@forms.route('/forms/employee/update_role')
@login_required
@admin_required
def update_role():
    form = Updaterole()
    return render_template('emp_update.html', type='role', form=form)

#Leave application Fiber
@forms.route('/forms/leave/fiber/<type>', methods=['GET', 'POST'])
@login_required
def leave_fiber(type):

    if type == 'Casual':
        form = Leavefibercasual()
    elif type == 'Medical':
        form = Leavefibermedical()
    
    names = Employee.query.join(Team).filter(Team.name==session['team'], Employee.role=='Team').all()
    form.empid.choices = [(i.id, i.fullname) for i in names]
    
    return render_template('forms.html', type='leave', leave=type, team='fiber', form=form)