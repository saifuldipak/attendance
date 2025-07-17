import os
import sys
from flask import Flask
from datetime import timedelta
import logging
from logging.config import dictConfig
from flask.logging import default_handler
import yaml
from flask_migrate import Migrate
from typing import Dict, Any, Type

def validate_config(app):
    CONFIG_SCHEMA: Dict[str, Type[Any]] = {
        'SECRET_KEY': str,
        'PERMANENT_SESSION_LIFETIME': int,
        'SMTP_HOST': str,
        'SMTP_PORT':str,
        'CASUAL': int,
        'MEDICAL': int,
        'EARNED': int,
        'IN_TIME': str,
        'OUT_TIME': str,
        'IN_GRACE_TIME': int,
        'OUT_GRACE_TIME': int
    }
    for key, expected_type in CONFIG_SCHEMA.items():
        if key not in app.config:
            raise ValueError(f"Missing required configuration key: {key}")
        
        if not isinstance(app.config[key], expected_type):
            raise TypeError(f"Configuration key {key} has wrong type: expected {expected_type}, got {type(app.config[key])}")


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    
    #updating config values
    app.config.from_mapping(
        SECRET_KEY='dev',
        PERMANENT_SESSION_LIFETIME =  timedelta(minutes=5),
        UPLOAD_FOLDER = os.path.join(app.instance_path, 'files'),
        SQLALCHEMY_DATABASE_URI = 'sqlite:////' + os.path.join(app.instance_path, 'db.sqlite'),
        SQLALCHEMY_TRACK_MODIFICATIONS = False,
    )
    
    #create instance directory
    if not os.path.exists(app.instance_path):
        try:
            os.makedirs(app.instance_path)
        except OSError as e:
            app.logger.error(e)

    #create medical leave application attachment directory
    file_dir = os.path.join(app.instance_path, 'files')
    if not os.path.exists(file_dir):
        try:
            os.makedirs(file_dir)
        except OSError as e:
            app.logger.error(e)

    #loading logging config
    logging_cfg = os.path.join(app.instance_path, 'logging.yaml')
    if os.path.exists(logging_cfg):
        dictConfig(yaml.safe_load(open(logging_cfg)))
        for logger in (app.logger, logging.getLogger('sqlalchemy'), logging.getLogger('wtforms')):
            logger.addHandler(default_handler)
    
    #loading configuration from file
    app.config.from_pyfile('config.py', silent=True)
    main_config = os.path.join(app.instance_path, 'config.py')
    if os.path.exists(main_config):
        try:
            validate_config(app)
        except (ValueError, TypeError) as e:
            app.logger.error(f"Configuration error: {e}")
            sys.exit(1) 
        
    #registering sqlalchemy
    from .db import db
    db.init_app(app)
    
    # Initialize Flask-Migrate
    Migrate(app, db)

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

    from .application import application as application_blueprint
    app.register_blueprint(application_blueprint)

    from .help import help as help_blueprint
    app.register_blueprint(help_blueprint)

    return app