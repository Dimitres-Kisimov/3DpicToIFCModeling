from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QWidget,
    QVBoxLayout,
    QStatusBar,
    QMessageBox,
)

from ui.image_panel import ImagePanel
from ui.controls_panel import ControlsPanel
from ui.viewer_widget import ViewerWidget


class _GenerateWorker(QObject):
    """Runs AI analysis + IFC generation in a background thread."""

    finished = Signal(str)    # ifc_path on success
    error = Signal(str)       # error message
    status = Signal(str)      # progress status text

    def __init__(self, ai_key: str, object_types: list[str], image_path: str):
        super().__init__()
        self._ai_key = ai_key
        self._object_types = object_types
        self._image_path = image_path

    def run(self):
        try:
            # 1. Create AI provider
            self.status.emit(f"Loading AI provider: {self._ai_key}...")
            provider = self._create_provider(self._ai_key)

            # 2. Analyze image
            self.status.emit("Analyzing image with AI...")
            result = provider.analyze_image(self._image_path, self._object_types)

            n_elements = len(result.get("elements", []))
            self.status.emit(f"AI detected {n_elements} elements. Generating IFC...")

            # 3. Generate IFC
            from ifc.generator import generate_ifc
            ifc_path = generate_ifc(result)

            self.finished.emit(ifc_path)

        except Exception as e:
            self.error.emit(str(e))

    @staticmethod
    def _create_provider(ai_key: str):
        if ai_key == "openai":
            from ai.openai_provider import OpenAIProvider
            return OpenAIProvider()
        elif ai_key == "huggingface":
            from ai.huggingface_provider import HuggingFaceProvider
            return HuggingFaceProvider()
        elif ai_key == "moondream":
            from ai.moondream_provider import MoondreamProvider
            return MoondreamProvider()
        else:
            raise ValueError(f"Unknown AI provider: {ai_key}")


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Pic → IFC Modeling")
        self.setMinimumSize(1200, 700)

        self._worker: _GenerateWorker | None = None
        self._thread: QThread | None = None

        # --- Status bar ---
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        # --- Central widget with splitter ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side: image panel + controls
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._image_panel = ImagePanel()
        self._controls = ControlsPanel()

        left_layout.addWidget(self._image_panel, stretch=1)
        left_layout.addWidget(self._controls, stretch=0)

        left_widget.setMaximumWidth(380)
        left_widget.setMinimumWidth(300)

        # Right side: xeokit viewer
        self._viewer = ViewerWidget()

        splitter.addWidget(left_widget)
        splitter.addWidget(self._viewer)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([350, 850])

        self.setCentralWidget(splitter)

        # --- Connections ---
        self._controls.generate_requested.connect(self._on_generate)

        # --- Stylesheet ---
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; }
            QWidget { background-color: #252526; color: #cccccc; }
            QGroupBox {
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 16px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QComboBox, QCheckBox, QPushButton, QLabel {
                font-size: 13px;
            }
            QComboBox {
                padding: 4px 8px;
                background: #333;
                border: 1px solid #555;
                border-radius: 3px;
            }
            QComboBox::drop-down { border: none; }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QProgressBar {
                border: 1px solid #555;
                border-radius: 3px;
                background: #333;
                height: 6px;
            }
            QProgressBar::chunk {
                background: #0078d4;
                border-radius: 3px;
            }
            QStatusBar { background: #1e1e1e; color: #888; }
        """)

    def _on_generate(self, ai_key: str, object_types: list[str]):
        """Handle generate request from controls panel."""
        image_path = self._image_panel.image_path
        if not image_path:
            QMessageBox.warning(self, "No Image", "Please upload an image first.")
            return

        self._controls.set_busy(True)
        self.statusBar().showMessage("Starting generation...")

        # Clear previous model
        self._viewer.clear_model()

        # Run in background thread
        self._thread = QThread()
        self._worker = _GenerateWorker(ai_key, object_types, image_path)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_generation_done)
        self._worker.error.connect(self._on_generation_error)
        self._worker.status.connect(self._on_generation_status)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)

        self._thread.start()

    def _on_generation_done(self, ifc_path: str):
        """Called when IFC generation completes successfully."""
        self._controls.set_busy(False)
        self._controls.set_status(f"IFC saved: {ifc_path}")
        self.statusBar().showMessage(f"Model generated: {ifc_path}")

        # Load into viewer
        self._viewer.load_ifc(ifc_path)

    def _on_generation_error(self, error_msg: str):
        """Called when generation fails."""
        self._controls.set_busy(False)
        self._controls.set_status(f"Error: {error_msg}")
        self.statusBar().showMessage("Generation failed.")
        QMessageBox.critical(self, "Generation Error", error_msg)

    def _on_generation_status(self, text: str):
        """Update status during generation."""
        self._controls.set_status(text)
        self.statusBar().showMessage(text)

    def _cleanup_thread(self):
        """Clean up worker and thread after completion."""
        self._worker = None
        self._thread = None
