from datetime import datetime, timedelta
from threading import local
from flask import Blueprint, current_app, request, flash, redirect, render_template, session, url_for
from sqlalchemy import and_, or_, extract, func
import pandas as pd
from .check import date_check, user_check
from .mail import send_mail
from .forms import Attnapplfiber, Attnqueryall, Attnqueryalldate, Attnqueryallusername, Attnqueryself, Attndataupload, Attnapplication, Attnsummary
from .db import AttnSummary, Team, db, Employee, Attendance, Applications, ApprLeaveAttn
from .auth import login_required, admin_required, manager_required

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
                #converting data in dataframe to appropriate column data types
                empid = int(df.iat[i, 0])
                date = datetime.strptime(df.iat[i, 1], "%m/%d/%Y")
                
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

                # check whether employee id exists in 'employee' table
                employee = Employee.query.filter_by(id=empid).first()
                if not employee:
                    error = 'Employee ID' + " '" + str(empid) + "' " + 'does not exists'
                    flash(error, category='error')
                    return redirect(request.url)

                # check whether employee and date maches any record in 'Attendance' table
                # this is done to eliminate the possibility of entering duplicate data in database
                data = Attendance.query.filter(and_(Attendance.empid==empid, 
                                                   Attendance.date==date)).first()

                if data:
                    error = 'Employee ID' + " '" + str(empid) + "' & date" + " '" + date + "' " \
                            + 'record already exists'
                    flash(error, category='error')
                    return redirect(request.url)

                # check approved applications for each date and employee id from Applications 
                # table
                application = Applications.query.filter(empid==empid).\
                                                filter(and_(Applications.start_date >= date, 
                                                            Applications.end_date <= date)).first()
                
                if not application:
                    approved = ''
                else:
                    approved = application.type

                apprleaveattn = ApprLeaveAttn(empid=empid, date=date, approved=approved)
                db.session.add(apprleaveattn)

                attendance = Attendance(empid=empid, date=date, in_time=in_time, out_time=out_time)
                db.session.add(attendance)

            db.session.commit()

            # write data frame to 'Attendance' table
            #df.to_sql('Attendance', con=db.engine, if_exists='append', index=None, 
            #            dtype={'date': db.Date, 'in_time': db.String, 'out_time': db.String})
            flash('Data uploaded successfully', category='message')
            
    return render_template('forms.html', form_type='attendance_upload', form=form)

#Query menu for all attendance data by Admin
@attendance.route('/attendance/query/all/menu')
@login_required
@admin_required
def query_menu():
    return render_template('attn_query.html')

#Query attendance data by individual employee username and prepare summary report of 
#absence and late attendance, this view is for admin users only 
@attendance.route('/attendance/query/all/<query_type>', methods=['GET', 'POST'])
@login_required
@admin_required
def query_all(query_type):

    #creating form object using appropriate class based on type
    if query_type == 'date':
        form = Attnqueryalldate()
    elif query_type == 'username':
        form = Attnqueryallusername()

    if form.validate_on_submit():
        #query by date
        if query_type == 'date':
            attendance = db.session.query(Employee.fullname, Attendance.date, Attendance.in_time, 
                                                Attendance.out_time, ApprLeaveAttn.approved).\
                            join(Employee, Attendance.empid==Employee.id).\
                            join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, 
                                                    Attendance.empid==ApprLeaveAttn.empid)).\
                            filter(Attendance.date==form.date.data).\
                            order_by(Attendance.date).all()
            
            return render_template('data.html', type='attn_details', query='all', query_type=query_type, 
                                        form=form, attendance=attendance)          
        #query by username
        if query_type == 'username':
            employee = Employee.query.filter_by(username=form.username.data).first()
            
            if employee:
                month = datetime.strptime(form.month.data, "%B").month

                attendance = db.session.query(Attendance.date, Attendance.in_time, 
                                                Attendance.out_time, ApprLeaveAttn.approved).\
                            join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, 
                                                    Attendance.empid==ApprLeaveAttn.empid)).\
                            filter(Attendance.empid==employee.id).\
                            filter(extract('month', Attendance.date)==month).\
                            order_by(Attendance.date).all()

                return render_template('data.html', type='attn_details', query='all', 
                                            fullname=employee.fullname, query_type=query_type, 
                                            form=form, attendance=attendance)
            else:
                flash('Username not found', category='error')
                return redirect(url_for('attendance.query_menu'))
        
        #query summary by month
        if type == 'summary':
            summary = AttnSummary.query.join(Employee).\
                                        filter(extract('month', Attendance.date)==month).all()
                               
            return render_template('data.html', type='attn_summary', query='all', form=form, summary=summary)
   
    return render_template('attn_query.html')


#Query attendance data by individual employee username and prepare summary report of 
#absence and late attendance, this view is for managers to see only their team members
#attendance records
@attendance.route('/attendance/query/team', methods=['GET', 'POST'])
@login_required
@manager_required
def query_team():
    form = Attnqueryall()

    if form.validate_on_submit():
        month = month_name_num(form.month.data)

        if form.type.data == 'Details':
            employee = Employee.query.join(Team).filter(Employee.username==form.username.data).first()
            
            if not employee:
                flash('Username not found', category='error')
                return redirect(url_for('forms.attnquery_team'))

            manager = Employee.query.join(Team).filter(Employee.role=='Manager').\
                                            filter(Team.name==employee.teams[0].name).first()
            
            if manager.username != session['username']:
                flash('You are not the manager of this employee', category='error')
                return redirect(url_for('forms.attnquery_team'))

            attendance = db.session.query(Attendance.date, Attendance.in_time, Attendance.out_time, 
                                            ApprLeaveAttn.approved).\
                            join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, 
                                                    Attendance.empid==ApprLeaveAttn.empid)).\
                            filter(Attendance.empid==employee.id).\
                            filter(extract('month', Attendance.date)==month).\
                            order_by(Attendance.date).all()

            return render_template('data.html', type='attn_details', query='team', form=form, 
                                    attendance=attendance)
            
        else:
            manager = Employee.query.join(Team).filter(Employee.username==session['username']).first()
            
            summary = []
            
            for team in manager.teams:
                result = db.session.query(Employee.fullname, AttnSummary.absent, AttnSummary.late).\
                                            join(Employee).join(Team, AttnSummary.empid==Team.empid).\
                                             filter(AttnSummary.month==form.month.data).\
                                             filter(Team.name==team.name).all()

                summary.append(result)

            return render_template('data.html', type='attn_summary', query='team', form=form, 
                                    summary=summary)
   
    return render_template('forms.html', type='attnquery', user='all', form=form)


#Query attendance data for logged in user and prepare summary report of 
#absence and late attendance
@attendance.route('/attendance/query/self', methods=['GET', 'POST'])
@login_required
def query_self():
    form = Attnqueryself()

    if form.validate_on_submit():
        month = month_name_num(form.month.data)

        employee = Employee.query.filter_by(username=session['username']).first()
            
        if employee:
            attendance = db.session.query(Attendance.date, Attendance.in_time, Attendance.out_time, ApprLeaveAttn.approved).\
                            join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, 
                                                    Attendance.empid==ApprLeaveAttn.empid)).\
                            filter(Attendance.empid==employee.id).\
                            filter(extract('month', Attendance.date)==month).\
                            order_by(Attendance.date).all()
            
            absent = db.session.query(func.count(Attendance.empid).label('count')).\
                        join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, 
                                                    Attendance.empid==ApprLeaveAttn.empid)).\
                        filter(Attendance.empid==employee.id).\
                        filter(extract('month', Attendance.date)==month).\
                        filter(Attendance.in_time == None).\
                        filter(ApprLeaveAttn.approved=='').group_by(Attendance.empid).first()

            late = db.session.query(func.count(Attendance.empid).label('count')).\
                        join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, 
                                                    Attendance.empid==ApprLeaveAttn.empid)).\
                        filter(Attendance.empid==employee.id).\
                        filter(extract('month', Attendance.date)==month).\
                        filter(Attendance.in_time != None).\
                        filter(or_(func.Time(Attendance.in_time) > '09:15:00', 
                                    Attendance.out_time==None, 
                                    func.Time(Attendance.out_time) < '17:45:00')).\
                        filter(ApprLeaveAttn.approved=='').group_by(Attendance.empid).first()
            
            return render_template('data.html', type='attn_details', form=form, attendance=attendance,
                                    absent=absent, late=late, user='self')
        else:
            flash('Username not found', category='error')
            return redirect(url_for('forms.query'))
        
    return render_template('forms.html', type='attnquery', user='all', form=form)

##Attendance approval application##
@attendance.route('/attendance/application', methods=['GET', 'POST'])
@login_required
def application():
    form = Attnapplication()
    employee = Employee.query.filter_by(username=session['username']).first()
    
    if form.validate_on_submit():

        msg = date_check(session['empid'], form.start_date.data, form.end_date.data)
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
        
        application = Applications(empid=employee.id, start_date=form.start_date.data, 
                                    end_date=form.end_date.data, duration=duration, 
                                    type=form.type.data, remark=form.remark.data, 
                                    submission_date=datetime.now(), status='Approval Pending')
        db.session.add(application)
        db.session.commit()
        flash('Attendance application submitted')

        #getting attendance application data from database for the above submitted leave
        application = Applications.query.filter_by(start_date=form.start_date.data, 
                                            end_date=form.end_date.data, type=form.type.data, 
                                            empid=session['empid']).first()
       
        #Getting manager email address of the above employee
        manager = Employee.query.join(Team).filter(Team.name==session['team'], 
                                                    Employee.role=='Manager').first()

        #Getting employee email
        employee = Employee.query.filter_by(id=session['empid']).first()

        if not manager:
            flash('Manager record not found for your team', category='warning')
            return redirect(request.url)
        
        #send mail to all concern
        host = current_app.config['SMTP_HOST']
        port = current_app.config['SMTP_PORT']
        rv = send_mail(host=host, port=port, sender=employee.email, receiver=manager.email, 
                        type='attendance', action='submitted', application=application)
        if rv:
            msg = 'Mail sending failed (' + str(rv) + ')' 
            flash(msg, category='warning')
    else:
        return render_template('forms.html', type='attn_application', form=form)
    
    return redirect(request.url)

## Attendance application cancel function ##
@attendance.route('/attendance/cancel/<id>')
@login_required
def cancel(id):
    attendance = Applications.query.filter_by(id=id).first()

    if not attendance:
        flash('Leave not found', category='error')
    elif attendance.status == 'Approved':
        flash('Cancel request sent to Team Manager', category='message')
    else:
        #delete application   
        db.session.delete(attendance)
        db.session.commit()
        flash('Application cancelled', category='message')
    
    return redirect(url_for('attendance.appl_status_self'))

## Show details of each leave application using application id ##
@attendance.route('/attendance/details/<id>')
@login_required
def appl_details(id):
    rv = user_check(id)
    
    if not rv:
        flash('You are not authorized to see this record', category='error')
        return redirect(url_for('attendance.appl_status_self', type=type))

    details = Applications.query.join(Employee).filter(Applications.id==id).first()
    return render_template('data.html', type='attn_appl_details', details=details)


## Attendance application status for individual ##
@attendance.route('/attendance/application/status/self')
@login_required
def appl_status_self():
    applications = Applications.query.join(Employee).\
                    filter(Employee.username == session['username']).\
                    filter(or_(Applications.type!='Casual', Applications.type!='Medical')).\
                    order_by(Applications.submission_date.desc()).all()
    
    return render_template('data.html', type='attn_appl_status', user='self', applications=applications)
    

#Attendance application status for team 
@attendance.route('/attendance/application/status/team')
@login_required
@manager_required
def appl_status_team():
    teams = Team.query.join(Employee).filter(Employee.username==session['username']).all()
    applications = []
        
    for team in teams:
        applist = Applications.query.select_from(Applications).\
                    join(Team, Applications.empid==Team.empid).\
                    filter(Team.name == team.name).\
                    filter(and_(Applications.type!='Casual', Applications.type!='Medical')).\
                    order_by(Applications.status).all()
        applications += applist

    return render_template('data.html', type='attn_appl_status', user='team', applications=applications)


#Attendance application status for all 
@attendance.route('/attendance/application/status/all')
@login_required
@admin_required
def appl_status_all():
    applications = Applications.query.filter(and_(Applications.type!='Casual', 
                                                Applications.type!='Medical')).\
                                        order_by(Applications.status).all()
    
    return render_template('data.html', type='attn_appl_status', user='all', 
                        applications=applications)

##Attendance application approval##
@attendance.route('/attendance/application/approval')
@login_required
@manager_required
def approval():
    id = request.args.get('id')
    
    if not user_check(id):
        flash('You are not authorizes to perform this action', category='error')
        return redirect(url_for('attendance.appl_status_team'))

    #Approve application and update appr_leave_attn table
    application = Applications.query.filter_by(id=id).first()
    start_date = application.start_date
    end_date = application.end_date
    type = request.args.get('type')
    
    while  start_date <= end_date:
        attendance = ApprLeaveAttn.query.filter(ApprLeaveAttn.empid==application.empid).\
                                        filter(ApprLeaveAttn.date==start_date).first()
        if attendance:
            attendance.approved = type
        
        start_date += timedelta(days=1)
    
    application.status = 'Approved'
    application.approval_date = datetime.now()
    db.session.commit()
    flash('Application approved')
    
    #Send mail to all concerned
    admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
    if not admin:
        current_app.logger.warning('HR email not found')
        msg = 'warning'
    
    manager = Employee.query.filter_by(id=session['empid']).first()
    if not manager:
        current_app.logger.warning('Team Manager email not found')
        msg = 'warning'

    head = Employee.query.filter(Employee.department==application.employee.department, 
                                    Employee.role=='Head').first()
    if not head:
        current_app.logger.warning('Dept. Head email not found')
        msg = 'warning'
    
    if 'msg' in locals():
        flash('Failed to send mail', category='warning')
        return redirect(request.url)

    host = current_app.config['SMTP_HOST']
    port = current_app.config['SMTP_PORT'] 
    
    rv = send_mail(host=host, port=port, sender=manager.email, receiver=admin.email, 
                    cc1=application.employee.email, cc2=head.email, type='attendance', 
                    action='approved', application=application)
    if rv:
        msg = 'Mail sending failed (' + str(rv) + ')' 
        flash(msg, category='warning')
    
    return redirect(url_for('attendance.appl_status_team'))

#Update attn_summary table with attendance summary data for each employee
@attendance.route('/attendance/summary', methods=['GET', 'POST'])
@login_required
@admin_required
def summary():
    form = Attnsummary()

    if form.validate_on_submit():
        month_num = datetime.strptime(form.month.data, '%B').month
        cur_month_num = datetime.now().month
        cur_year = datetime.now().year

        #checking given month number is equal or greater than current month number
        #leave deduction is only permitted for previous month or months before that
        if month_num >= cur_month_num and cur_year >= int(form.year.data):
            flash('You can only prepare attendance summary of previous month or before previous month', category='error')    
            return redirect(url_for('forms.attn_summary'))
            
        summary = AttnSummary.query.filter_by(year=form.year.data).\
                                    filter_by(month=form.month.data).first()

        if summary:
            flash('Summary data already exists for the year and month you submitted', category='error')
            return redirect(url_for('forms.attn_summary'))
    
        employees = Employee.query.all()

        count = 0
        
        for employee in employees:
            absent = db.session.query(func.count(Attendance.empid).label('count')).\
                        join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, 
                                                    Attendance.empid==ApprLeaveAttn.empid)).\
                        filter(Attendance.empid==employee.id).\
                        filter(extract('month', Attendance.date)==month_num).\
                        filter(Attendance.in_time == None).\
                        filter(ApprLeaveAttn.approved=='').first()
                            
            late = db.session.query(func.count(Attendance.empid).label('count')).\
                            join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, 
                                                        Attendance.empid==ApprLeaveAttn.empid)).\
                            filter(Attendance.empid==employee.id).\
                            filter(extract('month', Attendance.date)==month_num).\
                            filter(Attendance.in_time != None).\
                            filter(or_(func.Time(Attendance.in_time) > '09:15:00', 
                                        Attendance.out_time==None, 
                                        func.Time(Attendance.out_time) < '17:45:00')).\
                            filter(ApprLeaveAttn.approved=='').first()

            if absent.count > 0 or late.count > 0:
                attnsummary = AttnSummary(empid=employee.id, year=form.year.data, 
                                        month=form.month.data, absent=absent.count, late=late.count)
                db.session.add(attnsummary)
                count += 1
            
        if count == 0:
            flash('No late or absent in attendance data', category='warning')
        else:
            db.session.commit()
            flash('Attendance summary created', category='message')
    
    return redirect(url_for('forms.attn_summary'))

##Casual and Medical attendance application submission for Fiber##
@attendance.route('/attendance/application/fiber', methods=['GET', 'POST'])
@login_required
@manager_required
def application_fiber():
    
    form = Attnapplfiber()

    if form.validate_on_submit():
        
        employee = Employee.query.filter_by(id=form.empid.data).first()
        if not employee:
            flash('Employee does not exists', category='error')
            return redirect(url_for('forms.attn_fiber'))
        
        msg = date_check(employee.id, form.start_date.data, form.end_date.data)
        if msg:
            flash(msg, category='error')
            return redirect(url_for('forms.attn_fiber'))
            
        #Submit & approve application
        if form.end_date.data: 
            duration = (form.end_date.data - form.start_date.data).days + 1
        else:
            duration = 1
        
        if not form.end_date.data:
            form.end_date.data = form.start_date.data
        
        application = Applications(empid=employee.id, start_date=form.start_date.data, 
                                    end_date=form.end_date.data, duration=duration, 
                                    type=form.type.data, remark=form.remark.data, 
                                    submission_date=datetime.now(), status='Approved')
        db.session.add(application)
        db.session.commit()
        flash('Attendance application submitted')
        
        #Updating appr_leave_attn table
        start_date = form.start_date.data
        end_date = form.end_date.data
        while start_date <= end_date:
            attendance = ApprLeaveAttn.query.filter(ApprLeaveAttn.date==start_date, 
                            ApprLeaveAttn.empid==employee.id).first()
        
            if attendance:
                attendance.approved = form.type.data
            
            start_date += timedelta(days=1)

        db.session.commit()
        
        #Send mail to all concerned with application details
        application = Applications.query.filter_by(empid=employee.id, 
                                                start_date=form.start_date.data, 
                                                end_date=form.end_date.data, type=form.type.data).first()
       
        manager = Employee.query.join(Team).filter(Team.name==session['team'], 
                                                    Employee.role=='Manager').first()

        admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
        if not admin:
            flash('Failed to send mail (HR email not found)', category='warning')
            return redirect(request.url)

        head = Employee.query.filter(Employee.department==manager.department, 
                                        Employee.role=='Head').first()
        if not head:
            flash('Failed to send mail (Department head email not found)', category='warning')
            return redirect(request.url)
        
        host = current_app.config['SMTP_HOST']
        port = current_app.config['SMTP_PORT']
        rv = send_mail(host=host, port=port, sender=manager.email, receiver=admin.email, 
                        cc1=head.email, application=application, type='attendance', action='approved')
        
        if rv:
            msg = 'Mail sending failed (' + str(rv) + ')' 
            flash(msg, category='warning')
    else:
        return render_template('forms.html', type='leave', leave=type, team='fiber', form=form)

    return redirect(url_for('forms.attn_fiber'))