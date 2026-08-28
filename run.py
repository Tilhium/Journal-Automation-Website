print("1 - run.py dosyasi okumaya basladi...")

from app import create_app, db
print("2 - app klasorunden create_app fonksiyonu cagrildi...")

app = create_app()
print("3 - app degiskeni basariyla olusturuldu...")

if __name__ == '__main__':
    print("4 - Sunucu baslatiliyor! Lutfen bekleyin...")
    app.run(debug=True, port=5001)