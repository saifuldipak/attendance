from flask import Blueprint, current_app, request, session, redirect, url_for, render_template, flash, g
from .db import Employee, Team
from werkzeug.security import check_password_hash
import functools

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
    
        error = None
        
        employee = Employee.query.filter_by(username=username).first()

        #Checking username, password and access data from employee table
        if employee is None:
            error = 'Incorrect username/password.'
            current_app.logger.warning('"%s" login failed (wrong username)', username)
        elif not check_password_hash(employee.password, password):
            error = 'Incorrect username/password.'
            current_app.logger.warning('"%s" login failed (wrong password)', username)
        elif employee.access != 'Admin' and employee.access != 'User':
            error = 'Access denied'
            current_app.logger.warning('"%s" login failed (access denied)', username) 

        if error is None:
            session['empid'] = employee.id
            session['username'] = employee.username
            session['fullname'] = employee.fullname
            session['role'] = employee.role
            session['department'] = employee.department
            session['access'] = employee.access
            session['email'] = employee.email
            
            #Getting team name 
            team = Team.query.filter_by(empid=employee.id).first()
            if team:
                session['team'] = team.name
            
            session.permanent = True
            current_app.logger.info('"%s" login sucessfull', username)
            
            return render_template('index.html')        
                    
        flash(error, category='error')
    return render_template('auth/login.html')

@auth.before_app_request
def load_logged_in_user():
    username = session.get('username')

    if username is None:
        g.user = None
    else:
        g.user = Employee.query.filter_by(username=username).first()

@auth.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

#check whether user is logged in or not
def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        
        if g.user is None:
            return redirect(url_for('auth.login'))

        return view(**kwargs)
    
    return wrapped_view

#check whether user's role is 'Admin' or not
def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        
        if g.user.access != 'Admin':
            flash('You are not authorized to access', category='error')
            current_app.logger.warning('"%s" not in "HR" or not "Manager" or both', g.user.username)
            return render_template('base.html')

        return view(**kwargs)
    
    return wrapped_view

#check whether user's role is 'Manager' or not
def manager_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        
        if g.user.role != 'Manager':
            flash('You are not authorized to access', category='error')
            return render_template('base.html')

        return view(**kwargs)
    
    return wrapped_view

#check whether user's role is 'Head' or not
def head_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        
        if g.user.role != 'Head':
            flash('You are not authorized to access', category='error')
            return render_template('base.html')

        return view(**kwargs)
    
    return wrapped_view

#check whether user's role is 'Supervisor' or not
def supervisor_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        
        if g.user.role != 'Supervisor':
            flash('You are not authorized to access', category='error')
            return render_template('base.html')

        return view(**kwargs)
    
    return wrapped_view

def team_leader_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user.role not in ('Supervisor', 'Manager', 'Head'):
            flash('You are not authorized to access', category='error')
            return render_template('base.html')
        return view(**kwargs)
    return wrapped_view