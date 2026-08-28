from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime
import uuid

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum('Author', 'Reviewer', 'Editor', 'Admin'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Cascade deletion: When a user is deleted, their associated papers and reviews are also deleted.
    papers = db.relationship('Paper', backref='author', lazy=True, cascade="all, delete-orphan")
    reviews = db.relationship('Review', backref='reviewer', lazy=True, cascade="all, delete-orphan")

class Paper(db.Model):
    __tablename__ = 'papers'
    
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    abstract = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=False, default='General')
    content = db.Column(db.Text, nullable=True)  # Rich HTML content for paper detail page
    status = db.Column(db.String(50), default='Submitted') 
    view_count = db.Column(db.Integer, default=0)
    fee_amount = db.Column(db.Numeric(10, 2), default=0.00)
    is_paid = db.Column(db.Boolean, default=False)
    similarity_score = db.Column(db.Float, nullable=True)  # Plagiarism similarity %
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Cascade deletion: Deleting a paper clears all its child records (versions, reviews, views, images, payments).
    versions = db.relationship('PaperVersion', backref='paper', lazy=True, cascade="all, delete-orphan")
    reviews = db.relationship('Review', backref='paper', lazy=True, cascade="all, delete-orphan")
    views = db.relationship('PaperView', backref='paper', lazy=True, cascade="all, delete-orphan")
    images = db.relationship('PaperImage', backref='paper', lazy=True, cascade="all, delete-orphan")

class PaperVersion(db.Model):
    __tablename__ = 'paper_versions'
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('papers.id'), nullable=False)
    version_number = db.Column(db.Integer, nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('papers.id'), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='Pending')
    evaluation_report = db.Column(db.Text, nullable=True)
    recommendation = db.Column(db.String(20), nullable=True)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    deadline = db.Column(db.DateTime, nullable=True)          # Reviewer deadline
    deadline_status = db.Column(db.String(20), default='Pending')  # Pending/Completed/Late
    comment = db.Column(db.Text)
    report_path = db.Column(db.String(255))

    # Cascade deletion: Deleting a review removes all associated PDF annotations.
    annotations = db.relationship('Annotation', backref='review', lazy=True, cascade="all, delete-orphan")

class Annotation(db.Model):
    __tablename__ = 'annotations'
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('reviews.id'), nullable=False)
    paper_id = db.Column(db.Integer, db.ForeignKey('papers.id'), nullable=False)
    page_number = db.Column(db.Integer, nullable=False)
    x = db.Column(db.Float, nullable=False)
    y = db.Column(db.Float, nullable=False)
    width = db.Column(db.Float, nullable=False)
    height = db.Column(db.Float, nullable=False)
    comment = db.Column(db.Text, nullable=False)
    severity = db.Column(db.Enum('Critical', 'Major', 'Minor', 'Suggestion'), default='Major')
    is_resolved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PaperView(db.Model):
    __tablename__ = 'paper_views'
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('papers.id'), nullable=False)
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)

class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('papers.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    card_last_four = db.Column(db.String(4), nullable=False)
    card_holder_name = db.Column(db.String(100), nullable=False)
    transaction_id = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Completed')

    paper = db.relationship('Paper', backref=db.backref('payments', lazy=True, cascade='all, delete-orphan'))

class PaperImage(db.Model):
    __tablename__ = 'paper_images'
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('papers.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(255), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    __tablename__ = 'notifications'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message    = db.Column(db.String(500), nullable=False)
    link       = db.Column(db.String(255), nullable=True)
    is_read    = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user       = db.relationship('User', backref=db.backref('notifications', lazy=True, cascade='all, delete-orphan'))

# Fixed list of academic categories for manuscript submission
PAPER_CATEGORIES = [
    'General',
    'Medicine & Health Sciences',
    'Sports & Exercise Science',
    'Engineering & Technology',
    'Computer Science & AI',
    'Social Sciences',
    'Law & Political Science',
    'Education',
    'Economics & Business',
    'Natural Sciences',
    'Environmental Sciences',
    'Mathematics & Statistics',
    'Arts & Humanities',
    'Psychology',
    'Agriculture & Food Science'
]