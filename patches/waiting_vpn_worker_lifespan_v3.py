# HESAB_WAITING_VPN_WORKER_LIFESPAN_V3
# FastAPI's existing custom lifespan bypasses @app.on_event('startup').
# Bridge the existing (V2) paid-only restoration worker into that lifespan,
# without changing billing, XUI toggle logic or existing lifespan cleanup.
import asyncio as _wvr3_asyncio
import json as _wvr3_json
import os as _wvr3_os
import time as _wvr3_time
from datetime import datetime as _wvr3_datetime,timezone as _wvr3_timezone
from pathlib import Path as _wvr3_Path
from contextlib import asynccontextmanager as _wvr3_asynccontextmanager

_WVR3_ORIGINAL_LIFESPAN=app.router.lifespan_context
_WVR3_STARTUP_CALLBACKS=[f for f in app.router.on_startup if f is _wvc_startup]
if len(_WVR3_STARTUP_CALLBACKS)!=1:
    raise RuntimeError("Expected exactly one previous waiting worker startup callback")
if not callable(_WVR3_ORIGINAL_LIFESPAN):
    raise RuntimeError("Cannot wrap existing application lifespan")

# Prevent a future FastAPI/Starlette implementation that also executes
# on_startup under a custom lifespan from launching a second worker.
app.router.on_startup[:]=[
    f for f in app.router.on_startup if f is not _wvc_startup
]
_WVR3_HEALTH_FILE=_wvr3_Path("/tmp/hesab-waiting-worker-v3.json")
_WVR3_START_AT=_wvr3_time.time()
_WVR3_HEARTBEAT={"pid":_wvr3_os.getpid(),"started_at":_WVR3_START_AT,
                 "scan_started":0,"scan_completed":0,"errors":0,
                 "last_completed_at":None,"last_error":None}

def _wvr3_report(stage,error=None):
    if stage=="scanning":
        _WVR3_HEARTBEAT["scan_started"]+=1
    elif stage=="completed":
        _WVR3_HEARTBEAT["scan_completed"]+=1
        _WVR3_HEARTBEAT["last_completed_at"]=_wvr3_time.time()
        _WVR3_HEARTBEAT["last_error"]=None
    elif stage=="error":
        _WVR3_HEARTBEAT["errors"]+=1
        _WVR3_HEARTBEAT["last_error"]=str(error or "unknown")[:120]
    _WVR3_HEARTBEAT["stage"]=stage
    _WVR3_HEARTBEAT["heartbeat_at"]=_wvr3_time.time()
    temp=_wvr3_Path(str(_WVR3_HEALTH_FILE)+".tmp")
    try:
        temp.write_text(_wvr3_json.dumps(_WVR3_HEARTBEAT,sort_keys=True))
        temp.chmod(0o600)
        temp.replace(_WVR3_HEALTH_FILE)
    except Exception as exc:
        print("WVR3_HEARTBEAT_WRITE_ERROR",type(exc).__name__,str(exc)[:100],
              flush=True)

async def _wvr3_background_runner():
    # No extra panel polling: same V2 reconcile interval and candidate query.
    _wvr3_report("started")
    print("WVR3_WORKER_STARTED",flush=True)
    while True:
        _wvr3_report("scanning")
        try:
            await _wvr3_asyncio.to_thread(_wvc_reconcile_once)
            _wvr3_report("completed")
        except Exception as exc:
            _wvr3_report("error",type(exc).__name__+":"+str(exc)[:100])
            print("WVR3_SCAN_ERROR",type(exc).__name__,str(exc)[:160],
                  flush=True)
        await _wvr3_asyncio.sleep(_WVC_PAYMENT_CHECK_INTERVAL)

@_wvr3_asynccontextmanager
async def _wvr3_lifespan(application):
    # Preserve ALL old startup, yield state and teardown behavior.
    async with _WVR3_ORIGINAL_LIFESPAN(application) as state:
        existing=getattr(application.state,"wvr3_task",None)
        if existing is not None and not existing.done():
            raise RuntimeError("Refuse duplicate waiting restore worker")
        task=_wvr3_asyncio.create_task(_wvr3_background_runner(),
                                       name="hesab-paid-maya-restore-v3")
        application.state.wvr3_task=task
        try:
            yield state
        finally:
            task.cancel()
            await _wvr3_asyncio.gather(task,return_exceptions=True)
            application.state.wvr3_task=None
            _wvr3_report("stopped")
            print("WVR3_WORKER_STOPPED",flush=True)

app.router.lifespan_context=_wvr3_lifespan
