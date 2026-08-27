from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config import Config

# Initializing extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

# Configuration for unauthorized access redirection
login_manager.login_view = 'auth.login'
login_manager.login_message = "Please log in to view this page."

def create_app(config_class=Config):
    # Initialize the Flask application
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Bind extensions to the app instance
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # --- Blueprint (Route) Registrations ---
    
    # 1. Main Routes (Index, Archive, etc.)
    from app.routes.main import main_bp
    app.register_blueprint(main_bp)

    # 2. Authentication Routes (Login/Register)
    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)

    # 3. Author Module (Manuscript Submission)
    from app.routes.author import author_bp
    app.register_blueprint(author_bp)

    # 4. Editor Module (Reviewer Assignment and Decisions)
    from app.routes.editor import editor_bp
    app.register_blueprint(editor_bp)

    # 5. Reviewer Module (Evaluation Reports)
    from app.routes.reviewer import reviewer_bp
    app.register_blueprint(reviewer_bp)

    # 6. Admin Module (System Management)
    from app.routes.admin import admin_bp
    app.register_blueprint(admin_bp)

    # 7. Notifications Module (In-App Notification System)
    from app.routes.notifications import notifications_bp
    app.register_blueprint(notifications_bp)

    return app 

# Import database models to register them with Flask 
# (Placed at the bottom to prevent circular import errors)
from app import models