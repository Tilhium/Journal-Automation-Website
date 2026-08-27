from flask import Blueprint, render_template, redirect, url_for, flash, request
# pyrefly: ignore [missing-import]
from flask_login import login_required, current_user
from app.models import Paper, User, Review
from app import db
from app.routes.notifications import create_notification, notify_role
from datetime import datetime, timedelta

editor_bp = Blueprint('editor', __name__)

# AUTHORIZATION CHECK (Helper Function)
def has_management_privilege():
    """Allows access only to Editor and Admin roles."""
    return current_user.role in ['Editor', 'Admin']

@editor_bp.route('/editor-dashboard')
@login_required
def dashboard():
    if current_user.role != 'Editor':
        flash('Access denied. You do not have permission to view this page.', 'danger')
        return redirect(url_for('main.index'))

    # Fetch papers requiring immediate action (Submitted, Revision Submitted, Payment Received)
    pending_papers = Paper.query.filter(Paper.status.in_(['Submitted', 'Revision Submitted', 'Payment Received'])).all()
    # Fetch papers that are already in process or archived
    archived_papers = Paper.query.filter(~Paper.status.in_(['Submitted', 'Revision Submitted', 'Payment Received'])).all()

    # Determine the total number of reviewers to format the assignment UI accordingly
    total_reviewers = User.query.filter_by(role='Reviewer').count()

    # Update deadline statuses before rendering
    now = datetime.utcnow()
    pending_reviews = Review.query.filter_by(status='Pending').all()
    changed = False
    for r in pending_reviews:
        if r.deadline and r.deadline < now and r.deadline_status == 'Pending':
            r.deadline_status = 'Late'
            changed = True
    if changed:
        db.session.commit()

    return render_template('dashboard/editor_dashboard.html', 
                           pending=pending_papers, 
                           archived=archived_papers,
                           total_reviewers=total_reviewers)

@editor_bp.route('/assign-reviewer/<int:paper_id>', methods=['GET', 'POST'])
@login_required
def assign_reviewer(paper_id):
    """Manual assignment form — used when there's only 1 reviewer or manual selection is preferred."""
    if current_user.role != 'Editor':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('main.index'))

    paper = Paper.query.get_or_404(paper_id)
    reviewers = User.query.filter_by(role='Reviewer').all()

    # Calculate the number of completed review rounds so far
    completed_rounds = Review.query.filter_by(paper_id=paper.id, status='Completed').count()
    current_round = completed_rounds + 1

    if request.method == 'POST':
        reviewer_id = request.form.get('reviewer_id')
        if not reviewer_id:
            flash('Please select a reviewer.', 'danger')
            return redirect(url_for('editor.assign_reviewer', paper_id=paper.id))
            
        deadline_str = request.form.get('deadline')

        # Parse deadline or default to 7 days from now
        deadline = datetime.utcnow() + timedelta(days=7)
        if deadline_str:
            try:
                deadline = datetime.strptime(str(deadline_str), '%Y-%m-%d')
            except ValueError:
                pass

        new_review = Review()
        new_review.paper_id = paper.id
        new_review.reviewer_id = int(str(reviewer_id))
        new_review.status = 'Pending'
        new_review.deadline = deadline
        new_review.deadline_status = 'Pending'
        paper.status = 'Reviewing'
        db.session.add(new_review)

        # Notifications
        reviewer = User.query.get(int(reviewer_id))
        create_notification(int(reviewer_id),
                            f'A new paper has been assigned to you: "{paper.title}"',
                            link=url_for('reviewer.dashboard'))
        create_notification(paper.author_id,
                            f'Your paper "{paper.title}" is now under review.',
                            link=url_for('author.dashboard'))

        db.session.commit()
        flash(f'Paper "{paper.title}" has been assigned to {reviewer.full_name} for Round {current_round}.', 'success')
        return redirect(url_for('editor.dashboard'))

    return render_template('dashboard/assign_reviewer.html', 
                           paper=paper, 
                           reviewers=reviewers,
                           current_round=current_round,
                           completed_rounds=completed_rounds,
                           default_deadline=(datetime.utcnow() + timedelta(days=7)).strftime('%Y-%m-%d'))


@editor_bp.route('/auto-assign-reviewer/<int:paper_id>')
@login_required
def auto_assign_reviewer(paper_id):
    """Automatic assignment: Selects the reviewer with the least workload when multiple reviewers exist."""
    if current_user.role != 'Editor':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('main.index'))

    paper = Paper.query.get_or_404(paper_id)
    reviewers = User.query.filter_by(role='Reviewer').all()

    if not reviewers:
        flash('No reviewers found in the system.', 'danger')
        return redirect(url_for('editor.dashboard'))

    completed_rounds = Review.query.filter_by(paper_id=paper.id, status='Completed').count()
    current_round = completed_rounds + 1

    # Reviewer IDs already assigned to this paper (to prevent duplicate assignments in the current round)
    already_assigned_ids = [
        r.reviewer_id for r in Review.query.filter_by(paper_id=paper.id, status='Pending').all()
    ]

    # Select the reviewer with the minimum pending workload
    best_reviewer = None
    min_load = float('inf')
    for rv in reviewers:
        if rv.id in already_assigned_ids:
            continue  # Already assigned, skip
        pending_count = Review.query.filter_by(reviewer_id=rv.id, status='Pending').count()
        if pending_count < min_load:
            min_load = pending_count
            best_reviewer = rv

    if best_reviewer is None:
        flash('All reviewers are already assigned to this paper or no suitable reviewer found.', 'warning')
        return redirect(url_for('editor.dashboard'))

    deadline = datetime.utcnow() + timedelta(days=7)
    new_review = Review()
    new_review.paper_id = paper.id
    new_review.reviewer_id = best_reviewer.id
    new_review.status = 'Pending'
    new_review.deadline = deadline
    new_review.deadline_status = 'Pending'
    paper.status = 'Reviewing'
    db.session.add(new_review)

    # Notifications
    create_notification(best_reviewer.id,
                        f'A new paper has been assigned to you: "{paper.title}"',
                        link=url_for('reviewer.dashboard'))
    create_notification(paper.author_id,
                        f'Your paper "{paper.title}" is now under review.',
                        link=url_for('author.dashboard'))

    db.session.commit()

    flash(f'✓ Auto-assigned: "{paper.title}" → {best_reviewer.full_name} (Round {current_round}, {min_load} pending reviews)', 'success')
    return redirect(url_for('editor.dashboard'))


# ─────────────────────────────────────────────
# SET DECISION: Editor sets final decision after review
# ─────────────────────────────────────────────
@editor_bp.route('/set-decision/<int:paper_id>', methods=['POST'])
@login_required
def set_decision(paper_id):
    """Editor sets Accepted / Rejected / Revision Required on a reviewed paper."""
    if current_user.role != 'Editor':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('main.index'))

    paper = Paper.query.get_or_404(paper_id)
    decision = request.form.get('decision')  # 'Accepted', 'Rejected', 'Revision Required'

    allowed = ['Accepted', 'Rejected', 'Revision Required']
    if decision not in allowed:
        flash('Invalid decision.', 'danger')
        return redirect(url_for('editor.dashboard'))

    paper.status = decision
    db.session.commit()

    # Notify author
    msg_map = {
        'Accepted': f'Congratulations! Your paper "{paper.title}" has been accepted.',
        'Rejected': f'We regret to inform you that your paper "{paper.title}" has been rejected.',
        'Revision Required': f'Revision is required for your paper "{paper.title}". Please review the feedback and resubmit.',
    }
    create_notification(paper.author_id, msg_map[decision], link=url_for('author.dashboard'))
    db.session.commit()

    flash(f'Decision "{decision}" has been recorded for "{paper.title}".', 'success')
    return redirect(url_for('editor.dashboard'))


# --- MANAGEMENT ROUTES ---

# 1. TOGGLE VISIBILITY (Hide / Publish Paper)
@editor_bp.route('/toggle-visibility/<int:paper_id>')
@login_required
def toggle_visibility(paper_id):
    if not has_management_privilege():
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('main.archive'))

    paper = Paper.query.get_or_404(paper_id)
    
    # Toggle between Published and Hidden status
    if paper.status == 'Published':
        paper.status = 'Hidden'
        flash(f'"{paper.title}" has been hidden from the archive.', 'warning')
    else:
        paper.status = 'Published'
        flash(f'"{paper.title}" is now live and published.', 'success')
    
    db.session.commit()
    return redirect(url_for('main.archive'))

# 1b. APPROVE PUBLICATION (Editor approves a paid paper for publishing)
@editor_bp.route('/approve-publication/<int:paper_id>')
@login_required
def approve_publication(paper_id):
    if not has_management_privilege():
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('editor.dashboard'))

    paper = Paper.query.get_or_404(paper_id)

    if paper.status != 'Payment Received':
        flash('This paper is not awaiting publication approval.', 'warning')
        return redirect(url_for('editor.dashboard'))

    paper.status = 'Published'

    create_notification(paper.author_id,
                        f'Your paper "{paper.title}" has been published and is now live in the archive!',
                        link=url_for('main.archive'))
    db.session.commit()

    flash(f'"{paper.title}" has been approved and is now live in the archive!', 'success')
    return redirect(url_for('editor.dashboard'))

# 2. EDIT PAPER DETAILS (Title & Abstract)
@editor_bp.route('/edit-paper/<int:paper_id>', methods=['GET', 'POST'])
@login_required
def edit_paper(paper_id):
    if not has_management_privilege():
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('main.archive'))

    paper = Paper.query.get_or_404(paper_id)

    if request.method == 'POST':
        # Retrieve updated data from form
        paper.title = request.form.get('title')
        paper.abstract = request.form.get('abstract')
        
        db.session.commit()
        flash('Paper details have been updated successfully.', 'success')
        return redirect(url_for('main.archive'))

    return render_template('dashboard/edit_paper.html', paper=paper)