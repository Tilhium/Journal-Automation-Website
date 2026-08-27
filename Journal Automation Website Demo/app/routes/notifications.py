from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app.models import Notification, User
from app import db
from datetime import datetime

notifications_bp = Blueprint('notifications', __name__)


# ─────────────────────────────────────────────
# HELPER: Create a notification for a user
# ─────────────────────────────────────────────
def create_notification(user_id, message, link=None):
    """Create and persist a single notification."""
    notif = Notification(user_id=user_id, message=message, link=link)
    db.session.add(notif)
    # Note: caller must commit after calling this


def notify_role(role, message, link=None):
    """Send the same notification to all users with a given role."""
    users = User.query.filter_by(role=role).all()
    for u in users:
        create_notification(u.id, message, link)


# ─────────────────────────────────────────────
# API: Get current user's notifications
# ─────────────────────────────────────────────
@notifications_bp.route('/api/notifications')
@login_required
def get_notifications():
    notifs = (Notification.query
              .filter_by(user_id=current_user.id)
              .order_by(Notification.created_at.desc())
              .limit(30)
              .all())
    data = []
    for n in notifs:
        data.append({
            'id': n.id,
            'message': n.message,
            'link': n.link,
            'is_read': n.is_read,
            'created_at': n.created_at.strftime('%d %b %Y, %H:%M'),
        })
    unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({'notifications': data, 'unread': unread})


# ─────────────────────────────────────────────
# API: Mark a single notification as read
# ─────────────────────────────────────────────
@notifications_bp.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_read(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    if notif.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    notif.is_read = True
    db.session.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────
# API: Mark ALL notifications as read
# ─────────────────────────────────────────────
@notifications_bp.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})
