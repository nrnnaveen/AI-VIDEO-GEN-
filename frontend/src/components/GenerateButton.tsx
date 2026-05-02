'use client';

type Phase = 'idle' | 'generating' | 'done' | 'error';

interface Props { phase: Phase; onClick: () => void; }

const LABELS: Record<Phase, string> = {
  idle:       '⚡  GENERATE VIDEO',
  generating: '⏳  RENDERING…',
  done:       '🔁  REGENERATE',
  error:      '⚠  RETRY',
};

export default function GenerateButton({ phase, onClick }: Props) {
  const busy = phase === 'generating';

  return (
    <button
      onClick={onClick}
      disabled={busy}
      className={[
        'relative group px-12 py-4 rounded-2xl font-display font-bold',
        'text-base tracking-[0.3em] uppercase overflow-hidden',
        'transition-all duration-300 select-none',
        busy
          ? 'opacity-60 cursor-not-allowed bg-white/5 border border-white/10 text-white/40'
          : 'bg-gradient-to-r from-ember via-plasma to-ice text-white',
        !busy && 'hover:scale-105 hover:shadow-[0_0_60px_#c445f066] active:scale-95',
      ].join(' ')}
    >
      {/* Shimmer sweep */}
      {!busy && (
        <span className="absolute inset-0 -translate-x-full group-hover:translate-x-full transition-transform duration-700 bg-gradient-to-r from-transparent via-white/20 to-transparent" />
      )}

      {/* Pulsing ring when busy */}
      {busy && (
        <span className="absolute inset-0 rounded-2xl border border-plasma/60 animate-pulse_ring" />
      )}

      <span className="relative z-10">{LABELS[phase]}</span>
    </button>
  );
}
