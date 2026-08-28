from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import Review, Paper, Annotation, User
from app import db
from app.routes.notifications import create_notification, notify_role
from datetime import datetime
import os

reviewer_bp = Blueprint('reviewer', __name__)

# 1. REVIEWER DASHBOARD (PENDING AND COMPLETED REVIEWS)
@reviewer_bp.route('/reviewer-dashboard')
@login_required
def dashboard():
    if current_user.role != 'Reviewer':
        flash('Access denied. Only reviewers can access this page.', 'danger')
        return redirect(url_for('main.index'))

    # Pending Reviews: Reviews that have not been submitted yet
    pending_reviews = Review.query.filter_by(reviewer_id=current_user.id, status='Pending').all()

    # Completed Reviews: Reviews that have already been submitted
    completed_reviews = Review.query.filter_by(reviewer_id=current_user.id, status='Completed').all()

    return render_template('dashboard/reviewer_dashboard.html', 
                           pending=pending_reviews, 
                           completed=completed_reviews)

# 2. SUBMIT DECISION AND REVIEW REPORT
@reviewer_bp.route('/submit-review/<int:review_id>', methods=['POST'])
@login_required
def submit_review(review_id):
    review = Review.query.get_or_404(review_id)
    
    # Security check: Ensure the current user is the assigned reviewer
    if review.reviewer_id != current_user.id:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('main.index'))

    # Retrieve data from the form
    decision = request.form.get('decision')
    comment = request.form.get('comment')
    report_file = request.files.get('report_file')

    # 1. Save the written comments
    review.comment = comment
    
    # 2. If a report file is uploaded, save it
    if report_file and report_file.filename != '':
        ext = os.path.splitext(report_file.filename)[1].lower()
        # Naming the report file: report_reviewID.pdf (or .docx)
        report_filename = f"report_{review.id}{ext}"
        
        upload_path = os.path.join(os.getcwd(), 'uploads')
        if not os.path.exists(upload_path):
            os.makedirs(upload_path)
            
        report_file.save(os.path.join(upload_path, report_filename))
        review.report_path = report_filename 

    # 3. Update statuses
    review.status = 'Completed'
    review.completed_at = datetime.utcnow()

    # Update deadline status
    if review.deadline and datetime.utcnow() > review.deadline:
        review.deadline_status = 'Late'
    else:
        review.deadline_status = 'Completed'

    completed_rounds = 1
    paper = Paper.query.get(review.paper_id)
    if paper:
        # Update the paper's status based on the reviewer's decision
        paper.status = decision

        # Calculate which round this was (count after marking current as completed)
        completed_rounds = Review.query.filter_by(paper_id=paper.id, status='Completed').count()

        # Notify all editors
        editors = User.query.filter_by(role='Editor').all()
        for editor in editors:
            create_notification(
                editor.id,
                f'Reviewer submitted feedback for "{paper.title}" (Round {completed_rounds}). Decision: {decision}',
                link=url_for('editor.dashboard')
            )

    db.session.commit()
    
    flash(f'Round {completed_rounds} evaluation submitted. Paper status: {decision}', 'success')
    return redirect(url_for('reviewer.dashboard'))

# ═══════════════════════════════════════════
# ANNOTATION API ENDPOINTS
# ═══════════════════════════════════════════

# 3. SAVE ANNOTATIONS (Batch save from reviewer's annotation session)
@reviewer_bp.route('/api/annotations/<int:review_id>', methods=['POST'])
@login_required
def save_annotations(review_id):
    review = Review.query.get_or_404(review_id)
    
    # Security check
    if review.reviewer_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    annotations_data = data.get('annotations', [])
    
    # Delete existing annotations for this review (replace mode)
    Annotation.query.filter_by(review_id=review_id).delete()
    
    # Create new annotations
    for ann in annotations_data:
        new_ann = Annotation(
            review_id=review_id,
            paper_id=review.paper_id,
            page_number=ann.get('page_number', 1),
            x=ann.get('x', 0),
            y=ann.get('y', 0),
            width=ann.get('width', 0),
            height=ann.get('height', 0),
            comment=ann.get('comment', ''),
            severity=ann.get('severity', 'Major')
        )
        db.session.add(new_ann)
    
    db.session.commit()
    
    return jsonify({'success': True, 'count': len(annotations_data)})

# 4. GET ANNOTATIONS FOR A REVIEW
@reviewer_bp.route('/api/annotations/<int:review_id>', methods=['GET'])
@login_required
def get_annotations(review_id):
    review = Review.query.get_or_404(review_id)
    
    annotations = Annotation.query.filter_by(review_id=review_id).order_by(
        Annotation.page_number, Annotation.y
    ).all()
    
    result = []
    for ann in annotations:
        result.append({
            'id': ann.id,
            'page_number': ann.page_number,
            'x': ann.x,
            'y': ann.y,
            'width': ann.width,
            'height': ann.height,
            'comment': ann.comment,
            'severity': ann.severity,
            'is_resolved': ann.is_resolved
        })
    
    return jsonify({'annotations': result})

# 5. GET ANNOTATIONS FOR A PAPER (for author view)
@reviewer_bp.route('/api/paper-annotations/<int:paper_id>', methods=['GET'])
@login_required
def get_paper_annotations(paper_id):
    paper = Paper.query.get_or_404(paper_id)
    
    # Security: Only the paper author, reviewers, editors, and admins can view
    if current_user.role == 'Author' and paper.author_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    annotations = Annotation.query.filter_by(paper_id=paper_id).order_by(
        Annotation.page_number, Annotation.y
    ).all()
    
    result = []
    for ann in annotations:
        result.append({
            'id': ann.id,
            'page_number': ann.page_number,
            'x': ann.x,
            'y': ann.y,
            'width': ann.width,
            'height': ann.height,
            'comment': ann.comment,
            'severity': ann.severity,
            'is_resolved': ann.is_resolved,
            'reviewer': ann.review.reviewer.full_name if ann.review and ann.review.reviewer else 'Reviewer'
        })
    
    return jsonify({'annotations': result})

    return jsonify({'annotations': result})