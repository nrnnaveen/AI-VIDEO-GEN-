# 🎬 Free AI Video Generator

Turn a text prompt into a short cinematic video — completely free and open-source.

## Stack
| Layer    | Technology                              |
|----------|-----------------------------------------|
| Frontend | Next.js 14 + Tailwind CSS               |
| Backend  | FastAPI + Diffusers (Stable Diffusion)  |
| Frames   | Pillow                                  |
| Video    | ffmpeg                                  |
| Deploy   | Vercel (frontend) · Render/HF (backend) |

## Quick Start

### Backend
```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

### Production deploy

**Frontend → Vercel**
```bash
cd frontend
npx vercel --prod
```

**Backend → Render**
- New Web Service → connect repo → root dir: `backend`
- Build cmd: `pip install -r requirements.txt`
- Start cmd: `uvicorn main:app --host 0.0.0.0 --port 10000`

**Backend → Hugging Face Spaces**
- New Space → Gradio SDK → upload `backend/` contents
- The `app.py` wrapper is already included.

## Environment Variables

Create `frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=https://your-backend.onrender.com
```

## Prompt Templates
| Template      | Prompt hint                                       |
|---------------|---------------------------------------------------|
| Ocean Calm    | A serene ocean at golden hour, cinematic          |
| Rain Mood     | Rain on a neon-lit city street at night           |
| Forest Mist   | Morning mist drifting through a pine forest       |
| Space Drift   | Slow drift through a nebula, deep space           |

---
MIT License © 2024
