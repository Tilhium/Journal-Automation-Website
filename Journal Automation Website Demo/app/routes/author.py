from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models import Paper, PaperVersion, Review, Annotation, Payment, PaperImage, PAPER_CATEGORIES, User
from app import db
from app.routes.notifications import create_notification, notify_role
import os
from werkzeug.utils import secure_filename

author_bp = Blueprint('author', __name__)


# ─────────────────────────────────────────────
# PLAGIARISM HELPER — Jaccard similarity
# ─────────────────────────────────────────────
def _tokenize(text):
    if not text:
        return set()
    return set(text.lower().split())

def check_similarity(new_paper, exclude_id=None):
    """Compare new paper's title+abstract against all existing papers.
    Returns the highest Jaccard similarity score (0.0 – 1.0)."""
    query = Paper.query
    if exclude_id:
        query = query.filter(Paper.id != exclude_id)
    existing = query.all()

    new_text = _tokenize((new_paper.title or '') + ' ' + (new_paper.abstract or ''))
    if not new_text:
        return 0.0

    max_score = 0.0
    for p in existing:
        other_text = _tokenize((p.title or '') + ' ' + (p.abstract or ''))
        if not other_text:
            continue
        score = len(new_text & other_text) / len(new_text | other_text)
        if score > max_score:
            max_score = score
    return round(max_score * 100, 1)  # return as %

@author_bp.route('/submit-paper', methods=['GET', 'POST'])
@login_required
def submit_paper():
    # 1. Role Authorization
    if current_user.role != 'Author':
        flash('Access denied. Only authors can access this page.', 'danger')
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        # 2. Retrieve Form Data
        title = request.form.get('title')
        abstract = request.form.get('abstract')
        category = request.form.get('category', 'General')
        file = request.files.get('paper_file')

        if file and file.filename != '':
            # Validate file extension
            filename = file.filename
            ext = os.path.splitext(filename)[1].lower()

            # Restricting to .pdf and .docx as per academic standards
            if ext in ['.pdf', '.docx']:
                # 3. Create a new Paper record including the abstract
                new_paper = Paper(
                    title=title, 
                    abstract=abstract,
                    category=category,
                    author_id=current_user.id, 
                    status='Submitted'
                )
                db.session.add(new_paper)
                db.session.commit()  # Commit is necessary to generate the ID

                # 4. Standardize the filename (e.g., paper_5.pdf)
                new_filename = f"paper_{new_paper.id}{ext}"
                
                # Ensure the 'uploads' directory exists
                if not os.path.exists('uploads'):
                    os.makedirs('uploads')
                
                file_path = os.path.join('uploads', new_filename)
                file.save(file_path)

                # 5. Create the initial version record (v1)
                version = PaperVersion(
                    paper_id=new_paper.id, 
                    version_number=1, 
                    file_path=new_filename
                )
                db.session.add(version)
                db.session.commit()

                # ── Plagiarism / Similarity Check ──
                sim_score = check_similarity(new_paper, exclude_id=new_paper.id)
                new_paper.similarity_score = sim_score
                db.session.commit()

                # ── Notifications ──
                create_notification(
                    current_user.id,
                    f'Your paper "{new_paper.title}" has been submitted and is now under review.',
                    link=url_for('author.dashboard')
                )
                # Notify editors
                editors = User.query.filter_by(role='Editor').all()
                for editor in editors:
                    msg = f'A new paper has been submitted: "{new_paper.title}"'
                    link = url_for('editor.dashboard')
                    if sim_score > 40:
                        msg += f' ⚠️ High similarity detected ({sim_score}%) — possible duplicate.'
                    create_notification(editor.id, msg, link=link)
                db.session.commit()

                flash('Your manuscript and abstract have been successfully uploaded!', 'success')
                return redirect(url_for('author.dashboard'))
            else:
                flash('Invalid file format. Please upload only .pdf or .docx files.', 'warning')
        else:
            flash('Please select a file to upload.', 'danger')

    return render_template('dashboard/submit_paper.html', categories=PAPER_CATEGORIES)

@author_bp.route('/my-papers')
@login_required
def dashboard():
    if current_user.role != 'Author':
        flash('Access denied. Only authors can access this page.', 'danger')
        return redirect(url_for('main.index'))

    my_papers = Paper.query.filter_by(author_id=current_user.id).all()
    return render_template('dashboard/author_dashboard.html', papers=my_papers)

@author_bp.route('/submit-revision/<int:paper_id>', methods=['GET', 'POST'])
@login_required
def submit_revision(paper_id):
    paper = Paper.query.get_or_404(paper_id)
    
    # Security and Status Validation
    if paper.author_id != current_user.id or paper.status != 'Revision Required':
        flash('Unauthorized action or the manuscript is not in the revision stage.', 'danger')
        return redirect(url_for('author.dashboard'))

    # Fetching the most recent review for the author's reference
    last_review = paper.reviews[-1] if paper.reviews else None

    if request.method == 'POST':
        file = request.files.get('paper_file')
        if file and file.filename != '':
            ext = os.path.splitext(file.filename)[1].lower()
            
            # Determine the next version number
            next_version = len(paper.versions) + 1
            new_filename = f"paper_{paper.id}_v{next_version}{ext}"
            
            file_path = os.path.join('uploads', new_filename)
            file.save(file_path)

            # Create a new version record
            version = PaperVersion(paper_id=paper.id, version_number=next_version, file_path=new_filename)
            db.session.add(version)
            
            # Update the manuscript status to "Revision Submitted"
            paper.status = 'Revision Submitted'

            # Notify editors about the revision submission
            editors = User.query.filter_by(role='Editor').all()
            for editor in editors:
                create_notification(
                    editor.id,
                    f'Author submitted a revised version of "{paper.title}" (v{next_version}).',
                    link=url_for('editor.dashboard')
                )
            db.session.commit()

            flash(f'Version {next_version} of your manuscript has been successfully uploaded!', 'success')
            return redirect(url_for('author.dashboard'))

    return render_template('dashboard/submit_revision.html', paper=paper, review=last_review)

@author_bp.route('/pay-fee/<int:paper_id>', methods=['GET', 'POST'])
@login_required
def pay_fee(paper_id):
    paper = Paper.query.get_or_404(paper_id)

    # Security Validation
    if paper.author_id != current_user.id or paper.status != 'Accepted':
        flash('Payment is not available for this manuscript.', 'danger')
        return redirect(url_for('author.dashboard'))

    # AUTOMATED FEE COMPUTATION
    base_fee = 3000
    version_fee = len(paper.versions) * 150
    total_fee = base_fee + version_fee
    
    paper.fee_amount = total_fee
    db.session.commit()

    if request.method == 'POST':
        card_holder = request.form.get('card_holder', '').strip()
        card_number = request.form.get('card_number', '').replace(' ', '').replace('-', '')
        expiry = request.form.get('expiry', '').strip()
        cvv = request.form.get('cvv', '').strip()

        # Server-side validation
        errors = []
        if not card_holder or len(card_holder) < 3:
            errors.append('Please enter the cardholder name.')
        if not card_number or len(card_number) != 16 or not card_number.isdigit():
            errors.append('Card number must be exactly 16 digits.')
        if not expiry or len(expiry) != 5 or expiry[2] != '/':
            errors.append('Expiry must be in MM/YY format.')
        if not cvv or len(cvv) not in [3, 4] or not cvv.isdigit():
            errors.append('CVV must be 3 or 4 digits.')

        # Luhn check (Bypass for test cards)
        if card_number and len(card_number) == 16 and card_number.isdigit():
            if not card_holder.upper().startswith('TEST'):
                total = 0
                for i, ch in enumerate(reversed(card_number)):
                    n = int(ch)
                    if i % 2 == 1:
                        n *= 2
                        if n > 9:
                            n -= 9
                    total += n
                if total % 10 != 0:
                    errors.append('Invalid card number (failed Luhn check).')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('dashboard/pay_fee.html', paper=paper, total_fee=total_fee)

        # Create Payment record
        payment = Payment(
            paper_id=paper.id,
            amount=total_fee,
            card_last_four=card_number[-4:],
            card_holder_name=card_holder,
            status='Completed'
        )
        db.session.add(payment)

        paper.is_paid = True
        paper.status = 'Payment Received'
        db.session.commit()
        
        flash('Payment received successfully. Your manuscript is now awaiting editor approval for publication!', 'success')
        return render_template('dashboard/pay_success.html', paper=paper, payment=payment, total_fee=total_fee)

    return render_template('dashboard/pay_fee.html', paper=paper, total_fee=total_fee)

# ═══════════════════════════════════════════
# API: Toggle Annotation Resolved Status
# ═══════════════════════════════════════════
@author_bp.route('/api/annotations/<int:ann_id>/resolve', methods=['POST'])
@login_required
def toggle_annotation_resolve(ann_id):
    annotation = Annotation.query.get_or_404(ann_id)
    
    # Security: Ensure current user is the author of the paper
    paper = Paper.query.get(annotation.paper_id)
    if paper.author_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    annotation.is_resolved = not annotation.is_resolved
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'is_resolved': annotation.is_resolved
    })

# ═══════════════════════════════════════════
# REVIEW PAPER — Author views annotations and submits corrections
# ═══════════════════════════════════════════
@author_bp.route('/review-paper/<int:paper_id>', methods=['GET', 'POST'])
@login_required
def review_paper(paper_id):
    paper = Paper.query.get_or_404(paper_id)
    
    # Security: Only the paper's author can view this
    if paper.author_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('author.dashboard'))
    
    # Get all annotations for this paper
    annotations = Annotation.query.filter_by(paper_id=paper_id).order_by(
        Annotation.page_number, Annotation.y
    ).all()
    
    # Get the latest review
    last_review = paper.reviews[-1] if paper.reviews else None
    
    # Get annotation statistics
    total_annotations = len(annotations)
    resolved_count = sum(1 for a in annotations if a.is_resolved)
    
    # Handle revision file upload
    if request.method == 'POST':
        file = request.files.get('paper_file')
        if file and file.filename != '':
            ext = os.path.splitext(file.filename)[1].lower()
            next_version = len(paper.versions) + 1
            new_filename = f"paper_{paper.id}_v{next_version}{ext}"
            
            file_path = os.path.join('uploads', new_filename)
            file.save(file_path)

            version = PaperVersion(paper_id=paper.id, version_number=next_version, file_path=new_filename)
            db.session.add(version)
            paper.status = 'Revision Submitted'
            db.session.commit()

            flash(f'Version {next_version} has been uploaded successfully!', 'success')
            return redirect(url_for('author.dashboard'))
    
    return render_template('dashboard/review_paper.html', 
                           paper=paper,
                           annotations=annotations,
                           review=last_review,
                           total_annotations=total_annotations,
                           resolved_count=resolved_count)

# ═══════════════════════════════════════════
# PAPER DETAIL PAGE — Author writes content for paper landing page
# ═══════════════════════════════════════════
@author_bp.route('/edit-paper-page/<int:paper_id>', methods=['GET', 'POST'])
@login_required
def edit_paper_page(paper_id):
    paper = Paper.query.get_or_404(paper_id)
    
    if paper.author_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('author.dashboard'))
    
    if request.method == 'POST':
        paper.content = request.form.get('content', '')
        db.session.commit()
        flash('Paper page content updated successfully!', 'success')
        return redirect(url_for('main.paper_detail', paper_id=paper.id))
    
    return render_template('dashboard/edit_paper_page.html', paper=paper)

@author_bp.route('/upload-paper-image/<int:paper_id>', methods=['POST'])
@login_required
def upload_paper_image(paper_id):
    paper = Paper.query.get_or_404(paper_id)
    
    if paper.author_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    file = request.files.get('image')
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    allowed = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        return jsonify({'error': 'Invalid image format'}), 400
    
    # Save with unique name
    import uuid
    safe_name = f"paper_{paper_id}_{uuid.uuid4().hex[:8]}{ext}"
    
    upload_dir = os.path.join('uploads', 'paper_images')
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    
    file_path = os.path.join(upload_dir, safe_name)
    file.save(file_path)
    
    # Save to DB
    caption = request.form.get('caption', '')
    img = PaperImage(paper_id=paper_id, filename=safe_name, caption=caption)
    db.session.add(img)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'url': f'/uploads/paper_images/{safe_name}',
        'id': img.id,
        'caption': caption
    })

@author_bp.route('/delete-paper-image/<int:image_id>', methods=['POST'])
@login_required
def delete_paper_image(image_id):
    img = PaperImage.query.get_or_404(image_id)
    paper = Paper.query.get(img.paper_id)
    
    if not paper or paper.author_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Delete file
    file_path = os.path.join('uploads', 'paper_images', img.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    
    db.session.delete(img)
    db.session.commit()
    
    return jsonify({'success': True})