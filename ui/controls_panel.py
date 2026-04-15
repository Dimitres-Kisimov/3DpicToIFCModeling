from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QCheckBox,
    QPushButton,
    QProgressBar,
    QGroupBox,
)


OBJECT_TYPES = [
    ("wall", "Walls"),
    ("column", "Columns"),
    ("beam", "Beams"),
    ("slab", "Slabs"),
    ("window", "Windows"),
    ("door", "Doors"),
    ("furniture", "Furniture"),
]

AI_MODELS = [
    ("openai", "OpenAI (GPT-4o)"),
    ("huggingface", "HuggingFace (Free)"),
    ("moondream", "Moondream (Local/Free)"),
]


class ControlsPanel(QWidget):
    """Panel for selecting AI model, object types, and triggering generation."""

    generate_requested = Signal(str, list)  # (ai_key, [object_type_keys])

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # --- AI Model selector ---
        ai_group = QGroupBox("AI Model")
        ai_layout = QVBoxLayout(ai_group)
        self._ai_combo = QComboBox()
        for key, label in AI_MODELS:
            self._ai_combo.addItem(label, userData=key)
        ai_layout.addWidget(self._ai_combo)
        layout.addWidget(ai_group)

        # --- Object types ---
        obj_group = QGroupBox("Detect Objects")
        obj_layout = QVBoxLayout(obj_group)
        self._type_checks: dict[str, QCheckBox] = {}
        for key, label in OBJECT_TYPES:
            cb = QCheckBox(label)
            cb.setChecked(True)
            self._type_checks[key] = cb
            obj_layout.addWidget(cb)

        # Select all / none
        btn_row = QHBoxLayout()
        select_all = QPushButton("All")
        select_all.setFixedWidth(60)
        select_all.clicked.connect(lambda: self._set_all_checks(True))
        select_none = QPushButton("None")
        select_none.setFixedWidth(60)
        select_none.clicked.connect(lambda: self._set_all_checks(False))
        btn_row.addWidget(select_all)
        btn_row.addWidget(select_none)
        btn_row.addStretch()
        obj_layout.addLayout(btn_row)

        layout.addWidget(obj_group)

        # --- Generate button ---
        self._generate_btn = QPushButton("Generate IFC")
        self._generate_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #0078d4;"
            "  color: white;"
            "  font-weight: bold;"
            "  font-size: 14px;"
            "  padding: 10px;"
            "  border-radius: 4px;"
            "}"
            "QPushButton:hover { background-color: #106ebe; }"
            "QPushButton:disabled { background-color: #555; color: #999; }"
        )
        self._generate_btn.clicked.connect(self._on_generate)
        layout.addWidget(self._generate_btn)

        # --- Progress bar ---
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setVisible(False)
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress)

        # --- Status label ---
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #aaa; font-size: 12px;")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        layout.addStretch()

    @property
    def selected_ai_key(self) -> str:
        return self._ai_combo.currentData()

    @property
    def selected_object_types(self) -> list[str]:
        return [k for k, cb in self._type_checks.items() if cb.isChecked()]

    def _set_all_checks(self, state: bool):
        for cb in self._type_checks.values():
            cb.setChecked(state)

    def _on_generate(self):
        ai_key = self.selected_ai_key
        obj_types = self.selected_object_types
        if not obj_types:
            self._status_label.setText("Select at least one object type.")
            return
        self.generate_requested.emit(ai_key, obj_types)

    def set_busy(self, busy: bool):
        """Toggle progress bar and disable/enable controls."""
        self._generate_btn.setEnabled(not busy)
        self._progress.setVisible(busy)
        if busy:
            self._status_label.setText("Processing...")

    def set_status(self, text: str):
        self._status_label.setText(text)
