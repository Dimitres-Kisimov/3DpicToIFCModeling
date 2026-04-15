import os
import shutil

from PySide6.QtCore import QUrl, Slot, QObject, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel

import config


class _ViewerBridge(QObject):
    """Python object exposed to JavaScript via QWebChannel."""

    model_loaded = Signal()

    @Slot(str)
    def on_model_loaded(self, msg):
        self.model_loaded.emit()


class ViewerWidget(QWebEngineView):
    """QWebEngineView wrapping the xeokit 3D viewer."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._bridge = _ViewerBridge(self)

        # Set up QWebChannel for JS <-> Python communication
        channel = QWebChannel(self.page())
        channel.registerObject("backend", self._bridge)
        self.page().setWebChannel(channel)

        self._prepare_viewer_files()
        self._load_viewer()

    def _prepare_viewer_files(self):
        """Copy required JS files into the viewer directory so they can be served."""
        viewer_dir = config.VIEWER_DIR
        os.makedirs(viewer_dir, exist_ok=True)

        # Copy xeokit SDK
        sdk_src = os.path.join(
            os.path.dirname(config.VIEWER_DIR),
            "node_modules", "@xeokit", "xeokit-sdk", "dist", "xeokit-sdk.min.es5.js",
        )
        sdk_dst = os.path.join(viewer_dir, "xeokit-sdk.min.es5.js")
        if os.path.isfile(sdk_src) and not os.path.isfile(sdk_dst):
            shutil.copy2(sdk_src, sdk_dst)

        # Copy web-ifc WASM if available
        wasm_src = os.path.join(
            os.path.dirname(config.VIEWER_DIR),
            "node_modules", "@xeokit", "xeokit-sdk", "dist", "web-ifc.wasm",
        )
        wasm_dst = os.path.join(viewer_dir, "web-ifc.wasm")
        if os.path.isfile(wasm_src) and not os.path.isfile(wasm_dst):
            shutil.copy2(wasm_src, wasm_dst)

        # Copy qwebchannel.js from PySide6
        qwc_dst = os.path.join(viewer_dir, "qwebchannel.js")
        if not os.path.isfile(qwc_dst):
            try:
                from PySide6.QtWebEngineCore import QWebEngineProfile  # noqa: F401
                # qwebchannel.js ships with Qt WebEngine
                qt_path = os.path.dirname(os.path.dirname(
                    os.path.abspath(__import__("PySide6").__file__)
                ))
                # Try common paths
                for candidate in [
                    os.path.join(qt_path, "PySide6", "Qt6", "lib", "QtWebEngine",
                                 "resources", "qtwebchannel", "qwebchannel.js"),
                    os.path.join(qt_path, "PySide6", "resources", "qwebchannel.js"),
                    os.path.join(qt_path, "PySide6", "Qt", "lib", "QtWebEngine",
                                 "resources", "qtwebchannel", "qwebchannel.js"),
                ]:
                    if os.path.isfile(candidate):
                        shutil.copy2(candidate, qwc_dst)
                        break
            except Exception:
                pass

        # If qwebchannel.js still missing, create a minimal stub
        if not os.path.isfile(qwc_dst):
            with open(qwc_dst, "w", encoding="utf-8") as f:
                f.write(
                    "// Minimal QWebChannel stub\n"
                    "var QWebChannel = QWebChannel || function(transport, cb) {\n"
                    "  cb({ objects: { backend: {} } });\n"
                    "};\n"
                )

    def _load_viewer(self):
        """Load the viewer HTML page."""
        viewer_html = os.path.join(config.VIEWER_DIR, "index.html")
        self.setUrl(QUrl.fromLocalFile(viewer_html))

    def load_ifc(self, ifc_path: str):
        """Tell the JS viewer to load an IFC file."""
        # Convert to file:// URL
        url = QUrl.fromLocalFile(ifc_path).toString()
        self.page().runJavaScript(f'window.loadModel("{url}");')

    def clear_model(self):
        """Clear the current model from the viewer."""
        self.page().runJavaScript("window.clearModel();")

    def reset_camera(self):
        """Reset the camera to default position."""
        self.page().runJavaScript("window.resetCamera();")
