from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash

app = create_app()

test_users = [
    {'email': 'author@test.com', 'name': 'Test Author', 'role': 'Author', 'pass': 'password123'},
    {'email': 'reviewer@test.com', 'name': 'Test Reviewer', 'role': 'Reviewer', 'pass': 'password123'},
    {'email': 'editor@test.com', 'name': 'Test Editor', 'role': 'Editor', 'pass': 'password123'},
    {'email': 'admin@test.com', 'name': 'Test Admin', 'role': 'Admin', 'pass': 'password123'}
]

with app.app_context():
    for user_data in test_users:
        user = User.query.filter_by(email=user_data['email']).first()
        if not user:
            new_user = User(
                email=user_data['email'],
                full_name=user_data['name'],
                role=user_data['role'],
                password_hash=generate_password_hash(user_data['pass'], method='pbkdf2:sha256')
            )
            db.session.add(new_user)
            print(f"Created {user_data['role']} ({user_data['email']})")
        else:
            print(f"User {user_data['email']} already exists.")
    
    db.session.commit()
    print("All test users are ready.")
