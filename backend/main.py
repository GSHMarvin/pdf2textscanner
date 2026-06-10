import io
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from converter import convert_pdf_to_text
from parser import parse_form

app = FastAPI(title="PDF to Text Scanner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)


@app.post("/api/convert")
async def convert(
    file: UploadFile = File(...),
    ocr_lang: str = Form("eng"),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        result = convert_pdf_to_text(pdf_bytes, ocr_lang=ocr_lang)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {exc}")

    return {
        "filename": file.filename,
        "page_count": result["page_count"],
        "pages": result["pages"],
        "text": result["text"],
        "parsed": parse_form(result["text"]),
    }


# Mount static files AFTER API routes so the catch-all doesn't swallow POST /api/convert
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
