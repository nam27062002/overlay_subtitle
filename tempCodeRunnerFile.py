import sys
import os
from PyQt6.QtWidgets import QApplication
from src.models.database import init_db
from src.ui.main_window import MainWindow

if __name__ == "__main__":
    # Tạo thư mục downloads nếu chưa tồn tại
    os.makedirs(os.path.join("src", "downloads"), exist_ok=True)
    
    # Khởi tạo cơ sở dữ liệu
    init_db()
    
    # Tạo ứng dụng
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Tạo và hiển thị cửa sổ chính
    window = MainWindow()
    window.show()
    
    # Thực thi ứng dụng
    sys.exit(app.exec()) 