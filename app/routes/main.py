from flask import Blueprint, render_template, send_from_directory, request
from flask_login import current_user
from app.models import Paper, User, Review, db, PaperView, PAPER_CATEGORIES
from datetime import datetime, timedelta
from sqlalchemy import func
import os

# Creating the 'main' Blueprint
main_bp = Blueprint('main', __name__)

# --- CACHE CONTROL (FOR SECURITY) ---
@main_bp.after_app_request
def add_header(response):
    """
    Prevents the 'Back' button from showing stale data after logout.
    """
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# 1. HOME PAGE
@main_bp.route('/')
def index():
    # Statistics for the homepage
    total_papers = Paper.query.filter_by(status='Published').count()
    total_authors = User.query.filter_by(role='Author').count()
    total_reviews = Review.query.filter_by(status='Completed').count()
    total_reviewers = User.query.filter_by(role='Reviewer').count()
    
    # Recent published papers (latest 4)
    recent_papers = Paper.query.filter_by(status='Published') \
        .order_by(Paper.updated_at.desc()).limit(4).all()
    
    return render_template('index.html', 
                           total_papers=total_papers,
                           total_authors=total_authors,
                           total_reviews=total_reviews,
                           total_reviewers=total_reviewers,
                           recent_papers=recent_papers)

# 2. PDF VIEWING AND DUAL COUNTER (Timestamped + General Counter)
@main_bp.route('/view-file/<filename>')
def view_file(filename):
    try:
        # Extracting the paper ID from the filename (e.g., paper_5.pdf)
        paper_id = int(filename.split('_')[1].split('.')[0])
        
        # A. Create a new timestamped click record for weekly trending tracking
        new_view = PaperView(paper_id=paper_id)
        db.session.add(new_view)
        
        # B. Increment the general view count (view_count)
        paper = Paper.query.get(paper_id)
        if paper:
            paper.view_count = (paper.view_count or 0) + 1
            
        db.session.commit()
    except Exception:
        db.session.rollback()  # Rollback changes if an error occurs
        pass 

    return send_from_directory(os.path.join(os.getcwd(), 'uploads'), filename)

# 3. GENERAL ARCHIVE (Sorting, Filtering, Management)
@main_bp.route('/archive')
def archive():
    search_query = request.args.get('q', '')
    sort_by = request.args.get('sort', 'newest')
    category_filter = request.args.get('category', '')
    
    # --- PERMISSION CHECK AND QUERY INITIALIZATION ---
    if current_user.is_authenticated and current_user.role in ['Admin', 'Editor']:
        query = Paper.query.filter(Paper.status.in_(['Published', 'Hidden']))
    else:
        query = Paper.query.filter_by(status='Published')
    
    # Search filter
    if search_query:
        query = query.join(User).filter(
            (Paper.title.ilike(f'%{search_query}%')) | (User.full_name.ilike(f'%{search_query}%'))
        )
    
    # Category filter
    if category_filter:
        query = query.filter(Paper.category == category_filter)
    
    # Sorting
    if sort_by == 'oldest':
        query = query.order_by(Paper.created_at.asc())
    elif sort_by == 'most_viewed':
        query = query.order_by(Paper.view_count.desc())
    elif sort_by == 'alphabetical':
        query = query.order_by(Paper.title.asc())
    else:  # newest (default)
        query = query.order_by(Paper.created_at.desc())
    
    papers = query.all()

    # B. SIDEBAR: Top 5 most viewed papers (All Time)
    most_viewed = Paper.query.filter_by(status='Published').order_by(Paper.view_count.desc()).limit(5).all()

    # C. SIDEBAR: WEEKLY POPULAR QUERY (Last 7 Days)
    one_week_ago = datetime.utcnow() - timedelta(days=7)
    
    weekly_popular = db.session.query(
        Paper, func.count(PaperView.id).label('weekly_clicks')
    ).join(PaperView).filter(
        PaperView.viewed_at >= one_week_ago,
        Paper.status == 'Published'
    ).group_by(Paper.id).order_by(
        func.count(PaperView.id).desc()
    ).limit(3).all()

    # Get distinct categories that have published papers
    active_categories = db.session.query(Paper.category).filter(
        Paper.status.in_(['Published', 'Hidden'])
    ).distinct().all()
    active_categories = sorted([c[0] for c in active_categories if c[0]])

    return render_template(
        'archive.html', 
        papers=papers, 
        most_viewed=most_viewed, 
        weekly_popular=weekly_popular, 
        q=search_query,
        sort_by=sort_by,
        category_filter=category_filter,
        categories=PAPER_CATEGORIES,
        active_categories=active_categories
    )

from sqlalchemy.orm import joinedload

# 4. PAPER DETAIL PAGE (Forum-style)
@main_bp.route('/paper/<int:paper_id>')
def paper_detail(paper_id):
    # Eager load author and images to prevent multiple queries
    paper = Paper.query.options(
        joinedload(Paper.author),
        joinedload(Paper.images)
    ).get_or_404(paper_id)
    
    # Only published papers are publicly visible (or author/admin/editor)
    if paper.status not in ['Published', 'Hidden']:
        if not current_user.is_authenticated:
            flash('This paper is not publicly available.', 'warning')
            return redirect(url_for('main.archive'))
        if current_user.id != paper.author_id and current_user.role not in ['Admin', 'Editor']:
            flash('This paper is not publicly available.', 'warning')
            return redirect(url_for('main.archive'))
    
    # Increment view count
    try:
        new_view = PaperView(paper_id=paper_id)
        db.session.add(new_view)
        paper.view_count = (paper.view_count or 0) + 1
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    return render_template('paper_detail.html', paper=paper)

# 5. SERVE PAPER IMAGES
@main_bp.route('/uploads/paper_images/<filename>')
def serve_paper_image(filename):
    return send_from_directory(os.path.join(os.getcwd(), 'uploads', 'paper_images'), filename)