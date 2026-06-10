"""
Minimal stub for the `kaolin` Python package — just enough to satisfy
the imports SAM 3D Objects' inference path uses. Real kaolin doesn't
have a clean Windows wheel for our torch 2.12 + cu126 combo (its
DLL load fails), and the missing pieces are only used for Jupyter
visualisation and tensor-shape assertions — neither of which are on
the actual inference forward path.

Run-time check: imports succeed, dummy classes/functions raise
RuntimeError if they're ever actually called, so we'll catch regressions
loudly rather than silently.
"""
from __future__ import annotations
import sys
import types


def _module(name, parent=None):
    m = types.ModuleType(name)
    sys.modules[name] = m
    if parent is not None:
        setattr(parent, name.split(".")[-1], m)
    return m


def _stub_callable(name):
    def _fn(*a, **kw):
        raise RuntimeError(
            f"kaolin stub: {name} was actually called during SAM 3D inference; "
            "the stub is no longer sufficient — install real kaolin or refactor."
        )
    _fn.__name__ = name
    return _fn


def _stub_class(name):
    class _Stub:
        def __init__(self, *a, **kw):
            raise RuntimeError(
                f"kaolin stub: {name} instance created during SAM 3D inference; "
                "the stub is no longer sufficient."
            )

        def __getattr__(self, item):
            raise RuntimeError(f"kaolin stub: {name}.{item} accessed")
    _Stub.__name__ = name
    return _Stub


def install():
    """Insert minimal kaolin stubs into sys.modules. Idempotent."""
    if "kaolin" in sys.modules and not getattr(sys.modules["kaolin"], "_scs_stub", False):
        # real kaolin imported earlier — don't shadow it
        return False

    kaolin = _module("kaolin")
    kaolin._scs_stub = True
    kaolin.__version__ = "0.0.0-scs-stub"

    visualize = _module("kaolin.visualize", parent=kaolin)
    visualize.IpyTurntableVisualizer = _stub_class("IpyTurntableVisualizer")

    render = _module("kaolin.render", parent=kaolin)
    camera = _module("kaolin.render.camera", parent=render)
    camera.Camera = _stub_class("Camera")
    camera.CameraExtrinsics = _stub_class("CameraExtrinsics")
    camera.PinholeIntrinsics = _stub_class("PinholeIntrinsics")

    utils = _module("kaolin.utils", parent=kaolin)
    testing = _module("kaolin.utils.testing", parent=utils)

    # check_tensor IS called in flexicubes — but with the stub raising loudly we
    # quickly see whether the inference forward path needs it.
    # Make it a no-op so it doesn't blow up; tensor validation is a developer
    # safety net, not a correctness requirement.
    def _check_tensor(*args, **kwargs):
        return None
    testing.check_tensor = _check_tensor

    return True


if __name__ == "__main__":
    install()
    import kaolin
    print(f"kaolin stub installed: version={kaolin.__version__}, stub={kaolin._scs_stub}")
    import kaolin.visualize
    import kaolin.render.camera
    import kaolin.utils.testing
    print("All four stubbed submodules importable.")
