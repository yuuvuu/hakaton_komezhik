from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import hmac
import hashlib
import secrets
from app.data import users
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

TELEGRAM_BOT_TOKEN = "6145304122:AAElJG_7FLq9zJ3n5lXwr4PpYG9HXWV64RU"

def check_response(data):
    d = data.copy()
    hash_value = d.pop('hash', None)
    d_list = []
    for key in sorted(d.keys()):
        if d[key] is not None:
            d_list.append(f"{key}={d[key]}")
    data_string = '\n'.join(d_list).encode('utf-8')
    secret_key = hashlib.sha256(TELEGRAM_BOT_TOKEN.encode('utf-8')).digest()
    hmac_string = hmac.new(secret_key, data_string, hashlib.sha256).hexdigest()
    return hmac_string == hash_value

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@router.get("/login/telegram")
async def login_telegram(request: Request):
    data = {
        'id': request.query_params.get('id'),
        'first_name': request.query_params.get('first_name'),
        'last_name': request.query_params.get('last_name'),
        'username': request.query_params.get('username'),
        'photo_url': request.query_params.get('photo_url'),
        'auth_date': request.query_params.get('auth_date'),
        'hash': request.query_params.get('hash')
    }

    if check_response(data):
        user_id = data['id']
        if user_id in users:
            token = users[user_id]['token']
            logger.info(f"User {user_id} already exists. Reusing token: {token}")
        else:
            token = secrets.token_hex(16)
            users[user_id] = {
                'data': data,
                'token': token,
                'nickname': None,
                'schedule': None,
                'description': "No description yet",
                'joined_rooms': []
            }
            logger.info(f"User {user_id} authenticated with token: {token}")
        response = RedirectResponse(url=f"/chat?token={token}", status_code=303)
        response.set_cookie(
            key="auth_token",
            value=token,
            max_age=3600,
            path="/",
            secure=True,
            samesite="None"
        )
        logger.info(f"Cookie set with token: {token}, Secure=True, SameSite=None")
        return response
    else:
        raise HTTPException(status_code=401, detail="Authorization failed")

@router.get("/chat", response_class=HTMLResponse)
async def chat(request: Request):
    token = request.query_params.get("token") or request.cookies.get("auth_token")
    logger.info(f"Checking token in /chat: {token or 'None'}")
    if not token:
        logger.warning("No token found, redirecting to /")
        return RedirectResponse(url="/", status_code=303)
    
    user_id = next((uid for uid, info in users.items() if info['token'] == token), None)
    if not user_id:
        logger.warning("Invalid token, redirecting to /")
        return RedirectResponse(url="/", status_code=303)
    
    return templates.TemplateResponse("index.html", {"request": request, "token": token})