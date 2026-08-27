from flask import Blueprint, render_template, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app import db
from app.routes.notifications import create_notification

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # Redirect if the user is already logged in
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')

        # Check if the email is already registered in the system
        user_exists = User.query.filter_by(email=email).first()
        if user_exists:
            flash('This email address is already in use.', 'danger')
            return redirect(url_for('auth.register'))

        # Create new user and hash the password for security
        hashed_password = generate_password_hash(password)
        new_user = User(
            full_name=full_name, 
            email=email, 
            password_hash=hashed_password, 
            role=role
        )
        
        db.session.add(new_user)
        db.session.commit()

        # Notify all admins about the new registration
        admins = User.query.filter_by(role='Admin').all()
        for admin in admins:
            create_notification(
                admin.id,
                f'New user registered: {full_name} ({role}).',
                link=url_for('admin.dashboard')
            )
        db.session.commit()

        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Redirect if the user is already logged in
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(email=email).first()

        # Validate user existence and password hash
        if not user or not check_password_hash(user.password_hash, password):
            flash('Login failed. Please check your email and password.', 'danger')
            return redirect(url_for('auth.login'))

        # Process successful login
        login_user(user, remember=remember)
        return redirect(url_for('main.index'))

    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))