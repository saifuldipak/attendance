from .db import db, Employee
import click
from flask.cli import with_appcontext

# Drop all tables, create tables and create a default admin user
def reset_db():
    db.drop_all()
    db.create_all()
    
    user = Employee(username = 'admin', 
                    fullname = 'Admin', 
                    password = 'pbkdf2:sha256:260000$qA6YPzWdWhSA16Rk$2b3f13a4fbf0dc7c65f06ff59029566ce57f50b61afd2dc39103665bab4b20ab',
                    department = 'Accounts',
                    designation = 'Manager',
                    role = 'Manager',
                    access = 'Admin'
                    )

    db.session.add(user)
    db.session.commit()

# Flask cli command to initialize database 
@click.command('initdb')
@with_appcontext
def initdb_command():
    reset_db()
    click.echo('Initialized the database.')
    click.echo('User "admin" with Password "admin123" created.')
    click.echo('!!!Please change this password immediately!!!')


def reset(app):
    #app.teardown_appcontext(close_db)
    app.cli.add_command(initdb_command)