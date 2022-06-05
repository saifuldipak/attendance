import secrets
from flask import Blueprint, request, flash, redirect, render_template, session, url_for
from .db import db, Employee, Team, LeaveAvailable
from .forms import (Changeselfpass, Employeecreate, Employeedelete, Resetpass, Updatedept, 
                    Updateemail, Updatephone, Updaterole, Updateteam)
from werkzeug.security import generate_password_hash
from .mail import send_mail
from .auth import admin_required, login_required
import random
import string
from datetime import datetime, date

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
    if request.method == 'POST':
        department = request.form['department']

        if department == 'all':
            employees = Employee.query.all()
        else:
            employees = Team.query.join(Employee).filter(Team.department==department).all()
            
        return render_template('data.html', action='employee_search', employees=employees)
    
    return render_template('data.html', action='employee_search')

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
            
            if employee.email:
                flash('Email exists', category='error')
                return render_template('forms.html', form_type='employee_create', form=form)         
            
            email = form.email.data
        else:
            email = ''    

        if form.department.data == 'Accounts' or form.department.data == 'Sales' or \
            form.role.data == 'Head':
            team = ''
        else:
            team = form.team.data

        #creating entry in employee table
        employee = Employee(username=form.username.data, 
                            fullname=form.fullname.data, 
                            password=generate_password_hash(form.password.data),
                            phone=form.phone.data, email=email, department=form.department.data, 
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
        from_year = date.today().year
        to_year = from_year + 1
        available = LeaveAvailable(empid=employee.id, from_year=from_year, to_year=to_year, 
                                    casual=14, medical=14, earned=14)
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
    elif action == 'email':
        form = Updateemail()
    elif action == 'phone':
        form = Updatephone()
    elif action == 'role':
        form = Updaterole()
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
            employee.department = form.dept.data
            flash('Department updated', category='message')
        
        #update email
        if action == 'email':
            employee.email = form.email.data
            flash('Email updated', category='message')
        
        #update phone
        if action == 'phone':
            employee.phone = form.phone.data
            flash('Phone updated', category='message')

        #update role
        if action == 'role':
            if employee.role != form.role.data:
                employee.role = form.role.data
                flash('Role updated', category='message')
            else:
                flash('Current role and new role is same', category='warning')
        
        #reset password
        if action == 'pass':
            password = ''
            for _ in range(3):
                password += secrets.choice(string.ascii_lowercase)
                password += secrets.choice(string.ascii_uppercase)
                password += secrets.choice(string.digits)
            
            employee.password = generate_password_hash(password)

            admin = Employee.query.filter_by(username=session['username']).first()
            send_mail(admin.email, employee.email, password)
            
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