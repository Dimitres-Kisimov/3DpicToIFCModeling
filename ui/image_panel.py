import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
)


class ImagePanel(QWidget):
    """Panel for uploading and previewing an image."""

    image_loaded = Signal(str)  # emits the file path

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_path: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Title
        title = QLabel("Image")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        # Preview area
        self._preview = QLabel("Drag & drop an image here\nor click Browse")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(280, 200)
        self._preview.setStyleSheet(
            "QLabel {"
            "  border: 2px dashed #555;"
            "  border-radius: 8px;"
            "  background: #1e1e1e;"
            "  color: #888;"
            "  font-size: 13px;"
            "}"
        )
        layout.addWidget(self._preview, stretch=1)

        # Browse button
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        layout.addWidget(browse_btn)

        # Path label
        self._path_label = QLabel("")
        self._path_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self._path_label.setWordWrap(True)
        layout.addWidget(self._path_label)

        # Enable drag & drop
        self.setAcceptDrops(True)

    @property
    def image_path(self) -> str | None:
        return self._image_path

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All Files (*)",
        )
        if path:
            self._set_image(path)

    def _set_image(self, path: str):
        if not os.path.isfile(path):
            return
        self._image_path = path
        pixmap = QPixmap(path)
        scaled = pixmap.scaled(
            self._preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview.setPixmap(scaled)
        self._path_label.setText(os.path.basename(path))
        self.image_loaded.emit(path)

    # -- Drag & drop --
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self._set_image(path)
