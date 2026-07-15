/**
 * shell — the app conductor. One shared 3D viewport, three workspaces:
 *
 *   Generate object  ·  Build a room  ·  Building        (+ ▶ Demo run)
 *
 * Switching tabs never destroys work: each workspace's models stay loaded and are
 * simply shown/hidden (generator objects = "obj_*", room scene = "room", building
 * = "b-shell"/"bp-*"), and the camera position is remembered per workspace.
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const viewer = () => window.xeokitModule && window.xeokitModule.getViewer && window.xeokitModule.getViewer();

  let activeTab = 'generate';
  const cameras = {};                      // tab -> {eye, look, up}
  const CAMERA_DEFAULTS = {
    room: { eye: [11, 8, 11], look: [4, 0.5, 3], up: [0, 1, 0] },
    building: { eye: [18, 14, 18], look: [6, 1, 6], up: [0, 1, 0] },
  };

  // which models belong to which workspace
  const OWNS = {
    room: (id) => id === 'room',
    building: (id) => id === 'b-shell' || String(id).startsWith('bp-'),
    generate: (id) => id !== 'room' && id !== 'b-shell' && !String(id).startsWith('bp-'),
  };

  // ------------------------------------------------------------------ toasts
  function toast(text, kind = 'ok') {
    const wrap = $('toasts');
    if (!wrap) return;
    const el = document.createElement('div');
    el.className = 'toast' + (kind === 'bad' ? ' bad' : kind === 'info' ? ' info' : '');
    el.textContent = text;
    wrap.appendChild(el);
    setTimeout(() => { el.classList.add('fade'); setTimeout(() => el.remove(), 400); }, 4200);
  }

  // ------------------------------------------------------------------ stage banner
  let bannerTimer = null;
  function banner(text, bad) {
    const el = $('stageMsg');
    if (!el) return;
    el.textContent = text;
    el.className = 'stage-msg' + (bad ? ' bad' : '');
    el.hidden = false;
    clearTimeout(bannerTimer);
    if (!bad) bannerTimer = setTimeout(() => { el.hidden = true; }, 7000);
  }

  // ------------------------------------------------------------------ visibility & camera
  function applyVisibility() {
    const v = viewer();
    if (!v) return;
    const owns = OWNS[activeTab];
    Object.values(v.scene.models).forEach((m) => {
      try { m.visible = owns(m.id); } catch (e) {}
    });
  }

  function saveCamera(tab) {
    const v = viewer();
    if (!v) return;
    cameras[tab] = {
      eye: [...v.camera.eye], look: [...v.camera.look], up: [...v.camera.up],
    };
  }
  function restoreCamera(tab) {
    const v = viewer();
    if (!v) return;
    const cam = cameras[tab] || CAMERA_DEFAULTS[tab];
    if (!cam) return;
    try { v.camera.eye = cam.eye; v.camera.look = cam.look; v.camera.up = cam.up; } catch (e) {}
  }

  // ------------------------------------------------------------------ tab switching
  function setTab(tab) {
    if (tab === activeTab) return;
    saveCamera(activeTab);
    activeTab = tab;

    document.querySelectorAll('#mainTabs .tab').forEach((b) =>
      b.classList.toggle('active', b.dataset.tab === tab));

    $('panel-generate').hidden = tab !== 'generate';
    $('panel-room').hidden = tab !== 'room';
    $('panel-building').hidden = tab !== 'building';
    $('panel-table').hidden = tab === 'generate';
    $('roomExports').style.display = tab === 'room' ? '' : 'none';

    // stage controls per workspace
    const hasBuilding = !!(window.buildingMode && window.buildingMode.hasContent());
    $('rotateBtn').hidden = tab !== 'generate';
    $('planBtn').hidden = tab !== 'room';
    $('bPlanBtn').hidden = tab !== 'building' || !hasBuilding;
    $('wallsBtn').hidden = tab !== 'room';
    $('imgviewBtn').hidden = tab !== 'room' || !$('vfallback').src;
    $('lockBtn').hidden = tab !== 'building' || !hasBuilding;
    $('xrayBtn').hidden = tab !== 'building' || !hasBuilding;
    if (tab !== 'room') {
      $('vfallback').hidden = true;
      if (window.planEditor && window.planEditor.isOpen()) window.planEditor.toggle(false);
    }
    // section planes cut every model in the scene — clear them when leaving,
    // re-apply the floor filter when returning (shell just reset visibility)
    if (tab !== 'building' && window.buildingMode) window.buildingMode.onTabLeave();

    // camera lock only applies while dragging building pieces
    const v = viewer();
    if (v) { try { v.cameraControl.active = tab !== 'building' ? true : v.cameraControl.active; } catch (e) {} }

    // lazy-init workspaces on first visit (keeps startup instant)
    if (tab === 'room' && window.roomBuilder) window.roomBuilder.ensureInit();
    if (tab === 'building' && window.buildingMode) window.buildingMode.ensureInit();

    applyVisibility();
    if (tab === 'building' && window.buildingMode) window.buildingMode.onTabEnter();
    restoreCamera(tab);
  }

  // ------------------------------------------------------------------ fit view (tab-aware)
  function fitCurrent() {
    const v = viewer();
    if (!v) return;
    const target = activeTab === 'room' ? v.scene.models['room']
      : activeTab === 'building' ? v.scene.models['b-shell']
      : null;
    try {
      if (target) v.cameraFlight.flyTo(target);
      else if (window.xeokitModule.fitView) window.xeokitModule.fitView();
    } catch (e) {}
  }

  // ------------------------------------------------------------------ demo run
  async function demoRun() {
    const btn = $('demoRunBtn');
    btn.disabled = true;
    btn.textContent = '⏳ Building demo…';
    toast('▶ Demo run started — a full room is being laid out for you.', 'info');
    try {
      const r = await fetch('/api/room/demo', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
      });
      const d = await r.json();
      if (!d.ok) { toast('Demo failed: ' + (d.error || 'unknown'), 'bad'); return; }
      setTab('room');
      window.roomBuilder.ensureInit();
      window.roomBuilder.applyResult(d, { demo: true });
    } catch (e) {
      toast('Demo failed: ' + e, 'bad');
    } finally {
      btn.disabled = false;
      btn.textContent = '▶ Demo run';
    }
  }

  // ------------------------------------------------------------------ health dot
  async function pollHealth() {
    const dot = $('healthDot');
    try {
      const r = await fetch('/api/health');
      dot.className = 'health-dot ' + (r.ok ? 'ok' : 'bad');
      dot.title = r.ok ? 'server connected' : 'server error';
    } catch (e) {
      dot.className = 'health-dot bad';
      dot.title = 'server unreachable';
    }
  }

  // ------------------------------------------------------------------ wire up
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('#mainTabs .tab').forEach((b) =>
      b.addEventListener('click', () => setTab(b.dataset.tab)));
    // deep-linkable tabs: /#room and /#building open that workspace directly
    const h = (location.hash || '').replace('#', '');
    if (h === 'room' || h === 'building') setTab(h);
    $('demoRunBtn').addEventListener('click', demoRun);
    $('fitViewBtn').addEventListener('click', (e) => {
      // generator tab keeps its own fit behavior from index.js; for room/building
      // fly to that workspace's model instead
      if (activeTab !== 'generate') { e.stopImmediatePropagation(); fitCurrent(); }
    }, true);   // capture so it runs before index.js's listener

    pollHealth();
    setInterval(pollHealth, 30000);

    // success/error helpers from api.js also surface as toasts
    const origSuccess = window.showSuccess, origError = window.showError;
    if (typeof origSuccess === 'function') {
      window.showSuccess = (m) => { toast(m, 'ok'); return origSuccess(m); };
    }
    if (typeof origError === 'function') {
      window.showError = (m, err) => { toast(String(m), 'bad'); return origError(m, err); };
    }
  });

  window.appShell = { setTab, activeTab: () => activeTab, toast, banner, applyVisibility };
})();
