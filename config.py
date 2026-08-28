import os

class Config:
    # Güvenlik için gizli anahtar (Oturum yönetimi vb. için gerekli)
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'cok-gizli-bir-anahtar-kullan-bunu-degistir'
    
    # Veritabanı bağlantı adresi (Varsayılan olarak SQLite kullanıyoruz)
    # config.py içindeki ilgili satırı bul ve şöyle değiştir:
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///journal.db'
    
    
    # Performans için gereksiz takip mekanizmasını kapatıyoruz
    SQLALCHEMY_TRACK_MODIFICATIONS = False