'use client';

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface Props { url: string; prompt: string; jobId: string; }

export default function VideoPlayer({ url, prompt, jobId }: Props) {
  const slug = prompt.slice(0, 30).replace(/\s+/g, '_').replace(/[^a-zA-Z0-9_]/g, '');

  async function handleDownload() {
    try {
      const res = await fetch(`${API}/result/${jobId}`);
      if (!res.ok) {
        alert('Download failed — the video may have expired. Please generate again.');
        return;
      }
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `frameforge_${slug}.mp4`;
      a.click();
      URL.revokeObjectURL(blobUrl);
    } catch {
      alert('Download failed — please check your connection and try again.');
    }
  }

  return (
    <div className="animate-reveal w-full max-w-2xl flex flex-col gap-4">
      <div className="relative rounded-2xl overflow-hidden border border-plasma/30 box-glow-plasma bg-black">
        {/* Scanline overlay */}
        <div
          className="pointer-events-none absolute inset-0 z-10 opacity-[0.04]"
          style={{
            backgroundImage: 'repeating-linear-gradient(0deg, #fff 0px, #fff 1px, transparent 1px, transparent 3px)',
            animation: 'scanline 4s linear infinite',
          }}
        />

        <video
          src={url}
          controls
          autoPlay
          loop
          muted
          playsInline
          className="w-full aspect-square object-cover"
        />

        {/* Top-left badge */}
        <span className="absolute top-3 left-3 font-mono text-[10px] uppercase tracking-widest bg-black/70 border border-plasma/40 text-plasma px-2 py-1 rounded-md">
          AI Generated
        </span>
      </div>

      {/* Prompt echo */}
      <p className="font-mono text-xs text-white/40 text-center italic px-4 leading-relaxed line-clamp-2">
        "{prompt}"
      </p>

      {/* Download */}
      <button
        onClick={handleDownload}
        className="self-center flex items-center gap-2 px-8 py-3 rounded-xl border border-ember/50 text-ember font-mono text-sm tracking-widest uppercase hover:bg-ember/10 hover:border-ember/80 transition-all duration-200 hover:scale-105 active:scale-95"
      >
        ↓  Download MP4
      </button>
    </div>
  );
}
