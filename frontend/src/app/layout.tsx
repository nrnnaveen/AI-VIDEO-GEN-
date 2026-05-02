import type { Metadata } from 'next';
import { Cinzel, Share_Tech_Mono } from 'next/font/google';
import './globals.css';

const cinzel = Cinzel({
  subsets: ['latin'],
  variable: '--font-display',
  weight: ['400', '700', '900'],
});

const shareTechMono = Share_Tech_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  weight: '400',
});

export const metadata: Metadata = {
  title: 'FRAMEFORGE — AI Video Generator',
  description: 'Generate cinematic AI videos from text prompts. Free & open-source.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${cinzel.variable} ${shareTechMono.variable}`}>
      <body className="bg-void text-white antialiased">{children}</body>
    </html>
  );
}
