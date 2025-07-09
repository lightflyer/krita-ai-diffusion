import time
import json
from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)
from PyQt5.QtCore import QUrl, QUrlQuery, pyqtSignal
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from urllib.parse import urlencode

from ..util import client_logger as log
from ..settings import settings


class LoginWidget(QWidget):
    """Embedded widget for user authentication."""
    login_success = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.network_manager = QNetworkAccessManager(self)
        self.network_manager.finished.connect(self.on_login_finished)

        self.create_widgets()
        self.create_layout()

    def create_widgets(self):
        self.header_label = QLabel("AI Image Generation", self)
        self.header_label.setStyleSheet("font-size: 12pt; margin-bottom: 20px;")
        
        self.username_label = QLabel("工号:", self)
        self.username_input = QLineEdit(self)
        self.username_input.setPlaceholderText("请输入")

        self.password_label = QLabel("密码:", self)
        self.password_input = QLineEdit(self)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("请输入")

        self.login_button = QPushButton("登录", self)
        self.login_button.clicked.connect(self.handle_login)
        self.login_button.setDefault(True)
        self.login_button.setMinimumHeight(32)
        
        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #ffc107;") # A yellow/orange for visibility

    def create_layout(self):
        layout = QVBoxLayout(self)
        layout.addWidget(self.header_label)
        layout.addWidget(self.username_label)
        layout.addWidget(self.username_input)
        layout.addWidget(self.password_label)
        layout.addWidget(self.password_input)
        layout.addSpacing(10)
        layout.addWidget(self.login_button)
        layout.addWidget(self.status_label)
        layout.addStretch() # Pushes everything to the top
        self.setLayout(layout)

    def handle_login(self):
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            self.status_label.setText("工号和密码不能为空。")
            return

        self.status_label.setText("正在登录...")
        self.login_button.setEnabled(False)
        
        base_url = "https://xai.anta.com/aimodels-server/public/users/login"
        params = {
            "username": username,
            "password": password,
        }
        url_str = f"{base_url}?{urlencode(params)}"
        url = QUrl(url_str)
        
        request = QNetworkRequest(url)
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        request.setRawHeader(b"accept", b"application/json")

        self.network_manager.get(request)

    def on_login_finished(self, reply: QNetworkReply):
        self.login_button.setEnabled(True)
        
        if reply.error() != QNetworkReply.NetworkError.NoError:
            error_msg = f"登录失败: 工号或者密码错误"
            self.status_label.setText(error_msg)
            log.error(f"Login network error: {reply.errorString()}")
            reply.deleteLater()
            return
            
        response_bytes = reply.readAll()
        try:
            response_json = json.loads(response_bytes.data().decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            error_msg = "错误: 服务器返回无效的JSON响应。"
            self.status_label.setText(error_msg)
            log.error(f"Login JSON parsing error. Response: {response_bytes.data().decode('utf-8', 'ignore')}")
            reply.deleteLater()
            return

        api_code = response_json.get("code")
        
        if api_code == 200:
            data = response_json.get("data")
            if data and "api" in data:
                token = data["api"]
                worker_id = data["worker_id"]
                self.save_token(token, worker_id)
                self.status_label.setText("登录成功！")
                self.login_success.emit() 
            else:
                self.status_label.setText("登录成功，但响应中未找到Token。")
        else:
            error_message = response_json.get("msg", f"登录失败，代码: {api_code}")
            self.status_label.setText(error_message)
        
        reply.deleteLater()

    def save_token(self, token, worker_id):
        # Store token for  day
        settings.user_token = token
        settings.user_id = worker_id
        settings.last_login_time = int(time.time())
        settings.save()
        log.info("New auth token saved to settings file.")

    def reset(self):
        self.username_input.clear()
        self.password_input.clear()
        self.status_label.setText("")
        self.login_button.setEnabled(True)

def check_token() -> bool:
    """Check for a valid, non-expired token from the main settings."""
    token = settings.user_token
    expiration = settings.token_expiration
    last_login_time = settings.last_login_time

    if not token or not last_login_time or last_login_time == 0:
        log.info("No auth token found in settings.")
        return False

    if int(time.time()) > int(last_login_time) + expiration:
        log.info("Auth token has expired.")
        settings.user_token = ""
        settings.token_expiration = 0
        settings.save()
        return False

    log.info("Auth token is valid.")
    return True

