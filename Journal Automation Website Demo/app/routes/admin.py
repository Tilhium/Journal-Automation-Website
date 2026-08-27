from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.models import User, Paper
from app import db

admin_bp = Blueprint('admin', __name__)

# --- AUTHORIZATION DECORATOR ---
def admin_required(func):
    """Restricts access to users with the 'Admin' role only."""
    def wrapper(*args, **kwargs):
        if current_user.role != 'Admin':
            flash('Security Access Denied: This area is for system administrators only.', 'danger')
            return redirect(url_for('main.index'))
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

# --- ADMIN DASHBOARD ---
@admin_bp.route('/admin-dashboard')
@login_required
@admin_required
def dashboard():
    users = User.query.all()
    papers = Paper.query.all()
    return render_template('dashboard/admin_dashboard.html', users=users, papers=papers)

# --- USER MANAGEMENT ---

@admin_bp.route('/delete-user/<int:user_id>')
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # Self-deletion prevention
    if user.id == current_user.id:
        flash('Action Blocked: You cannot delete your own administrator account!', 'warning')
        return redirect(url_for('admin.dashboard'))
    
    # The new cascade logic in models.py will automatically remove 
    # all papers, versions, and reviews associated with this user.
    db.session.delete(user)
    db.session.commit()
    
    flash(f'Account for "{user.full_name}" and all associated academic data have been successfully removed.', 'success')
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/change-role/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def change_role(user_id):
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('new_role')
    
    user.role = new_role
    db.session.commit()
    
    flash(f'Role for {user.full_name} has been updated to "{new_role}".', 'info')
    return redirect(url_for('admin.dashboard'))

# --- MANUSCRIPT MANAGEMENT ---

@admin_bp.route('/toggle-visibility/<int:paper_id>')
@login_required
@admin_required
def toggle_visibility(paper_id):
    paper = Paper.query.get_or_404(paper_id)
    
    if paper.status == 'Published':
        paper.status = 'Hidden'
        flash(f'Manuscript "{paper.title}" is now hidden from the public archive.', 'warning')
    else:
        paper.status = 'Published'
        flash(f'Manuscript "{paper.title}" is now live in the public archive.', 'success')
    
    db.session.commit()
    return redirect(url_for('main.archive'))

@admin_bp.route('/edit-paper/<int:paper_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_paper(paper_id):
    paper = Paper.query.get_or_404(paper_id)

    if request.method == 'POST':
        paper.title = request.form.get('title')
        paper.abstract = request.form.get('abstract')
        
        db.session.commit()
        flash('Manuscript data has been successfully updated.', 'success')
        return redirect(url_for('main.archive'))

    return render_template('dashboard/edit_paper.html', paper=paper)