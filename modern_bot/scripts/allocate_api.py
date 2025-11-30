#!/usr/bin/env python3
"""
Веб-интерфейс для распределения лотов аукциона.
- Загружаете файл реестра (XLSX) через форму.
- Бекенд берет продажи и остатки из файлов по умолчанию в корне проекта.
- Возвращает XLSX с распределением и короткий предпросмотр в браузере.
Запуск:
    uvicorn modern_bot.scripts.allocate_api:app --reload --port 8000
После старта открыть http://127.0.0.1:8000
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from starlette.concurrency import run_in_threadpool

from modern_bot.scripts.allocate_auction import BASE_DIR, run_allocation

app = FastAPI(title="Распределение аукциона", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_SALES = BASE_DIR / "Табличная_часть_Продажи_распродажа_0109_311225.xlsx"
DEFAULT_STOCK = BASE_DIR / "остатки на 301125.xlsx"
DEFAULT_AUCTION = BASE_DIR / "Реестр аукциона 15.11 Санкт-Петербург.xlsx"
OUTPUT_DIR = BASE_DIR / "tmp_outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

HOME_HTML = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>Распределение аукциона</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 32px; background: #f8fafc; color: #0f172a; }
    h1 { margin-bottom: 0.2em; }
    .card { background: #fff; padding: 20px; border-radius: 12px; box-shadow: 0 10px 30px rgba(15,23,42,0.08); max-width: 900px; }
    form { margin-top: 1em; display: grid; gap: 12px; }
    input[type=file] { padding: 10px; border: 1px solid #cbd5e1; border-radius: 8px; background: #f8fafc; }
    button { padding: 12px 16px; background: #0ea5e9; border: none; border-radius: 10px; color: #fff; font-size: 15px; cursor: pointer; }
    button:hover { background: #0284c7; }
    .muted { color: #475569; font-size: 14px; }
    .note { background: #ecfeff; border: 1px solid #bae6fd; padding: 12px; border-radius: 10px; margin-top: 12px; }
    table { border-collapse: collapse; width: 100%; margin-top: 16px; }
    th, td { border: 1px solid #e2e8f0; padding: 8px; font-size: 13px; text-align: left; }
    th { background: #f1f5f9; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Распределение лотов аукциона</h1>
    <p class="muted">Загрузите XLSX реестра. Продажи и остатки берутся из файлов по умолчанию.</p>
    <form action="/upload" method="post" enctype="multipart/form-data">
      <label>Реестр аукциона (XLSX):
        <input type="file" name="auction_file" accept=".xlsx" />
      </label>
      <button type="submit">Рассчитать распределение</button>
    </form>
    <div class="note">
      <b>Логика:</b> считаем скорость продаж (шт./неделя) по подразделениям, покрытие = остаток / скорость,
      отправляем туда, где покрытие минимально; при равенстве — туда, где скорость выше.
    </div>
  </div>
</body>
</html>
"""


def _safe_output_path() -> Path:
    return OUTPUT_DIR / f"alloc_{uuid.uuid4().hex}.xlsx"


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    return HOME_HTML


@app.post("/upload", response_class=HTMLResponse)
async def upload(auction_file: UploadFile | None = File(default=None)) -> HTMLResponse:
    # Если файл не пришел — используем дефолтный реестр.
    if auction_file and auction_file.filename:
        with NamedTemporaryFile(delete=False, suffix=Path(auction_file.filename).suffix) as tmp:
            shutil.copyfileobj(auction_file.file, tmp)
            auction_path = Path(tmp.name)
    else:
        auction_path = DEFAULT_AUCTION

    output_path = _safe_output_path()

    output_path, alloc_df, summary_df = await run_in_threadpool(
        run_allocation,
        DEFAULT_SALES,
        DEFAULT_STOCK,
        auction_path,
        output_path,
        None,
        True,
    )

    alloc_preview = alloc_df.head(50).to_html(index=False)
    summary_preview = summary_df.head(20).to_html(index=False)

    download_link = f"/download/{output_path.name}"

    html = f"""
    <html><head><meta charset='utf-8'>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 24px; color: #0f172a; }}
      a.button {{ background: #0ea5e9; color: #fff; padding: 10px 14px; border-radius: 8px; text-decoration: none; }}
      h2 {{ margin-top: 32px; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border: 1px solid #e2e8f0; padding: 6px; font-size: 12px; }}
      th {{ background: #f1f5f9; }}
      .muted {{ color: #475569; }}
    </style>
    </head><body>
      <h1>Готово</h1>
      <p>Файл с распределением: <a class="button" href="{download_link}">скачать XLSX</a></p>
      <p class="muted">Берутся продажи: {DEFAULT_SALES.name}, остатки: {DEFAULT_STOCK.name}</p>
      <h2>Итог по подразделениям (топ 20)</h2>
      {summary_preview}
      <h2>Предпросмотр распределения (первые 50 строк)</h2>
      {alloc_preview}
      <p><a href="/">← Новый расчет</a></p>
    </body></html>
    """
    return HTMLResponse(content=html)


@app.get("/download/{filename}")
async def download(filename: str):
    path = (OUTPUT_DIR / filename).resolve()
    if OUTPUT_DIR not in path.parents and path != OUTPUT_DIR:
        return HTMLResponse(status_code=400, content="Некорректное имя файла")
    if not path.exists():
        return HTMLResponse(status_code=404, content="Файл не найден")
    return FileResponse(path, filename=path.name)

