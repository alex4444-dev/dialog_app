import time
import logging
import re
from ui.dialogs import show_question_dialog
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QTextBrowser, 
                             QLineEdit, QPushButton, QHBoxLayout, QApplication, QMenu, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal, QUrl
from PyQt5.QtGui import QDesktopServices
from ui.styles.main_style import CHAT_WINDOW_STYLE


logger = logging.getLogger('dialog_gui')

class ChatWindow(QWidget):
    message_sent = pyqtSignal(str, str)  # username, message
    unread_count_changed = pyqtSignal(str, int)  # username, unread_count
    call_requested = pyqtSignal(str, str)  # username, call_type
    file_sent = pyqtSignal(str, str)  # username, file_path
    message_deleted = pyqtSignal(str, str)  # username, message_id (опционально)
    clear_all_messages_requested = pyqtSignal(str)  # username

    def __init__(self, username, host="unknown", port=0):
        super().__init__()
        self.username = username
        self.host = host
        self.port = port
        self.message_count = 0
        self.unread_count = 0
        self.is_active_tab = False
        self.message_ids = {}  # номер_строки -> message_id
        self.current_message_id = None
        self.current_message_text = ""  # для отображения в диалоге
        
        
        logger.info(f"ChatWindow.__init__: Создание чата с {username} ({host}:{port})")
        
        self.init_ui()
        self.check_methods()

    def init_ui(self):
        try:
            logger.info(f"ChatWindow.init_ui: Инициализация UI для чата с {self.username}")
            layout = QVBoxLayout()
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(12)
            
            self.title_label = QLabel(f"💬 Чат с {self.username}")
            self.title_label.setAlignment(Qt.AlignCenter)
            self.title_label.setStyleSheet("""
                font-size: 16px; 
                font-weight: bold; 
                color: #2c3e50; 
                padding: 12px;
                background-color: #f8f9fa;
                border-radius: 8px;
            """)
            layout.addWidget(self.title_label)
            
            # Используем QTextBrowser вместо QTextEdit (поддерживает ссылки)
            self.chat_history = QTextBrowser()
            self.chat_history.setObjectName("chat_history")
            self.chat_history.setReadOnly(True)
            # Отключаем автоматическое открытие ссылок (будем обрабатывать вручную)
            self.chat_history.setOpenExternalLinks(False)
            # Подключаем сигнал клика по ссылке
            self.chat_history.anchorClicked.connect(self.on_anchor_clicked)
            # Включаем контекстное меню
            self.chat_history.setContextMenuPolicy(Qt.CustomContextMenu)
            self.chat_history.customContextMenuRequested.connect(self.show_context_menu)
                
            layout.addWidget(self.chat_history)
            
            # Кнопки звонков
            call_buttons_layout = QHBoxLayout()
            self.audio_call_btn = QPushButton("📞 Аудио звонок")
            self.audio_call_btn.setToolTip("Начать аудио звонок")
            self.audio_call_btn.clicked.connect(lambda: self.call_requested.emit(self.username, 'audio'))
            self.video_call_btn = QPushButton("📹 Видео звонок")
            self.video_call_btn.setToolTip("Начать видео звонок")
            self.video_call_btn.clicked.connect(lambda: self.call_requested.emit(self.username, 'video'))
            call_buttons_layout.addWidget(self.audio_call_btn)
            call_buttons_layout.addWidget(self.video_call_btn)
            layout.addLayout(call_buttons_layout)
            
            # Поле ввода и кнопки
            input_layout = QHBoxLayout()
            input_layout.setSpacing(12)
            self.message_input = QLineEdit()
            self.message_input.setObjectName("message_input")
            self.message_input.returnPressed.connect(self.send_message)
            self.message_input.setPlaceholderText("Введите сообщение...")
            
            self.file_btn = QPushButton("📎 Файл")
            self.file_btn.setToolTip("Отправить файл")
            self.file_btn.clicked.connect(self.send_file)
            input_layout.addWidget(self.file_btn)

            self.send_btn = QPushButton("📤 Отправить")
            self.send_btn.setObjectName("send_btn")
            self.send_btn.clicked.connect(self.send_message)
            
            input_layout.addWidget(self.message_input, 4)
            input_layout.addWidget(self.send_btn, 1)
            layout.addLayout(input_layout)
            self.setLayout(layout)
            self.setStyleSheet(CHAT_WINDOW_STYLE)
            self.update_title()
            logger.info(f"ChatWindow.init_ui: UI успешно инициализирован")
        except Exception as e:
            logger.error(f"ChatWindow.init_ui: Ошибка инициализации UI: {e}")
            raise

    def on_anchor_clicked(self, url):
        """Обработка клика по ссылке в истории чата"""
        QDesktopServices.openUrl(url)
        # Подавляем дальнейшую обработку
        self.chat_history.setSource(QUrl())  # сброс

    
    def check_methods(self):
        required_methods = ['send_message', 'add_message', 'set_active', 
                          'mark_as_read', 'update_title']
        for method_name in required_methods:
            if not hasattr(self, method_name):
                logger.error(f"ChatWindow: ОТСУТСТВУЕТ метод {method_name}!")
            else:
                logger.info(f"ChatWindow: метод {method_name} присутствует")

    def set_active(self, active):
        logger.debug(f"ChatWindow.set_active: Установка активности {active} для чата с {self.username}")
        self.is_active_tab = active
        if active and self.unread_count > 0:
            self.mark_as_read()

    def mark_as_read(self):
        if self.unread_count > 0:
            old_unread = self.unread_count
            self.unread_count = 0
            self.update_title()
            self.unread_count_changed.emit(self.username, 0)
            logger.info(f"ChatWindow.mark_as_read: Сброшено {old_unread} непрочитанных сообщений в чате с {self.username}")
        
    def update_title(self):
        unread_text = f" ({self.unread_count})" if self.unread_count > 0 else ""
        new_title = f" Чат с {self.username} {unread_text}"
        self.title_label.setText(new_title)
        logger.debug(f"ChatWindow.update_title: Обновлен заголовок: {new_title}")
        
    def send_message(self):
        try:
            message = self.message_input.text().strip()
            if message:
                logger.info(f"ChatWindow.send_message: Отправка сообщения для {self.username}: '{message}'")
                self.message_sent.emit(self.username, message)
                self.add_message("Вы", message, is_own=True)
                self.message_input.clear()
                logger.info(f"ChatWindow.send_message: Сообщение отправлено успешно")
            else:
                logger.debug("ChatWindow.send_message: Пустое сообщение, отправка отменена")
        except Exception as e:
            logger.error(f"ChatWindow.send_message: Ошибка отправки сообщения: {e}")
            
    def add_message(self, sender, message, is_own=False, message_id=None):
        """
        Добавляет сообщение в историю чата.
        :param sender: имя отправителя
        :param message: текст сообщения
        :param is_own: True, если сообщение отправлено текущим пользователем
        :param message_id: уникальный идентификатор сообщения (из БД или генерируется)
        """
        try:
            logger.info(f"ChatWindow.add_message: Добавление сообщения в чат {self.username}: {sender} - {message}")
            self.message_count += 1

            # Учёт непрочитанных
            if not is_own and not self.is_active_tab:
                self.unread_count += 1
                self.unread_count_changed.emit(self.username, self.unread_count)
                logger.info(f"ChatWindow.add_message: Увеличено количество непрочитанных до {self.unread_count}")

            self.update_title()
            timestamp = time.strftime("%H:%M:%S")

            # Генерация временного ID, если не передан
            if not message_id:
                message_id = f"local_{int(time.time())}_{self.message_count}"

            # Формируем HTML-строку с атрибутом data-msgid
            if is_own:
                full_message = f'<span data-msgid="{message_id}">[{timestamp}] 👤 Вы: {message}</span>'
            else:
                full_message = f'<span data-msgid="{message_id}">[{timestamp}] 👤 {sender}: {message}</span>'

            self.chat_history.append(full_message)

            # Сохраняем message_id для этого блока (индекс последнего добавленного блока)
            block_count = self.chat_history.document().blockCount()
            self.message_ids[block_count - 1] = message_id

            # Прокрутка вниз
            scrollbar = self.chat_history.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            self.chat_history.repaint()
            QApplication.processEvents()

            logger.info(f"ChatWindow.add_message: Сообщение успешно добавлено в чат {self.username}: '{full_message}'")

        except Exception as e:
            logger.error(f"ChatWindow.add_message: Ошибка при добавлении сообщения в чат: {e}")

    def add_system_message(self, message):
        try:
            timestamp = time.strftime("%H:%M:%S")
            system_message = f"[{timestamp}] ⚡ Система: {message}"
            self.chat_history.append(system_message)
            scrollbar = self.chat_history.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            logger.info(f"ChatWindow.add_system_message: Добавлено системное сообщение: {message}")
        except Exception as e:
            logger.error(f"ChatWindow.add_system_message: Ошибка добавления системного сообщения: {e}")

    def rebuild_message_ids(self):
        """Перестраивает словарь message_ids на основе текущего содержимого chat_history."""
        self.message_ids.clear()
        html = self.chat_history.toHtml()
        # Ищем все span с data-msgid
        import re
        pattern = r'<span data-msgid="([^"]+)"'
        matches = re.finditer(pattern, html)
    
   

    def add_file_notification(self, file_name, file_path, is_sent=True):
        """Добавление системного сообщения с кликабельной ссылкой на файл"""
        timestamp = time.strftime("%H:%M:%S")
        # Создаём URL для локального файла
        url = QUrl.fromLocalFile(file_path)
        link = f'<a href="{url.toString()}">{file_name}</a>'
        if is_sent:
            prefix = "📤 Отправлен файл: "
        else:
            prefix = "📥 Получен файл: "
        full_message = f'[{timestamp}] ⚡ Система: {prefix}{link}'
        self.chat_history.append(full_message)
        scrollbar = self.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
            
    def show_context_menu(self, pos):
        cursor = self.chat_history.cursorForPosition(pos)
        if cursor.isNull():
            return

        block = cursor.block()
        block_text = block.text()
        if not block_text.strip():
            return

        block_number = block.blockNumber()
        message_id = self.message_ids.get(block_number)

        if message_id is None:
            return

        self.current_message_id = message_id
        self.current_message_text = block_text.strip()

        menu = QMenu(self)
        delete_single = menu.addAction("Удалить это сообщение")
        delete_all = menu.addAction("🗑️ Удалить все сообщения с этим пользователем")

        action = menu.exec_(self.chat_history.mapToGlobal(pos))

        if action == delete_single:
            self.delete_selected_message()
        elif action == delete_all:
            self.clear_all_messages_requested.emit(self.username)

    def delete_selected_message(self):
        """Удаляет выбранное сообщение (локально)."""
        if not self.current_message_id:
            return
        
        # Подтверждение
        if show_question_dialog(self, "Подтверждение удаления", f"Вы действительно хотите удалить это сообщение?\n\n{self.current_message_text[:100]}..."):
            self.message_deleted.emit(self.username, self.current_message_id)
            self.current_message_id = None

        

    def refresh_history(self):
        """Перезагружает историю сообщений из БД."""
        # Этот метод должен вызываться из главного окна, которое имеет доступ к БД.
        # Можно передать колбэк или сигнал.
        # Пока просто очищаем и добавляем системное сообщение.
        self.chat_history.clear()
        # Здесь должен быть вызов загрузки из БД через главное окно.
        # Для простоты: emit сигнал, чтобы главное окно перезагрузило историю.
        self.message_deleted.emit(self.username, "__refresh__")
    
    def clear_chat(self):
        try:
            self.chat_history.clear()
            self.message_count = 0
            self.unread_count = 0
            self.message_ids.clear()   # очищаем словарь
            self.update_title()
            logger.info(f"ChatWindow.clear_chat: История чата с {self.username} очищена")
        except Exception as e:
            logger.error(f"ChatWindow.clear_chat: Ошибка очистки чата: {e}")

    def send_file(self):
        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите файл для отправки")
        if file_path:
            self.file_sent.emit(self.username, file_path)