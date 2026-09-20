"""Local-first live voice server; Vercel serves only ../web assets, not this process."""
from __future__ import annotations
import asyncio
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from controller import Controller
from settings import settings, public_config, missing_keys

cfg=settings();sessions={};handler=None

@asynccontextmanager
async def lifespan(app):
    yield
    for entry in list(sessions.values()):
        entry['controller'].connected=False
        if entry['controller'].workout:entry['controller'].workout.control('stop')
        entry['task'].cancel()
    if handler:await handler.close()

app=FastAPI(title='Spare Voice',lifespan=lifespan,docs_url=None,redoc_url=None)
app.add_middleware(CORSMiddleware,allow_origins=cfg['origins'],allow_methods=['GET','POST'],
                   allow_headers=['Authorization','Content-Type'],allow_credentials=False)

class Offer(BaseModel):
    sdp:str=Field(max_length=100000)
    type:str

class Control(BaseModel):
    action:str


def authenticate(request):
    origin=request.headers.get('origin')
    if origin and origin not in cfg['origins']:
        raise HTTPException(403,'This frontend origin is not allowed. Set ALLOWED_ORIGINS on the server.')
    token=cfg['access_token']
    if token:
        if not secrets.compare_digest(request.headers.get('authorization',''),'Bearer '+token):
            raise HTTPException(401,'Enter your private Spare access code in Connection settings. This is not a provider API key.')
    else:
        remote=request.client.host if request.client else ''
        public_origin=origin and urlparse(origin).hostname not in {'localhost','127.0.0.1'}
        if remote not in {'127.0.0.1','::1','testclient'} or public_origin:
            raise HTTPException(403,'Public/tunneled use requires SPARE_ACCESS_TOKEN. Do not expose an unprotected voice backend.')

@app.middleware('http')
async def headers(request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='no-store' if request.url.path.startswith('/api') else 'no-cache'
    return response

@app.get('/api/config')
async def config():
    result=public_config()
    try:
        import importlib.util
        result['voice_installed']=importlib.util.find_spec('pipecat') is not None
    except (ValueError,ModuleNotFoundError):result['voice_installed']=False
    return result

@app.post('/api/offer')
async def offer(body:Offer,request:Request):
    global handler
    authenticate(request)
    missing=missing_keys(cfg)
    if missing:raise HTTPException(503,'Missing private server settings: '+', '.join(missing))
    if body.type!='offer':raise HTTPException(400,'Expected a WebRTC offer.')
    # One call at a time: intentional demo cost control, not a multi-tenant deployment.
    for sid,e in list(sessions.items()):
        if e['task'].done():sessions.pop(sid,None)
    if sessions:raise HTTPException(409,'Another call is active. Stop it before starting another.')
    try:
        from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequestHandler, SmallWebRTCRequest
        from pipecat.transports.smallwebrtc.connection import IceServer
        from coach import run_coach
    except (ImportError,ModuleNotFoundError) as exc:
        raise HTTPException(503,'Voice dependencies are missing. Run the included launcher or uv sync --extra voice.') from None
    if handler is None:
        handler=SmallWebRTCRequestHandler(ice_servers=[IceServer(**x) for x in cfg['ice_servers']])
    sid=secrets.token_urlsafe(24);c=Controller(cfg['max_designs'])
    async def setup(connection):
        async def guarded():
            try:await run_coach(connection,c,cfg)
            except asyncio.CancelledError:raise
            except Exception:
                c.error='Voice startup failed. Check model access, keys, and installed dependencies.'
                c.connected=False
                if c.workout:c.workout.control('pause')
            finally:
                c.connected=False
                try:await connection.disconnect()
                except Exception:pass
        t=asyncio.create_task(guarded())
        sessions[sid]={'controller':c,'task':t,'connection':connection,'created':time.monotonic()}
    try:
        result=await handler.handle_web_request(SmallWebRTCRequest(sdp=body.sdp,type=body.type),setup)
    except Exception:
        if sid in sessions:
            sessions.pop(sid)['task'].cancel()
        raise HTTPException(502,'Could not negotiate audio. No workout started.') from None
    if not result or sid not in sessions:raise HTTPException(502,'Voice session initialization failed.')
    return {**result,'session_id':sid}


def get_session(sid,request):
    authenticate(request)
    e=sessions.get(sid)
    if not e:raise HTTPException(404,'Session expired or disconnected.')
    return e

@app.get('/api/session/{sid}')
async def status(sid:str,request:Request):
    return get_session(sid,request)['controller'].public()

@app.post('/api/session/{sid}/control')
async def control(sid:str,body:Control,request:Request):
    e=get_session(sid,request);c=e['controller']
    if body.action not in {'pause','stop','disconnect'}:raise HTTPException(400,'Only emergency pause/stop/disconnect are exposed here. Use voice to resume.')
    if c.workout:c.workout.control('stop' if body.action in {'stop','disconnect'} else 'pause')
    c.generation+=1
    # Cancel output too, so a UI stop does not leave an obsolete instruction playing.
    if getattr(c,'task',None):
        from pipecat.frames.frames import InterruptionFrame
        await c.task.queue_frames([InterruptionFrame()])
    c.event(body.action)
    if body.action=='disconnect':
        c.connected=False;e['task'].cancel();await e['connection'].disconnect();sessions.pop(sid,None)
    return {'ok':True,'workout':c.workout.snapshot() if c.workout else None}

app.mount('/',StaticFiles(directory=Path(__file__).resolve().parent.parent/'web',html=True),name='web')

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=7860,log_level='warning')
