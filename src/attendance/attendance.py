from datetime import datetime, timedelta
import os
from re import search
from flask import Blueprint, current_app, request, flash, redirect, render_template, send_from_directory, session, url_for
from sqlalchemy import and_, or_, extract, func, select
import pandas as pd
from attendance.leave import update_apprleaveattn
from .check import check_access, check_application_dates, check_attnsummary
from .mail import send_mail
from .forms import (Addholidays, Attnapplfiber, Attnquerydate, Attnqueryusername, Attnqueryself, Attndataupload, 
                    Attnapplication, Attnsummary, Attnsummaryshow, Dutyschedulecreate, Dutyschedulequery, Dutyshiftcreate)
from .db import *
from .auth import head_required, login_required, admin_required, manager_required, supervisor_required, team_leader_required
from .functions import convert_team_name

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
                empid = int(df.iat[i, 0])
                date = datetime.strptime(df.iat[i, 1], "%m/%d/%Y").date()
                
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

                employee = Employee.query.filter_by(id=empid).first()
                if not employee:
                    error = 'Employee ID' + " '" + str(empid) + "' " + 'does not exists'
                    flash(error, category='error')
                    return redirect(request.url)
                
                record_exists = Attendance.query.filter(Attendance.empid==empid, Attendance.date==date).first()
                if record_exists:
                    error = f"Employee ID '{str(empid)}' & date '{date}' record already exists in database or duplicate data in uploaded file"
                    flash(error, category='error')
                    return redirect(request.url)
                
                application = Applications.query.filter(Applications.empid==empid, Applications.start_date >= date, 
                                Applications.end_date <= date, Applications.status=='Approved').first()
                
                team = Team.query.filter_by(empid=employee.id).first()
                if not team:
                    msg = f'Team name not found for {employee.fullname}'
                    flash(msg, category='error')
                    return redirect(url_for('forms.upload'))

                match = search(r'^Fiber', team.name)
                holiday = Holidays.query.filter_by(date=date).first()
                weekday = date.strftime("%A")

                if application:
                    application_id = application.id
                else:
                    application_id = None

                if holiday:
                    holiday_id = holiday.id
                elif weekday == 'Friday':
                    holiday_id = 0
                elif weekday == 'Saturday':
                    if not match:
                        holiday_id = 1     
                else:
                    holiday_id = None    

                applications_holidays = ApplicationsHolidays(empid=empid, date=date, application_id=application_id, 
                                            holiday_id=holiday_id)
                db.session.add(applications_holidays)

                attendance = Attendance(empid=empid, date=date, in_time=in_time, out_time=out_time)
                db.session.add(attendance)

            db.session.commit()

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
        form = Attnsummaryshow()

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

            if form.result.data == 'Show':
                summary = AttnSummary.query.join(Employee).with_entities(Employee.fullname, AttnSummary.absent, 
                            AttnSummary.late, AttnSummary.early, AttnSummary.extra_absent, AttnSummary.leave_deducted).\
                            filter(AttnSummary.year==form.year.data, AttnSummary.month==form.month.data).all()
        
                if not summary:
                    flash('No record found', category='warning')                  
            
                return render_template('data.html', type='attn_summary', form=form, summary=summary)

            if form.result.data == 'Download':
                file_name = f'Attendance-summary-{form.month.data}-{form.year.data}.csv'
                
                stmt = select(Employee.fullname, AttnSummary.absent, AttnSummary.late, AttnSummary.early, 
                        AttnSummary.extra_absent, AttnSummary.leave_deducted).join(Employee).\
                        where(AttnSummary.year==form.year.data, AttnSummary.month==form.month.data)
                df = pd.read_sql(stmt, db.engine)
                
                df.to_csv(os.path.join(current_app.config['UPLOAD_FOLDER'], file_name))
                
                return render_template('attn_query.html', download='yes', file_name=file_name)

    return render_template('attn_query.html')

@attendance.route('/attendance/files/<name>')
@login_required
@admin_required
def files(name):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], name)

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
                        AttnSummary.late, AttnSummary.early, AttnSummary.extra_absent, AttnSummary.leave_deducted).\
                        filter(Employee.id!=session['empid'], Employee.department==session['department'], 
                        AttnSummary.year==form.year.data, AttnSummary.month==form.month.data).all()

            if len(summary) == 0:
                flash('No record found', category='warning')                  
            
            return render_template('data.html', type='attn_summary', form=form, summary=summary)
   
    return render_template('attn_query.html')

##Query attendance data for team by managers##
@attendance.route('/attendance/query/team/<query_type>', methods=['GET', 'POST'])
@login_required
@team_leader_required
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

            team_leader = Employee.query.join(Team).filter(Team.name==team.name, or_(Employee.role=='Manager', 
                        Employee.role=='Supervisor', Employee.id==session['empid'])).first()
            if not team_leader:
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
                                AttnSummary.extra_absent, AttnSummary.leave_deducted).filter(Employee.id!=session['empid'], 
                                Team.name==team.name, AttnSummary.year==form.year.data, AttnSummary.month==form.month.data).all()
                
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

##Attendance application##
@attendance.route('/attendance/application', methods=['GET', 'POST'])
@login_required
def application():
    form = Attnapplication()
    employee = Employee.query.filter_by(username=session['username']).first()
    
    if form.validate_on_submit():

        msg = check_application_dates(session['empid'], form.start_date.data, form.end_date.data)
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


@attendance.route('/attendance/application/cancel/team/fiber/<id>')
@login_required
@supervisor_required
def cancel_team_fiber(id):
    application = Applications.query.filter_by(id=id).first()

    if not application:
        flash('Application not found', category='error')
        return redirect(url_for(attendance.appl_status_team))

    update_apprleaveattn(application.empid, application.start_date, application.end_date, '')
    
    db.session.delete(application)
    db.session.commit()
    
    flash('Application cancelled', category='message')

    #Send mail to all concerned
    manager = Employee.query.join(Team).filter(Team.name==session['team'], Employee.role=='Manager').first()
    head = Employee.query.filter(Employee.department==session['department'], Employee.role=='Head').first()
    
    if not manager and not head:
        current_app.logger.error(' cancel_team_fiber() - Neither Manager and Head record found for team %s', session['team'])
        flash('Failed to send mail', category='warning')
        return redirect(url_for('attendance.appl_status_team'))

    if not manager:
        receiver_email = head.email
    else:            
        receiver_email = manager.email

    supervisor = Employee.query.filter_by(id=session['empid']).first()
    
    host = current_app.config['SMTP_HOST']
    port = current_app.config['SMTP_PORT']
    rv = send_mail(host=host, port=port, sender=supervisor.email, receiver=receiver_email, type='attendance', 
                    application=application, action='cancelled')
    
    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')
    
    return redirect(url_for('attendance.appl_status_team'))


@attendance.route('/attendance/cancel/team/<application_id>')
@login_required
@manager_required
def cancel_team(application_id):
    application = Applications.query.filter_by(id=application_id).first()
    if not application:
        flash('Attendance application not found', category='error')
        return redirect(url_for('attendance.status_team'))
    
    employee = Employee.query.join(Applications).filter(Applications.id==application_id).first()
    if not employee:
        current_app.logger.warning(' cancel_team(): employee details not found for application:%s', application_id)
        flash('Employee details not found for this application', category='error')
        return redirect(url_for('attendance.status_team'))
    
    team = Team.query.filter_by(empid=application.empid).first()
    if not team:
        flash('Employee team not found for this application', category='error')
        current_app.logger.warning(' cancel_team(): team not found for %s', application.empid)
        return redirect(url_for('attendance.status_team'))

    manager = Employee.query.join(Team).filter(Employee.id==session['empid'], Employee.role=='Manager', 
                Team.name==team.name).first()
    if not manager:
        flash('You are not authorized', category='error')
        current_app.logger.warning(' cancel_team(): not the manager of %s', team.name)
        return redirect(url_for('attendance.status_team'))
    
    if application.status == 'Approved':
        summary = AttnSummary.query.filter_by(year=application.start_date.year, month=application.start_date.strftime("%B"), 
                empid=application.empid).first()
        if summary:
            msg = f'Attendance summary already prepared for {application.start_date.strftime("%B")},{application.start_date.year}' 
            flash(msg, category='error')
            return redirect(url_for('attendance.status_team'))
    
    update_apprleaveattn(employee.id, application.start_date, application.end_date, '')
    db.session.delete(application)
    db.session.commit()
    flash('Application cancelled', category='message')

    #Send mail to all concerned
    email_found = True
    
    if not manager.email:
        current_app.logger.warning(' cancel_team(): Team Manager email not found for %s', employee.username)
        email_found = False

    if application.status == 'Approved':
        admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
        if not admin:
            current_app.logger.warning(' cancel_team(): Admin email not found')
            email_found = False

        head = Employee.query.join(Team).filter(Employee.department==employee.department, Employee.role=='Head').first()
        if not head:
            current_app.logger.warning('Dept. Head email not found')
            email_found = False
    
    if not email_found:
        flash('Failed to send mail', category='warning')
        return redirect(url_for('attendance.status_team'))
    
    if application.status == 'Approved':
        rv = send_mail(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], sender=manager.email, 
                    receiver=admin.email, cc1=head.email, cc2=employee.email, type='attendance', application=application, 
                    action='cancelled')
    
    if application.status == 'Approval Pending':
        rv = send_mail(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], sender=manager.email, 
                    receiver=employee.email, type='attendance', application=application, action='cancelled')

    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')
    
    return redirect(url_for('attendance.appl_status_team'))

@attendance.route('/attendance/cancel/department/<application_id>')
@login_required
@head_required
def cancel_department(application_id):
    application = Applications.query.filter_by(id=application_id).first()
    if not application:
        flash('Attendance application not found', category='error')
        return redirect(url_for('attendance.appl_status_department'))
    
    employee = Employee.query.join(Applications).filter(Applications.id==application_id).first()
    if not employee:
        current_app.logger.warning(' cancel_department(): employee details not found for application:%s', application_id)
        flash('Employee details not found for this application', category='error')
        return redirect(url_for('attendance.appl_status_department'))

    head = Employee.query.filter_by(department=employee.department, id=session['empid'], role='Head').first()
    if not head:
        flash('You are not authorized', category='error')
        current_app.logger.warning(' cancel_department(): not the head of %s', employee.department)
        return redirect(url_for('attendance.appl_status_department'))
    
    if application.status == 'Approved':
        summary = AttnSummary.query.filter_by(year=application.start_date.year, month=application.start_date.strftime("%B"), 
                empid=application.empid).first()
        if summary:
            msg = f'Attendance summary already prepared for {application.start_date.strftime("%B")},{application.start_date.year}' 
            flash(msg, category='error')
            return redirect(url_for('attendance.appl_status_department'))

    update_apprleaveattn(employee.id, application.start_date, application.end_date, '')
    db.session.delete(application)
    db.session.commit()
    flash('Application cancelled', category='message')

    #Send mail to all concerned
    email_found = True

    if employee.role == 'Team':
        manager = Employee.query.join(Team).filter(Team.name==employee.teams[0].name, Employee.role=='Manager').first()
        if not manager.email:
            current_app.logger.warning(' cancel_department(): Team Manager email not found for %s', employee.username)
            email_found = False

    if application.status == 'Approved':
        admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
        if not admin:
            current_app.logger.warning(' cancel_department(): Admin email not found')
            email_found = False

        head = Employee.query.join(Team).filter(Employee.department==employee.department, Employee.role=='Head').first()
        if not head:
            current_app.logger.warning('Dept. Head email not found')
            email_found = False
    
    if not email_found:
        flash('Failed to send mail', category='warning')
        return redirect(url_for('leave.status_department'))
    
    if employee.role != 'Team':
            manager.email = None

    if application.status == 'Approved': 
        rv = send_mail(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], sender=head.email, 
                    receiver=admin.email, cc1=employee.email, cc2=manager.email, type='attendance', application=application, 
                    action='cancelled')
    
    if application.status == 'Approval Pending':
        rv = send_mail(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], sender=head.email, 
                    receiver=employee.email, cc2=manager.email, type='attendance', application=application, action='cancelled')

    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')
    
    return redirect(url_for('attendance.appl_status_department'))

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
@team_leader_required
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
    
    update_apprleaveattn(application.empid, start_date, end_date, type)
    
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

    application = Applications.query.filter_by(id=application_id).first()
    update_apprleaveattn(application.empid, application.start_date, application.end_date, request.args.get('type'))
    
    application.status = 'Approved'
    application.approval_date = datetime.now()
    db.session.commit()
    flash('Application approved')
    
    #Send mail to all concerned
    error = False
    admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
    if not admin:
        current_app.logger.warning('approval_department(): Admin email not found for employee id: %s', application.employee.id)
        error = True
    
    if application.employee.role == 'Team':
        team = Team.query.filter_by(empid=application.empid).first()
        manager = Employee.query.join(Team).filter(Team.name==team.name, Employee.role=='Manager').first()
        if not manager:
            current_app.logger.warning('approval_department(): manager email not found for employee %s', application.employee.username)
            error = True

    if error:
        flash('Failed to send mail', category='warning')
        return redirect(url_for('attendance.appl_status_department'))

    if application.employee.role != 'Team':
        manager.email = None 
    
    rv = send_mail(host=current_app.config['SMTP_HOST'], port=current_app.config['SMTP_PORT'], sender=session['email'], 
            receiver=admin.email, cc1=application.employee.email, cc2=manager.email, application=application, type='attendance', 
            action='approved')
    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')
        return redirect(url_for('attendance.appl_status_department'))

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
            attendances = Attendance.query.join(ApprLeaveAttn, and_(Attendance.empid==ApprLeaveAttn.empid, 
                            Attendance.date==ApprLeaveAttn.date)).filter(Attendance.empid==employee.id, 
                            extract('month', Attendance.date)==month_num, ApprLeaveAttn.approved=='').all()
            absent_count = 0
            late_count = 0
            early_count = 0
            for attendance in attendances:
                duty_schedule = DutySchedule.query.join(DutyShift).filter(DutySchedule.empid==employee.id, 
                                    DutySchedule.date==attendance.date).first()
                if duty_schedule:
                    standard_in_time = duty_schedule.dutyshift.in_time
                    standard_out_time = duty_schedule.dutyshift.out_time
                else:
                    standard_in_time = datetime.strptime(current_app.config['LATE'], '%H:%M:%S').time()
                    standard_out_time = datetime.strptime(current_app.config['EARLY'], '%H:%M:%S').time()

                if attendance.in_time == datetime.strptime('00:00:00', '%H:%M:%S').time():
                    absent_count += 1

                if attendance.in_time > standard_in_time:
                    late_count += 1

                if attendance.out_time < standard_out_time:
                    early_count += 1

            if absent_count > 0 or late_count > 0 or early_count > 0:
                attnsummary = AttnSummary(empid=employee.id, year=form.year.data, month=form.month.data, 
                                absent=absent_count, late=late_count, early=early_count)
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
@supervisor_required
def application_fiber():
    form = Attnapplfiber()

    if form.validate_on_submit():
        employee = Employee.query.filter_by(id=form.empid.data).first()
        if not employee:
            flash('Employee does not exists', category='error')
            return redirect(url_for('forms.attn_fiber'))
        
        msg = check_application_dates(employee.id, form.start_date.data, form.end_date.data)
        if msg:
            flash(msg, category='error')
            return redirect(url_for('forms.attn_fiber'))
            
        if not form.end_date.data:
            form.end_date.data = form.start_date.data

        duration = (form.end_date.data - form.start_date.data).days + 1

        application = Applications(empid=employee.id, start_date=form.start_date.data, end_date=form.end_date.data, 
                        duration=duration, type=form.type.data, remark=form.remark.data, submission_date=datetime.now(), 
                        status='Approved')
        db.session.add(application)
        db.session.commit()
        flash('Attendance application approved', category='message')
        
        update_apprleaveattn(employee.id, form.start_date.data, form.end_date.data, form.type.data)
        db.session.commit()
        
        #Send mail to all concerned 
        application = Applications.query.filter_by(empid=employee.id, 
                                                start_date=form.start_date.data, 
                                                end_date=form.end_date.data, type=form.type.data).first()
       
        manager = Employee.query.join(Team).filter(Team.name==session['team'], 
                                                    Employee.role=='Manager').first()

        admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
        if not admin:
            current_app.logger.warning('application_fiber(): Admin email not found')
            rv = 'failed'

        head = Employee.query.filter(Employee.department==session['department'], Employee.role=='Head').first()
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


@attendance.route('/attendance/duty_schedule/<action>', methods=['GET', 'POST'])
@login_required
@team_leader_required
def duty_schedule(action):
    if action != 'query' and action != 'create' and action != 'delete':
        current_app.logger.error(' duty_shift() - action unknown')
        flash('Unknown action', category='error')
        return render_template('base.html')
   
    if action == 'query':
        form = Dutyschedulequery()
    elif action == 'create':
        form = Dutyschedulecreate()   
    
    team_name = convert_team_name()

    if action == 'query':
        if form.validate_on_submit():
            month = form.month.data
            year = form.year.data
        else:
            month = datetime.now().month
            year = datetime.now().year

        schedule = DutySchedule.query.join(Employee, DutyShift).join(Team, Team.empid==DutySchedule.empid).\
                        filter(DutySchedule.team==team_name, extract('month', DutySchedule.date)==month,
                        extract('year', DutySchedule.date==year)).order_by(DutySchedule.date).all()
        
        return render_template('data.html', type='duty_schedule', schedule=schedule, form=form)

    if action == 'create':
        attnsummary_prepared = check_attnsummary(form.start_date.data, form.end_date.data)
        if attnsummary_prepared:
            msg = 'Cannot create duty schedule (' + attnsummary_prepared + ')'
            flash(msg, category='error')
            return redirect(url_for('forms.duty_schedule', action='create'))
            
        for empid in form.empid.data:
            schedule_exist = DutySchedule.query.filter(DutySchedule.date>=form.start_date.data, 
                                DutySchedule.date<=form.end_date.data, DutySchedule.empid==empid).all()
        if schedule_exist:
            employee = Employee.query.filter_by(id=empid).one()
            msg = f'Schedule exists for {employee.fullname}'
            flash(msg, category='error')
            return redirect(url_for('forms.duty_schedule', action='create'))
    
        while form.start_date.data <= form.end_date.data:
            for empid in form.empid.data:
                schedule = DutySchedule(empid=empid, team=team_name, date=form.start_date.data, 
                            duty_shift=form.duty_shift.data)
                db.session.add(schedule)
            form.start_date.data += timedelta(days=1)

        db.session.commit()

        flash('Duty schedule created', category='message')
        return redirect(url_for('attendance.duty_schedule', action='query'))
    
    if action == 'delete':
        duty_schedule_id = request.args.get('id')

        duty_schedule = DutySchedule.query.filter_by(id=duty_schedule_id).one()

        if not duty_schedule:
            flash('Duty schdule record not found', category='error')
            current_app.logger.error('duty_schedule(action="delete"): Duty schedule id %s not found', duty_schedule_id)
            return redirect(url_for('attendance.duty_schedule', action='query'))
        
        attnsummary_prepared = check_attnsummary(duty_schedule.date)
        if attnsummary_prepared:
            msg = 'Cannot delete duty schedule (' + attnsummary_prepared + ')'
            flash(msg, category='error')
            return redirect(url_for('attendance.duty_schedule', action='query'))
        
        db.session.delete(duty_schedule)
        db.session.commit()
        
        flash('Duty schedule record deleted', category='message')
        return redirect(url_for('attendance.duty_schedule', action='query'))


@attendance.route('/attendance/duty_shift/<action>', methods=['GET', 'POST'])
@login_required
@team_leader_required
def duty_shift(action):
    if action != 'query' and action != 'create' and action != 'delete':
        current_app.logger.error(' duty_shift() - action unknown')
        flash('Unknown action', category='error')
        return render_template('base.html')
    
    team_name = convert_team_name()

    if action == 'query':
        shifts = DutyShift.query.filter(DutyShift.team==team_name).all() 
        return render_template('data.html', type='duty_shift', shifts=shifts)
    
    if action == 'create':
        form = Dutyshiftcreate()
        
        if form.validate_on_submit():
            shift_exist = DutyShift.query.filter(DutyShift.in_time==form.in_time.data, DutyShift.out_time==form.out_time.data, 
                            DutyShift.team==team_name).all()
            if shift_exist:
                flash('Shift exists', category='error')
                return redirect(url_for('forms.duty_shift_create', form=form))
        
            duty_shift = DutyShift(team=team_name, name=form.shift_name.data, in_time=form.in_time.data, 
                            out_time=form.out_time.data)
            db.session.add(duty_shift)
            db.session.commit()

            flash('Duty shift created', category='message')
            return redirect(url_for('attendance.duty_shift', action='query'))

    if action == 'delete':
        shift_id = request.args.get('shift_id')
        
        shift = DutyShift.query.filter_by(id=shift_id).one()
        if not shift:
            flash('Shift not found', category='error')
            current_app.logger.warning('duty_shift(action="delete"): Shift id not found')
            return redirect(url_for('attendance.duty_shift', action='query'))
        
        db.session.delete(shift)
        db.session.commit()

        flash('Duty shift deleted', category='message')
        return redirect(url_for('attendance.duty_shift', action='query'))


@attendance.route('/attendance/holidays/<action>', methods=['GET', 'POST'])
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
                return redirect(url_for('attendance.holidays', action='show'))

            holiday = Holidays.query.filter(Holidays.date>=form.start_date.data, Holidays.date<=form.end_date.data).first()
            if holiday:
                    flash('Date exists in holidays', category='error')
                    return redirect(url_for('attendance.holidays', action='show'))

            while form.start_date.data <= form.end_date.data:
                holiday = Holidays(date=form.start_date.data, name=form.name.data)
                db.session.add(holiday)
                
                attendances = ApprLeaveAttn.query.filter(ApprLeaveAttn.date==form.start_date.data).all()
                if attendances:
                    for attendance in attendances:
                        attendance.approved = form.name.data 
                
                form.start_date.data += timedelta(days=1)
            
            db.session.commit()
            return redirect(url_for('attendance.holidays', action='show'))

        return render_template('forms.html', type='add_holiday', form=form)
    elif action == 'delete':
        holiday_name = request.args.get('holiday_name')
        holidays = Holidays.query.filter_by(name=holiday_name).all()
        for holiday in holidays:
            rv = check_attnsummary(holiday.date)
            if rv:
                flash(rv, category='error')
                return redirect(url_for('attendance.holidays', action='show'))
        
        for holiday in holidays:
            attendances = ApprLeaveAttn.query.filter(ApprLeaveAttn.date==holiday.date).all()
            if attendances:
                for attendance in attendances:
                    attendance.approved = ''
            
            db.session.delete(holiday)
        
        db.session.commit()
    else:
        current_app.logger.error(' holidays(): unknown action %s', action)
        flash('Unknown action', category='error')
    
    return redirect(url_for('attendance.holidays', action='show'))
