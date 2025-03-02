from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.router_page import router as router_page
from app.api.router_socket import router as router_socket
from fastapi.templating import Jinja2Templates

app = FastAPI()
app.users = {}
# Настраиваем шаблоны
templates = Jinja2Templates(directory="app/templates")

# Монтируем статические файлы
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(router_socket)
app.include_router(router_page)