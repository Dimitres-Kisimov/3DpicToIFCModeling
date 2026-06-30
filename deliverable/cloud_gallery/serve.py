"""Double-click serve.bat (or run `python serve.py`) to open the interactive 3D comparison
gallery. model-viewer needs a tiny local server (browsers block GLB fetches over file://)."""
import http.server, socketserver, webbrowser, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
PORT = 8900
webbrowser.open(f"http://127.0.0.1:{PORT}/index.html")
print(f"Serving SCS single-image->3D gallery at http://127.0.0.1:{PORT}/index.html")
print("(needs internet once for the model-viewer library; Ctrl+C to stop)")
socketserver.TCPServer(("127.0.0.1", PORT), http.server.SimpleHTTPRequestHandler).serve_forever()
