import secrets
from flask import Blueprint, current_app, request, flash, redirect, render_template, session, url_for

from attendance.check import check_attnsummary
from .db import AttnSummary, Holidays, db, Employee, Team, LeaveAvailable
from .forms import (Addholidays, Changeselfpass, Employeecreate, Employeedelete, Employeesearch, Resetpass, Updateaccess, Updatedept, Updatedesignation, 
                    Updateemail, Updatefullname, Updatephone, Updaterole, Updateteam)
from werkzeug.security import generate_password_hash
from .mail import send_mail
from .auth import admin_required, login_required
import random
import string
from datetime import datetime, date, timedelta
from sqlalchemy import extract

employee = Blueprint('employee', __name__)

#Generate random string for password
def random_string_generator():
    allowed_chars = string.ascii_letters
    str_size = 8
    return ''.join(random.choice(allowed_chars) for x in range(str_size))

#making string for fiscal year
def fiscalyear():
    currentyear = int(datetime.now().strftime('%Y'))
    month = int(datetime.now().strftime('%m'))
    if month >= 6:
        nextyear = currentyear + 1
        year = str(currentyear) + '-' + str(nextyear)
    else:
        lastyear = currentyear - 1
        year = str(lastyear) + '-' + str(currentyear)
    
    return year    

## Search employee record ##
@employee.route('/employee/search', methods=['GET', 'POST'])
@login_required
@admin_required
def search():
    form = Employeesearch()
    
    if form.validate_on_submit():
        #creating string for sql like query
        string = f'{form.string.data}%'
        
        if form.type.data.lower() == 'username':
            employees = Employee.query.filter(Employee.username.like(string)).all()
        elif form.type.data.lower() == 'fullname':
            string = f'%{form.string.data}%'
            employees = Employee.query.filter(Employee.fullname.like(string)).all()
        elif form.type.data.lower() == 'department':
            employees = Employee.query.filter(Employee.department.like(string)).all()
        elif form.type.data.lower() == 'team':
            employees = Employee.query.join(Team).filter(Team.name.like(string)).all()
        elif form.type.data.lower() == 'designation':
            employees = Employee.query.filter(Employee.designation.like(string)).all()
        elif form.type.data.lower() == 'access':
            employees = Employee.query.filter(Employee.access.like(string)).all()
        else:
            employees = Employee.query.all()

        return render_template('data.html', action='employee_search', form=form, employees=employees)
    
    return render_template('data.html', action='employee_search', form=form)

## Show detail employee record for every employee ##
@employee.route('/employee/details/<id>', methods=['GET', 'POST'])
@login_required
@admin_required
def details(id):
    employee = Employee.query.filter_by(id=id).first()

    return render_template('data.html', type='employee_details', employee=employee)
            
## Create employee record ##
@employee.route('/employee/create', methods=['GET', 'POST'])
@login_required
@admin_required     
def create():
    form = Employeecreate()

    if form.validate_on_submit(): 
        
        username = Employee.query.filter_by(username=form.username.data).first()  
        if username:
            flash('Username exists', category='error')
            return render_template('forms.html', form_type='employee_create', form=form)

        #check if email already exists in database
        if form.email.data:
            employee = Employee.query.filter_by(email=form.email.data).first()
            
            if employee:
                flash('Email exists', category='error')
                return render_template('forms.html', form_type='employee_create', form=form)  

        if form.department.data == 'Accounts' or form.department.data == 'Sales' or \
            form.role.data == 'Head':
            team = ''
        else:
            team = form.team.data

        #creating entry in employee table
        employee = Employee(username=form.username.data, 
                            fullname=form.fullname.data, 
                            password=generate_password_hash(form.password.data),
                            phone=form.phone.data, email=form.email.data, department=form.department.data, 
                            designation=form.designation.data, role=form.role.data, access=form.access.data)

        db.session.add(employee)
        db.session.commit()
        
        #getting employee_id of newly created user and creating 'team' and 'LeaveAvailable' 
        #table entry using that employee_id
        employee = Employee.query.filter_by(username=form.username.data).first()
        
        #setting team name 'All' for department heads
        if form.role.data=='Head':
            name = 'All'
        else:
            name = form.team.data

        team = Team(empid=employee.id, name=name)
        db.session.add(team)

        #adding yearly leave 
        current_year = date.today().year
        current_month = date.today().month
        if current_month <= 6:
            year_start = date((current_year - 1), 7, 1)
            year_end = date(current_year, 6, 30)
        else:
            year_start = date(current_year, 7, 1)
            year_end = date((current_year + 1), 6, 30)

        available = LeaveAvailable(empid=employee.id, year_start=year_start, year_end=year_end, 
                                    casual=current_app.config['CASUAL'], medical=current_app.config['MEDICAL'], 
                                    earned=current_app.config['EARNED'])
        db.session.add(available)
        db.session.commit()

    flash("Employee record created.", category='message')
    return redirect(url_for('forms.employee', action='create'))

## Delete employee record ##
@employee.route('/employee/delete', methods=['GET', 'POST'])
@login_required
@admin_required    
def delete():     
    form = Employeedelete()

    if form.validate_on_submit():
        employee = Employee.query.filter_by(id=form.empid.data).first()
        error = ''

        #At least one 'Admin' role employee must exists in the 'employee' table
        if employee:
            if employee.role == 'Admin':
                admincount = Employee.query.filter_by(role='Admin').count()
                if admincount < 2:
                    error = 'Your are trying to delete last "Admin" user'
        else:
            error = 'Employee ID not found'

        if error != '':
            flash(error, category='error')
            return render_template('forms.html', form_type='employee_delete', form=form)
        
        #Finally delete 'employee' table entry
        db.session.delete(employee)
        db.session.commit()
        
        flash('Employee deleted', category='message')

    return redirect(url_for('forms.employee', action='delete'))

## Employee record update menu ##
@employee.route('/employee/update_menu')
@login_required
@admin_required     
def update_menu():
    return render_template('emp_update.html')

## Update employee record  ##
@employee.route('/employee/update/<action>', methods=['GET', 'POST'])
@login_required
@admin_required     
def update(action):
    
    if action == 'team':
        form = Updateteam()
    elif action == 'dept':
        form = Updatedept()
    elif action == 'designation':
        form = Updatedesignation()
    elif action == 'email':
        form = Updateemail()
    elif action == 'fullname':
        form = Updatefullname()
    elif action == 'phone':
        form = Updatephone()
    elif action == 'role':
        form = Updaterole()
    elif action == 'access':
        form = Updateaccess()
    elif action == 'pass':
        form = Resetpass()
    else:
        flash('Function not found', category='error')
        return redirect(url_for('employee.update_menu'))

    if form.validate_on_submit():
        employee = Employee.query.filter_by(username=form.username.data).first()
        
        if not employee:
            flash('Username not found.', category='error')
            return redirect(request.url)
        
        #add or delete team
        if action == 'team':
            team = Team.query.filter_by(empid=employee.id, name=form.team.data).first()

            if form.action.data == 'Add':
                if not team:
                    team = Team(empid=employee.id, name=form.team.data)
                    db.session.add(team)
                    flash('Team added', category='message')
                else:
                    flash('Team name already exists', category='error')
                    return redirect(url_for('forms.update_team'))
            
            if form.action.data == 'Delete':
                if team:
                    db.session.delete(team)
                    flash('Team deleted', category='message')
                else:
                    flash('Team name not found', category='error')
        
        #update department
        if action == 'dept':
            if employee.department == form.dept.data:
                flash('Current and new department is same', category='warning')
            else:
                employee.department = form.dept.data
                flash('Department updated', category='message')
        
        if action == 'designation':
            if employee.designation == form.designation.data:
                flash('Current and new designation is same', category='warning')
            else:
                employee.designation = form.designation.data
                flash('Designation updated', category='message')

        #update email
        if action == 'email':
            if employee.email == form.email.data:
                flash('Current and new email is same', category='warning')
            else:
                employee.email = form.email.data
                flash('Email updated', category='message')
        
        #update fullname
        if action == 'fullname':
            if employee.fullname == form.fullname.data:
                flash('Current and new fullname is same', category='warning')
            else:
                employee.fullname = form.fullname.data
                flash('Fullname updated', category='message')

        #update phone
        if action == 'phone':
            if employee.phone == form.phone.data:
                flash('Current and new phone is same', category='warning')
            else:
                employee.phone = form.phone.data
                flash('Phone updated', category='message')

        #update role
        if action == 'role':
            if employee.role != form.role.data:
                employee.role = form.role.data
                flash('Role updated', category='message')
            else:
                flash('Current and new role is same', category='warning')
        
        #update access
        if action == 'access':
            if employee.access != form.access.data:
                employee.access = form.access.data
                flash('Access updated', category='message')
            else:
                flash('Current and new access is same', category='warning')

        #reset password
        if action == 'pass':
            password = ''
            for _ in range(3):
                password += secrets.choice(string.ascii_lowercase)
                password += secrets.choice(string.ascii_uppercase)
                password += secrets.choice(string.digits)
            
            employee.password = generate_password_hash(password)

            admin = Employee.query.filter_by(username=session['username']).first()
            send_mail(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], sender=admin.email, 
                        receiver=employee.email, type='reset', extra=password)
            
            flash('Password reset', category='message')

        db.session.commit()

    return redirect(url_for('employee.update_menu'))


## Change password for self ##
@employee.route('/employee/password/self', methods=['GET', 'POST'])
@login_required    
def password_self():
    form = Changeselfpass()

    if form.validate_on_submit():
        employee = Employee.query.filter_by(username=session['username']).first()
        employee.password = generate_password_hash(form.password.data)
        db.session.commit()
        flash('Password changed', category='message')

    return render_template('forms.html', type='change_pass', form=form)

## Show detail employee record for self ##
@employee.route('/employee/details/self', methods=['GET', 'POST'])
@login_required
def details_self():
    employee = Employee.query.filter_by(username=session['username']).first()

    return render_template('data.html', type='employee_details', employee=employee)

@employee.route('/employee/holidays/<action>', methods=['GET', 'POST'])
@login_required
@admin_required
def holidays(action):
    
    if action == 'show':
        holidays = Holidays.query.filter(extract('year', Holidays.date)==datetime.now().year).all()
        return render_template('data.html', type='holidays', holidays=holidays)
    elif action == 'add':
        form = Addholidays()

        if form.validate_on_submit():
            if not form.end_date.data:
                form.end_date.data = form.start_date.data
            
            rv = check_attnsummary(form.start_date.data, form.end_date.data)
            if rv:
                flash(rv, category='error')
                return redirect(url_for('employee.holidays', action='show'))

            holiday = Holidays.query.filter(Holidays.date>=form.start_date.data, Holidays.date<=form.end_date.data).first()
            if holiday:
                    flash('Date exists in holidays', category='error')
                    return redirect(url_for('employee.holidays', action='show'))

            while form.start_date.data <= form.end_date.data:
                holiday = Holidays(date=form.start_date.data, name=form.name.data)
                db.session.add(holiday)
                form.start_date.data += timedelta(days=1)
            
            db.session.commit()
            return redirect(url_for('employee.holidays', action='show'))

        return render_template('forms.html', type='add_holiday', form=form)
    elif action == 'delete':
        holiday_name = request.args.get('holiday_name')
        holidays = Holidays.query.filter_by(name=holiday_name).all()
        for holiday in holidays:
            rv = check_attnsummary(holiday.date)
            if rv:
                flash(rv, category='error')
                return redirect(url_for('employee.holidays', action='show'))
        
        for holiday in holidays:
            db.session.delete(holiday)
        
        db.session.commit()
    else:
        current_app.logger.error(' holidays(): unknown action %s', action)
        flash('Unknown action', category='error')
    
    return redirect(url_for('employee.holidays', action='show'))