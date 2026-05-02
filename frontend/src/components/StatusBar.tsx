'use client';

type Phase = 'generating' | 'error';
interface Props { phase: Phase; error: string | null; }

const STEPS = [
  'Initialising model',
  'Encoding prompt',
  'Diffusing frames',
  'Applying motion',
  'Encoding MP4',
];

export default function StatusBar({ phase, error }: Props) {
  if (phase === 'error') {
    return (
      <div className="w-full max-w-2xl animate-reveal">
        <div className="rounded-xl border border-ember/40 bg-ember/10 px-5 py-4 font-mono text-sm text-ember/90">
          <span className="font-bold">ERROR — </span>{error ?? 'Unknown error. Is the backend running?'}
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-2xl animate-reveal flex flex-col gap-3">
      {/* Progress dots */}
      <div className="flex items-center gap-3">
        {STEPS.map((step, i) => (
          <div key={step} className="flex-1 flex flex-col items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-plasma animate-pulse_ring"
                 style={{ animationDelay: `${i * 0.3}s` }} />
            <span className="font-mono text-[9px] text-white/30 uppercase tracking-wider text-center">
              {step}
            </span>
          </div>
        ))}
      </div>

      {/* Indeterminate bar */}
      <div className="w-full h-px bg-white/10 rounded-full overflow-hidden">
        <div className="h-full bg-gradient-to-r from-plasma via-ice to-ember rounded-full animate-[shimmer_2s_linear_infinite] w-1/2"
             style={{ backgroundSize: '200% 100%' }} />
      </div>

      <p className="font-mono text-xs text-white/30 text-center">
        This can take 30–90 s on CPU · much faster on GPU
      </p>
    </div>
  );
}
