import os
from flask import Flask
from datetime import timedelta
import logging
from logging.config import dictConfig
from flask.logging import default_handler
import yaml

def create_app(test_config=None):
    
    #initializing application
    app = Flask(__name__)
    
    #updating config values
    app.config.from_mapping(
        SECRET_KEY='dev',
        PERMANENT_SESSION_LIFETIME =  timedelta(minutes=5),
        UPLOAD_FOLDER = os.path.join(app.instance_path, 'files'),
        SQLALCHEMY_DATABASE_URI = 'sqlite:////' + os.path.join(app.instance_path, 'db.sqlite'),
        SQLALCHEMY_TRACK_MODIFICATIONS = False,
    )

    #loading configuration from .py file
    app.config.from_pyfile(os.path.join(os.environ['VIRTUAL_ENV'], 'config/config.py'))
    
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    
    #loading logging config
    dictConfig(yaml.safe_load(open(os.path.join((os.environ['VIRTUAL_ENV']), 'config/logging.yaml'))))
    for logger in (app.logger, logging.getLogger('sqlalchemy'), logging.getLogger('wtforms')):
            logger.addHandler(default_handler)
    
    #registering sqlalchemy
    from .db import db
    db.init_app(app)
    
    #registering database initialization command
    from . import initdb
    initdb.reset(app)

    #registering different modules as blueprints
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from .employee import employee as employee_blueprint
    app.register_blueprint(employee_blueprint)

    from .leave import leave as leave_blueprint
    app.register_blueprint(leave_blueprint)

    from .forms import forms as forms_blueprint
    app.register_blueprint(forms_blueprint)

    from .attendance import attendance as attendance_blueprint
    app.register_blueprint(attendance_blueprint)

    return app