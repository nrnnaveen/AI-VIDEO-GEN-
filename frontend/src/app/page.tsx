'use client';

import { useState, useRef } from 'react';
import GenerateButton from '../components/GenerateButton';
import VideoPlayer    from '../components/VideoPlayer';
import PromptTemplates from '../components/PromptTemplates';
import StatusBar      from '../components/StatusBar';

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Phase = 'idle' | 'generating' | 'done' | 'error';

export default function Home() {
  const [prompt,   setPrompt]   = useState('');
  const [phase,    setPhase]    = useState<Phase>('idle');
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [jobId,    setJobId]    = useState<string | null>(null);
  const [error,    setError]    = useState<string | null>(null);
  const [frames,   setFrames]   = useState(6);
  const [fps,      setFps]      = useState(8);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  async function handleGenerate() {
    if (!prompt.trim()) { inputRef.current?.focus(); return; }
    setPhase('generating');
    setVideoUrl(null);
    setJobId(null);
    setError(null);

    const RETRY_DELAY_MS = 2000;
    const MAX_TRANSIENT_ERRORS = 3;

    try {
      // Submit the job with retry on transient network / cold-start failures
      let res: Response | null = null;
      for (let attempt = 0; attempt < 3; attempt++) {
        if (attempt > 0) await new Promise(r => setTimeout(r, RETRY_DELAY_MS * attempt));
        try {
          res = await fetch(`${API}/generate`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              prompt,
              num_frames: frames,
              fps,
              num_inference_steps: 25,
              guidance_scale: 7.5,
            }),
          });
          // Stop retrying if response is definitive (not a transient server error)
          if (res.ok || (res.status !== 502 && res.status !== 503 && res.status !== 504)) break;
        } catch {
          if (attempt === 2) throw new Error('Failed to reach the server. Is the backend running?');
        }
      }

      if (!res || !res.ok) {
        const body = await res?.json().catch(() => ({})) ?? {};
        throw new Error(body.detail ?? `Server error ${res?.status ?? 'unknown'}`);
      }

      const { job_id } = await res.json();
      setJobId(job_id);

      // Poll /result/{job_id} until the video is ready (max 5 minutes)
      const MAX_POLLS = 120;
      let transientErrors = 0;
      for (let attempt = 0; attempt < MAX_POLLS; attempt++) {
        if (attempt > 0) {
          await new Promise(r => setTimeout(r, 2500));
        }
        let poll: Response;
        try {
          poll = await fetch(`${API}/result/${job_id}`);
        } catch {
          // Network error (e.g. Render cold-start) — retry up to MAX_TRANSIENT_ERRORS times
          transientErrors++;
          if (transientErrors > MAX_TRANSIENT_ERRORS) throw new Error('Lost connection to the server.');
          continue;
        }
        if (!poll.ok) {
          // Transient gateway errors — retry instead of failing immediately
          if ((poll.status === 502 || poll.status === 503 || poll.status === 504) && transientErrors < MAX_TRANSIENT_ERRORS) {
            transientErrors++;
            continue;
          }
          const body = await poll.json().catch(() => ({}));
          throw new Error(body.detail ?? `Server error ${poll.status}`);
        }
        transientErrors = 0; // reset on successful response
        const ct = poll.headers.get('content-type') ?? '';
        if (ct.startsWith('video/')) {
          const blob = await poll.blob();
          setVideoUrl(URL.createObjectURL(blob));
          setPhase('done');
          return;
        }
        const data = await poll.json();
        if (data.status === 'failed') {
          throw new Error(data.error ?? 'Generation failed');
        }
        // status is 'queued' or 'processing' — keep polling
      }
      throw new Error('Generation timed out — please try again');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase('error');
    }
  }

  return (
    <main className="relative min-h-dvh flex flex-col items-center px-4 py-14 gap-10 overflow-hidden">

      {/* ── Ambient background blobs ── */}
      <div className="pointer-events-none fixed inset-0 -z-10">
        <div className="absolute top-[-20%] left-[-10%] w-[55vw] h-[55vw] rounded-full bg-plasma/10 blur-[120px]" />
        <div className="absolute bottom-[-15%] right-[-8%] w-[45vw] h-[45vw] rounded-full bg-ember/10 blur-[100px]" />
        <div className="absolute top-[40%] left-[35%] w-[25vw] h-[25vw] rounded-full bg-ice/5 blur-[80px]" />
      </div>

      {/* ── Header ── */}
      <header className="flex flex-col items-center gap-3 animate-reveal" style={{ animationDelay: '0ms' }}>
        <div className="flex items-center gap-3">
          <span className="text-4xl">🎬</span>
          <h1 className="font-display font-black text-5xl tracking-widest uppercase glow-plasma">
            FRAMEFORGE
          </h1>
        </div>
        <p className="font-mono text-sm text-white/40 tracking-[0.25em] uppercase">
          Text → Cinematic AI Video · Free & Open-Source
        </p>
      </header>

      {/* ── Prompt templates ── */}
      <div className="animate-reveal w-full max-w-2xl" style={{ animationDelay: '120ms' }}>
        <PromptTemplates onSelect={t => { setPrompt(t); inputRef.current?.focus(); }} />
      </div>

      {/* ── Prompt input ── */}
      <div className="animate-reveal w-full max-w-2xl" style={{ animationDelay: '200ms' }}>
        <label className="block font-mono text-xs uppercase tracking-[0.2em] text-white/50 mb-2">
          Your Prompt
        </label>
        <textarea
          ref={inputRef}
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleGenerate(); }}
          rows={3}
          placeholder="A lone lighthouse on a stormy cliff at dusk, cinematic…"
          disabled={phase === 'generating'}
          className={[
            'w-full bg-white/5 border rounded-xl px-5 py-4 resize-none',
            'font-mono text-sm text-white/90 placeholder-white/20',
            'outline-none transition-all duration-300',
            phase === 'generating'
              ? 'border-white/10 opacity-60 cursor-not-allowed'
              : 'border-white/10 focus:border-plasma/60 focus:box-glow-plasma',
          ].join(' ')}
        />
        <p className="mt-1.5 font-mono text-[11px] text-white/25">
          Ctrl+Enter to generate · {prompt.length}/500
        </p>
      </div>

      {/* ── Sliders ── */}
      <div className="animate-reveal w-full max-w-2xl grid grid-cols-2 gap-6" style={{ animationDelay: '260ms' }}>
        <SliderControl
          label="Frames"
          value={frames}
          min={4} max={8} step={1}
          onChange={setFrames}
          hint={`${frames} frames`}
        />
        <SliderControl
          label="FPS"
          value={fps}
          min={4} max={24} step={2}
          onChange={setFps}
          hint={`${fps} fps — ~${(frames / fps).toFixed(1)}s`}
        />
      </div>

      {/* ── Generate button ── */}
      <div className="animate-reveal" style={{ animationDelay: '320ms' }}>
        <GenerateButton phase={phase} onClick={handleGenerate} />
      </div>

      {/* ── Status bar ── */}
      {(phase === 'generating' || phase === 'error') && (
        <StatusBar phase={phase} error={error} />
      )}

      {/* ── Video player ── */}
      {phase === 'done' && videoUrl && jobId && (
        <VideoPlayer url={videoUrl} prompt={prompt} jobId={jobId} />
      )}

      {/* ── Footer ── */}
      <footer className="mt-auto font-mono text-[11px] text-white/20 tracking-widest uppercase text-center">
        Stable Diffusion · ffmpeg · FastAPI · Next.js · MIT License
      </footer>
    </main>
  );
}

// ─── Inline slider control ────────────────────────────────────────────────

interface SliderProps {
  label: string;
  value: number;
  min: number; max: number; step: number;
  onChange: (v: number) => void;
  hint: string;
}

function SliderControl({ label, value, min, max, step, onChange, hint }: SliderProps) {
  return (
    <div>
      <div className="flex justify-between font-mono text-xs uppercase tracking-[0.15em] mb-2">
        <span className="text-white/50">{label}</span>
        <span className="text-plasma">{hint}</span>
      </div>
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full accent-plasma cursor-pointer"
      />
    </div>
  );
}
