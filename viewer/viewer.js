import { Viewer } from "./xeokit-sdk.min.es5.js";

// ---------------------------------------------------------------------------
// xeokit Viewer setup
// ---------------------------------------------------------------------------
const viewer = new Viewer({
    canvasId: "viewer-canvas",
    transparent: true,
});

// Camera defaults
viewer.camera.eye = [15, 15, 15];
viewer.camera.look = [0, 0, 0];
viewer.camera.up = [0, 0, 1];

const statusEl = document.getElementById("status");
const emptyMsg = document.getElementById("empty-msg");

let currentModel = null;

// ---------------------------------------------------------------------------
// Public API called from Python via QWebChannel / runJavaScript
// ---------------------------------------------------------------------------

/**
 * Load an IFC file into the viewer using SceneModel + mesh fallback.
 * Since WebIFCLoaderPlugin requires web-ifc WASM which is complex in
 * an embedded context, we load IFC via a lightweight approach:
 * Python converts to glTF first, or we load directly.
 *
 * For now we use XKTLoaderPlugin-compatible loading or direct file protocol.
 */
window.loadModel = function (ifcUrl) {
    clearModel();
    statusEl.textContent = "Loading model...";
    emptyMsg.style.display = "none";

    // Dynamically import and use WebIFCLoaderPlugin
    import("./xeokit-sdk.min.es5.js").then((sdk) => {
        if (sdk.WebIFCLoaderPlugin) {
            const webIFCLoader = new sdk.WebIFCLoaderPlugin(viewer, {
                wasmPath: "./",
            });
            currentModel = webIFCLoader.load({
                id: "ifcModel",
                src: ifcUrl,
                edges: true,
            });
            currentModel.on("loaded", () => {
                viewer.cameraFlight.flyTo(currentModel);
                statusEl.textContent = "Model loaded.";
            });
            currentModel.on("error", (msg) => {
                statusEl.textContent = "Error loading model: " + msg;
                console.error("WebIFCLoaderPlugin error:", msg);
                // Fallback: try loading as XKT
                tryXKTLoad(sdk, ifcUrl);
            });
        } else {
            // Fallback: try loading as a generic model
            tryXKTLoad(sdk, ifcUrl);
        }
    });
};

function tryXKTLoad(sdk, url) {
    if (sdk.XKTLoaderPlugin) {
        const xktLoader = new sdk.XKTLoaderPlugin(viewer);
        currentModel = xktLoader.load({
            id: "xktModel",
            src: url,
            edges: true,
        });
        currentModel.on("loaded", () => {
            viewer.cameraFlight.flyTo(currentModel);
            statusEl.textContent = "Model loaded (XKT).";
        });
    }
}

window.clearModel = clearModel;

function clearModel() {
    if (currentModel) {
        currentModel.destroy();
        currentModel = null;
    }
    // Also destroy any models in the scene
    const models = viewer.scene.models;
    for (const id in models) {
        models[id].destroy();
    }
    emptyMsg.style.display = "block";
    statusEl.textContent = "Model cleared.";
}

window.flyToModel = function () {
    if (currentModel) {
        viewer.cameraFlight.flyTo(currentModel);
    }
};

window.resetCamera = function () {
    viewer.camera.eye = [15, 15, 15];
    viewer.camera.look = [0, 0, 0];
    viewer.camera.up = [0, 0, 1];
};

// ---------------------------------------------------------------------------
// QWebChannel bridge (connects to Python backend)
// ---------------------------------------------------------------------------
if (typeof QWebChannel !== "undefined") {
    new QWebChannel(qt.webChannelTransport, function (channel) {
        window.backend = channel.objects.backend;
        statusEl.textContent = "Connected to Python backend.";
    });
}

statusEl.textContent = "Viewer ready.";
