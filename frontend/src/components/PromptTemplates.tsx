'use client';

interface Props { onSelect: (t: string) => void; }

const TEMPLATES = [
  { emoji: '🌊', label: 'Ocean Calm',   text: 'A serene ocean at golden hour, slow waves, cinematic depth of field, 8K' },
  { emoji: '🌧', label: 'Rain Mood',    text: 'Rain on a neon-lit Tokyo street at night, reflections on wet asphalt, moody' },
  { emoji: '🌲', label: 'Forest Mist',  text: 'Morning mist drifting through an ancient pine forest, ethereal light rays' },
  { emoji: '🌌', label: 'Space Drift',  text: 'Slow drift through a colourful nebula, deep space, ultra-detailed photorealistic' },
  { emoji: '🌋', label: 'Lava Flow',    text: 'Molten lava flowing slowly over black basalt at night, glowing embers, cinematic' },
  { emoji: '🏙', label: 'Cyber City',   text: 'Cyberpunk megacity at dusk, flying vehicles, neon advertisements, Blade Runner style' },
];

export default function PromptTemplates({ onSelect }: Props) {
  return (
    <div>
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-white/40 mb-3">Quick Templates</p>
      <div className="flex flex-wrap gap-2">
        {TEMPLATES.map(t => (
          <button
            key={t.label}
            onClick={() => onSelect(t.text)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/10 bg-white/5
                       font-mono text-xs text-white/60 hover:border-ice/50 hover:text-ice hover:bg-ice/5
                       transition-all duration-200 hover:scale-105 active:scale-95"
          >
            <span>{t.emoji}</span>
            <span>{t.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
