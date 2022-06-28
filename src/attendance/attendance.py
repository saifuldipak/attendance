from datetime import date, datetime, timedelta
from unicodedata import category
from flask import Blueprint, current_app, request, flash, redirect, render_template, session, url_for
from sqlalchemy import and_, or_, extract, func
import pandas as pd
from .check import check_access, date_check
from .mail import send_mail
from .forms import (Attnapplfiber, Attnquerydate, Attnqueryusername, Attnqueryself, Attndataupload, 
                    Attnapplication, Attnsummary)
from .db import AttnSummary, Team, db, Employee, Attendance, Applications, ApprLeaveAttn
from .auth import head_required, login_required, admin_required, manager_required

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

##Attendance query menu for all#
@attendance.route('/attendance/query/menu')
@login_required
def query_menu():
    return render_template('attn_query.html')

##Attendance data for all by Admin##
@attendance.route('/attendance/query/all/<query_type>', methods=['GET', 'POST'])
@login_required
@admin_required
def query_all(query_type):

    #creating form object using appropriate class based on type
    if query_type == 'date':
        form = Attnquerydate()
    elif query_type == 'username':
        form = Attnqueryusername()
    elif query_type == 'month':
        form = Attnsummary()

    if form.validate_on_submit():
        
        if query_type == 'date':
            attendance = Attendance.query.join(Employee).join(ApprLeaveAttn, 
                            and_(Attendance.date==ApprLeaveAttn.date, 
                            Attendance.empid==ApprLeaveAttn.empid)).\
                            with_entities(Employee.fullname, Attendance.date, Attendance.in_time, 
                            Attendance.out_time, ApprLeaveAttn.approved).\
                            filter(Attendance.date==form.date.data).all()
            
            if not attendance:
                flash('No record found', category='warning')
                      
            return render_template('data.html', type='attn_details', query='all', 
                                    query_type=query_type, attendance=attendance)          
        
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
                
                if not attendance:
                    flash('No record found', category='warning')

                return render_template('data.html', type='attn_details', query='all', 
                                            fullname=employee.fullname, query_type=query_type, 
                                            form=form, attendance=attendance)
            else:
                flash('Username not found', category='error')
                return redirect(url_for('attendance.query_menu'))
        
        if query_type == 'month':
            summary = AttnSummary.query.join(Employee).filter(AttnSummary.year==form.year.data, 
                        AttnSummary.month==form.month.data).all()
            
            if not summary:
                flash('No record found', category='warning')                  
            
            return render_template('data.html', type='attn_summary', query='all', form=form, 
                                    summary=summary)
   
    return render_template('attn_query.html')

@attendance.route('/attendance/query/department/<query_type>', methods=['GET', 'POST'])
@login_required
@head_required
def query_department(query_type):

    if query_type == 'date':
        form = Attnquerydate()
    elif query_type == 'username':
        form = Attnqueryusername()
    elif query_type == 'month':
        form = Attnsummary()

    if form.validate_on_submit():
        
        if query_type == 'date':
            attendance = Attendance.query.join(Employee).join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, 
                            Attendance.empid==ApprLeaveAttn.empid)).with_entities(Employee.fullname, Attendance.date, 
                            Attendance.in_time, Attendance.out_time, ApprLeaveAttn.approved).\
                            filter(Attendance.date==form.date.data, Employee.department==session['department'], 
                            Employee.id!=session['empid']).all()
            
            if not attendance:
                flash('No record found', category='warning')
                      
            return render_template('data.html', type='attn_details', query_type=query_type, attendance=attendance)          
        
        if query_type == 'username':
            
            employee = Employee.query.filter_by(username=form.username.data).first()
            if not employee:
                flash('Username not found', category='error')
                return redirect(url_for('attendance.query_menu'))

            head = Employee.query.filter(Employee.department==employee.department, Employee.role=='Head').first()
            if not head:
                current_app.logger.warning('query_department(): Trying to query attendance of another department by %s', 
                                            session['username'])
                flash('Username not found', category='error')
                return redirect(url_for('forms.attendance_query', query_type='username'))
            
            month = datetime.strptime(form.month.data, "%B").month

            attendance = db.session.query(Attendance.date, Attendance.in_time, Attendance.out_time, ApprLeaveAttn.approved).\
                        join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, Attendance.empid==ApprLeaveAttn.empid)).\
                        filter(Attendance.empid==employee.id, extract('month', Attendance.date)==month).order_by(Attendance.date).all()
            
            if not attendance:
                flash('No record found', category='warning')

            return render_template('data.html', type='attn_details', query_type=query_type, form=form, attendance=attendance)
        
        if query_type == 'month':
            summary = AttnSummary.query.join(Employee).with_entities(Employee.fullname, AttnSummary.absent, 
                        AttnSummary.late, AttnSummary.early, AttnSummary.late_absent, AttnSummary.deducted).\
                        filter(Employee.id!=session['empid'], Employee.department==session['department'], 
                        AttnSummary.year==form.year.data, AttnSummary.month==form.month.data).all()

            if len(summary) == 0:
                flash('No record found', category='warning')                  
            
            return render_template('data.html', type='attn_summary', form=form, summary=summary)
   
    return render_template('attn_query.html')

##Query attendance data for team by managers##
@attendance.route('/attendance/query/team/<query_type>', methods=['GET', 'POST'])
@login_required
@manager_required
def query_team(query_type):
    
    if query_type == 'date':
        form = Attnquerydate()
    elif query_type == 'username':
        form = Attnqueryusername()
    elif query_type == 'month':
        form = Attnsummary()
    else:
        current_app.logger.error('query_team(): Unknown query_type')
        flash('Query failed', category='error')
        return render_template('attn_query.html')

    if form.validate_on_submit():
        teams = Team.query.filter_by(empid=session['empid']).all()
        
        if not teams:
            current_app.logger.error('query_team(): No team found in Team table for %s', session['username'])
            flash('Query failed', category='error')
            return render_template('base.html')

        if query_type == 'date':
            allteams_attendance = []
            
            for team in teams:
                team_attendance = Attendance.query.join(Employee).join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, 
                            Attendance.empid==ApprLeaveAttn.empid)).join(Team, Attendance.empid==Team.empid).\
                            with_entities(Employee.fullname, Team.name, Attendance.date, Attendance.in_time, Attendance.out_time, 
                            ApprLeaveAttn.approved).filter(Attendance.date==form.date.data, Team.name==team.name, 
                            Attendance.empid!=session['empid']).all()

                allteams_attendance += team_attendance

            attendance = allteams_attendance
        
            if len(attendance) == 0:
                flash('No record found', category='warning')
                      
            return render_template('data.html', type='attn_details', query_type='date', attendance=attendance)
        

        if query_type == 'username':
            team = Team.query.join(Employee).filter(Employee.username==form.username.data).first()

            manager = Employee.query.join(Team).filter(Team.name==team.name, Employee.role=='Manager', 
                        Employee.id==session['empid']).first()
            if not manager:
                current_app.logger.warning('query_team(): Trying to query attendance of another team by %s', session['username'])
                flash('Username not found', category='error')
                return render_template('attn_query.html')

            employee = Employee.query.filter_by(username=form.username.data).first()

            month = datetime.strptime(form.month.data, "%B").month

            attendance = Attendance.query.join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, 
                            Attendance.empid==ApprLeaveAttn.empid)).with_entities(Attendance.date, Attendance.in_time, 
                            Attendance.out_time, ApprLeaveAttn.approved).filter(Attendance.empid==employee.id, 
                            extract('month', Attendance.date)==month).all()
                
            if not attendance:
                    flash('No record found', category='warning')

            return render_template('data.html', type='attn_details', query_type='username', form=form, attendance=attendance)

        if query_type == 'month':
            allteams_summary = []

            for team in teams:
                team_summary = AttnSummary.query.join(Employee).join(Team, AttnSummary.empid==Team.empid).\
                                with_entities(Employee.fullname, AttnSummary.absent, AttnSummary.late, AttnSummary.early, 
                                AttnSummary.deducted).filter(Employee.id!=session['empid'], Team.name==team.name, 
                                AttnSummary.year==form.year.data, AttnSummary.month==form.month.data).all()
                
                allteams_summary += team_summary
            
            summary = allteams_summary
            
            if not summary:
                flash('No record found', category='warning')                  
            
            return render_template('data.html', type='attn_summary', query='team', form=form, summary=summary)

##Attendance query for self##
@attendance.route('/attendance/query/self', methods=['GET', 'POST'])
@login_required
def query_self():
    form = Attnqueryself()
    
    if form.validate_on_submit():
        
        if form.query.data == 'Details':
            attendance = Attendance.query.join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, 
                            Attendance.empid==ApprLeaveAttn.empid)).with_entities(Attendance.date, Attendance.in_time, 
                            Attendance.out_time, ApprLeaveAttn.approved).filter(Attendance.empid==session['empid'], 
                            extract('month', Attendance.date)==int(form.month.data)).order_by(Attendance.date).all()
            
            if not attendance:
                flash('No record found', category='warning')
                return redirect(url_for('forms.attnquery_self'))
            
            return render_template('data.html', type='attn_details_self', attendance=attendance)

        if form.query.data == 'Summary':
            month_obj = datetime.strptime(str(form.month.data), '%m')
            month_name = month_obj.strftime('%B')
            
            summary = AttnSummary.query.filter(AttnSummary.year==form.year.data, 
                        AttnSummary.month==month_name).first()

            if not summary:
                flash('No record found', category='warning')
                return redirect(url_for('forms.attnquery_self'))
            
            return render_template('data.html', type='attn_summary_self', summary=summary)

    else:    
        return render_template('forms.html', type='attnquery_self', form=form)

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

        #Send mail to all concerned
        application = Applications.query.filter_by(start_date=form.start_date.data, end_date=form.end_date.data, 
                        type=form.type.data, empid=session['empid']).first()
       
        if session['role'] == 'Team':
            manager = Employee.query.join(Team).filter(Team.name==session['team'], Employee.role=='Manager').first()
            
            if not manager:
                current_app.logger.warning('Team Manager email not found')
            else:            
                receiver_email = manager.email

        if session['role'] == 'Manager' or not manager:
            head = Employee.query.join(Team).filter(Employee.department==session['department'], Employee.role=='Head').first()
            
            if not head:
                current_app.logger.warning('Dept. Head email not found')
                rv = 'failed'
            else:
                receiver_email = head.email

        if 'rv' in locals():
            flash('Failed to send mail', category='warning')
            return redirect(request.url)

        employee = Employee.query.filter_by(id=session['empid']).first()
        
        host = current_app.config['SMTP_HOST']
        port = current_app.config['SMTP_PORT']
        rv = send_mail(host=host, port=port, sender=employee.email, receiver=receiver_email, type='attendance', 
                        application=application, action='submitted')
        
        if rv:
            current_app.logger.warning(rv)
            flash('Failed to send mail', category='warning')
            return redirect(request.url)
    else:
        return render_template('forms.html', type='attn_application', form=form)
    
    return redirect(request.url)

## Attendance application cancel function ##
@attendance.route('/attendance/cancel/<id>')
@login_required
def cancel(id):
    application = Applications.query.filter_by(id=id).first()

    if not application:
        flash('Application not found', category='error')
    elif application.status == 'Approved':
        flash('Cancel request sent to Team Manager', category='message')
    else:  
        db.session.delete(application)
        db.session.commit()
        flash('Application cancelled', category='message')

        #Send mail to all concerned
        if session['role'] == 'Team':
            manager = Employee.query.join(Team).filter(Team.name==session['team'], Employee.role=='Manager').first()
            
            if not manager:
                current_app.logger.warning('Team Manager email not found')
            else:            
                receiver_email = manager.email

        if session['role'] == 'Manager' or not manager:
            head = Employee.query.join(Team).filter(Employee.department==session['department'], Employee.role=='Head').first()
            
            if not head:
                current_app.logger.warning('Dept. Head email not found')
                rv = 'failed'
            else:
                receiver_email = head.email

        if 'rv' in locals():
            flash('Failed to send mail', category='warning')
            return redirect(request.url)

        employee = Employee.query.filter_by(id=session['empid']).first()
        
        host = current_app.config['SMTP_HOST']
        port = current_app.config['SMTP_PORT']
        rv = send_mail(host=host, port=port, sender=employee.email, receiver=receiver_email, type='attendance', 
                        application=application, action='cancelled')
        
        if rv:
            current_app.logger.warning(rv)
            flash('Failed to send mail', category='warning')
    
    return redirect(url_for('attendance.appl_status_self'))

##Attendance application details##
@attendance.route('/attendance/application/details/<application_id>')
@login_required
def application_details(application_id):
    rv = check_access(application_id)
    
    if not rv:
        flash('You are not authorized to see this record', category='error')
        return redirect(url_for('attendance.appl_status_self', type=type))

    details = Applications.query.join(Employee).filter(Applications.id==application_id).first()
    return render_template('data.html', type='attn_appl_details', details=details)


## Attendance application status for individual ##
@attendance.route('/attendance/application/status/self')
@login_required
def appl_status_self():
    applications = Applications.query.join(Employee).\
                    filter(Employee.username == session['username']).\
                    filter(and_(Applications.type!='Casual', Applications.type!='Medical')).\
                    order_by(Applications.submission_date.desc()).all()
    
    return render_template('data.html', type='attn_appl_status', data='self', applications=applications)
    
#Attendance application status for team 
@attendance.route('/attendance/application/status/team')
@login_required
@manager_required
def appl_status_team():
    teams = Team.query.join(Employee).filter(Employee.username==session['username']).all()
    applications = []
        
    for team in teams:
        applist = Applications.query.select_from(Applications).\
                    join(Team, Applications.empid==Team.empid).filter(Team.name == team.name).\
                    filter(Applications.empid!=session['empid'], and_(Applications.type!='Casual', 
                    Applications.type!='Medical')).order_by(Applications.status).all()
        applications += applist

    return render_template('data.html', type='attn_appl_status', data='team', applications=applications)

#Attendance application status for department
@attendance.route('/attendance/application/status/department')
@login_required
@head_required
def appl_status_department():
    applications = Applications.query.join(Employee).filter(Employee.department==session['department'], 
                    and_(Applications.type!='Casual', Applications.type!='Medical')).\
                    order_by(Applications.status, Applications.submission_date.desc()).all()

    return render_template('data.html', type='attn_appl_status', data='department', applications=applications)

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

##Attendance application approval for Team##
@attendance.route('/attendance/application/approval/team')
@login_required
@manager_required
def approval_team():
    application_id = request.args.get('application_id')
    
    if not check_access(application_id):
        flash('You are not authorizes to perform this action', category='error')
        return redirect(url_for('attendance.appl_status_team'))

    #Approve application and update appr_leave_attn table
    application = Applications.query.filter_by(id=application_id).first()
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

##Attendance application approval for Department##
@attendance.route('/attendance/application/approval/department')
@login_required
@head_required
def approval_department():
    application_id = request.args.get('application_id')
    
    if not check_access(application_id):
        flash('You are not authorizes to perform this action', category='error')
        return redirect(url_for('attendance.appl_status_department'))

    #Approve application and update appr_leave_attn table
    application = Applications.query.filter_by(id=application_id).first()
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

    head = Employee.query.filter_by(department=application.employee.department, role='Head').first()
    if not head:
        current_app.logger.warning('Dept. Head email not found')
        msg = 'warning'
    
    if 'msg' in locals():
        flash('Failed to send mail', category='warning')
        return redirect(url_for('attendance.appl_status_department'))

    host = current_app.config['SMTP_HOST']
    port = current_app.config['SMTP_PORT'] 
    
    rv = send_mail(host=host, port=port, sender=head.email, receiver=admin.email, cc1=application.employee.email, 
                    type='attendance', action='approved', application=application)
    if rv:
        msg = 'Mail sending failed (' + str(rv) + ')' 
        flash(msg, category='warning')
    
    return redirect(url_for('attendance.appl_status_department'))

#Update attn_summary table with attendance summary data for each employee
@attendance.route('/attendance/prepare_summary', methods=['GET', 'POST'])
@login_required
@admin_required
def prepare_summary():
    form = Attnsummary()

    if form.validate_on_submit():
        month_num = datetime.strptime(form.month.data, '%B').month
        cur_month_num = datetime.now().month
        cur_year = datetime.now().year

        if month_num >= cur_month_num and cur_year >= int(form.year.data):
            flash('You can only prepare attendance summary of previous month or before previous month', category='error')    
            return redirect(url_for('forms.attn_prepare_summary'))
            
        summary = AttnSummary.query.filter_by(year=form.year.data, month=form.month.data).first()

        if summary:
            flash('Summary data already exists for the year and month you submitted', category='error')
            return redirect(url_for('forms.attn_prepare_summary'))
    
        employees = Employee.query.all()

        count = 0
        
        for employee in employees:
            absent = db.session.query(func.count(Attendance.empid).label('count')).\
                        join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, 
                        Attendance.empid==ApprLeaveAttn.empid)).filter(Attendance.empid==employee.id, 
                        extract('month', Attendance.date)==month_num, Attendance.in_time=='00:00:00.000000', 
                        ApprLeaveAttn.approved=='').first()
                            
            late = db.session.query(func.count(Attendance.empid).label('count')).\
                    join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, 
                    Attendance.empid==ApprLeaveAttn.empid)).filter(Attendance.empid==employee.id, 
                    extract('month', Attendance.date)==month_num, Attendance.in_time!='00:00:00.000000', 
                    Attendance.in_time > '09:15:00', ApprLeaveAttn.approved=='').first()
                    
            early = db.session.query(func.count(Attendance.empid).label('count')).\
                    join(ApprLeaveAttn, and_(Attendance.date==ApprLeaveAttn.date, 
                    Attendance.empid==ApprLeaveAttn.empid)).filter(Attendance.empid==employee.id, 
                    extract('month', Attendance.date)==month_num, Attendance.in_time!='00:00:00.000000', 
                    or_(Attendance.out_time=='00:00:00.000000', Attendance.out_time < '17:45:00'), 
                    ApprLeaveAttn.approved=='').first()

            if absent.count > 0 or late.count > 0 or early.count > 0:
                attnsummary = AttnSummary(empid=employee.id, year=form.year.data, 
                                month=form.month.data, absent=absent.count, late=late.count, 
                                early=early.count)
                db.session.add(attnsummary)
                count += 1
            
        if count == 0:
            flash('No late or absent in attendance data', category='warning')
        else:
            db.session.commit()
            flash('Attendance summary created', category='message')
    else:
        flash('Form data not correct', category='error')
    
    return redirect(url_for('forms.attn_prepare_summary')) 

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
        flash('Attendance application approved', category='message')
        
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
            current_app.logger.warning('application_fiber(): Admin email not found')
            rv = 'failed'

        head = Employee.query.filter(Employee.department==manager.department, 
                                        Employee.role=='Head').first()
        if not head:
            current_app.logger.warning('application_fiber(): Dept. head email not found')
            rv = 'failed'
        
        if 'rv' in locals():
            flash('Failed to send mail', category='warning')
            return redirect(request.url)
        
        host = current_app.config['SMTP_HOST']
        port = current_app.config['SMTP_PORT']
        rv = send_mail(host=host, port=port, sender=manager.email, receiver=admin.email, 
                        cc1=head.email, application=application, type='attendance', action='approved')
        
        if rv:
            current_app.logger.warning(rv)
            flash('Failed to send mail', category='warning')
            return redirect(request.url)

    else:
        return render_template('forms.html', type='leave', leave=type, team='fiber', form=form)

    return redirect(url_for('forms.attn_fiber'))