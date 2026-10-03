"""Private process entry point; never executes downloaded or model-generated code."""
from __future__ import annotations
import json
import os
import sys
import traceback
from pathlib import Path

def main():
    mode, request_path, result_path = sys.argv[1:4]
    request = json.loads(Path(request_path).read_text())
    limits = request["limits"]
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (int(limits["timeout_seconds"])+1, int(limits["timeout_seconds"])+2))
        resource.setrlimit(resource.RLIMIT_FSIZE, (int(limits["output_mb"])*1024**2, int(limits["output_mb"])*1024**2))
        # Darwin's RLIMIT_AS is not reliably enforced; supervisor also monitors RSS.
        if sys.platform.startswith("linux"):
            memory = int(limits["memory_mb"]) * 1024**2
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    except (ImportError, ValueError, OSError):
        pass
    try:
        if mode == "build":
            from .geometry import build
            import inspect
            cache_options={'cache_dir':request.get('cache_dir')} if 'cache_dir' in inspect.signature(build).parameters else {}
            result = build(request["spec"], request["output_dir"],**cache_options)
        elif mode == "verify":
            from .verifier import verify
            result = verify(request["spec"], request["output_dir"])
        elif mode == 'measure':
            from .measure import measure
            result=measure(request['output_dir'],request['entities'],request.get('kind','distance'))
        else:
            raise ValueError("Unknown worker operation")
        Path(result_path).write_text(json.dumps({"ok": True, "result": result}, default=str))
    except BaseException as error:
        Path(result_path).write_text(json.dumps({"ok": False, "error": str(error), "type":type(error).__name__, "trace":traceback.format_exc()[-6000:]}))
        sys.exit(1)

if __name__ == "__main__":
    main()
