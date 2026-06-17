#!/data/data/com.termux/files/usr/bin/bash
# Установка зависимостей для rw-ticket.py
# Запусти один раз: bash setup.sh

set -e

echo "=== Установка Python и зависимостей ==="
pkg update -y
pkg install -y python

echo "=== Установка pip-пакетов ==="
pkg install -y poppler
pip install requests PyPDF2 pdf2image

echo "=== Копирую скрипт ==="
cp rw-ticket.py ~/rw-ticket.py

echo "=== Создаю ярлык для домашнего экрана ==="
mkdir -p ~/.shortcuts
cat > ~/.shortcuts/rw-ticket.sh << 'EOF'
#!/data/data/com.termux/files/usr/bin/bash
cd ~
python rw-ticket.py
EOF
chmod +x ~/.shortcuts/rw-ticket.sh

echo ""
echo "=== Готово! ==="
echo ""
echo "Следующий шаг — ярлык на рабочем столе:"
echo "1. Установи приложение 'Termux:Widget' из F-Droid"
echo "2. Долгое нажатие на рабочий стол → виджеты → Termux"
echo "3. Выбери виджет и укажи скрипт 'rw-ticket.sh'"
echo ""
echo "Или просто запускай командой: python ~/rw-ticket.py"
