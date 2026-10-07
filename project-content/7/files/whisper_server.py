from fastapi import FastAPI, File, UploadFile
import torch
import whisper
import uvicorn
import tempfile
import os
import signal

app = FastAPI()
model = whisper.load_model("base.en")  # "base" ou "small", "medium", "large"
device = "cuda" if torch.cuda.is_available() else "cpu"

@app.post("/transcribe/")
async def transcribe(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(await file.read())
        tmp.flush()
        result = model.transcribe(tmp.name, language="en", fp16=(device=="cuda"))
        print(f"Transcription result: {result['text']}")
        return {"text": result["text"]}

@app.get("/")
async def root():
    return {}

@app.get("/shutdown")
async def shutdown():
    # Retourne la réponse puis arrête le serveur
    response = {"message": "Server is shutting down..."}
    # Utilise une tâche pour tuer le serveur après la réponse
    import threading, time
    def stop():
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Thread(target=stop).start()
    return response

@app.on_event('shutdown')
def on_shutdown():
    print('Server shutting down...')

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
