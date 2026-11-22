import type { Metadata, Viewport } from 'next';
import { Pixelify_Sans } from 'next/font/google';
import './globals.css';

const pixel = Pixelify_Sans({ variable: '--font-pixel', subsets: ['latin'] });

const description = 'All of Sri Lanka as one explorable isometric pixel-art map, with Colombo drawn in full detail.';

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000'),
  title: 'Pixel Lanka',
  description,
  openGraph: { type: 'website', siteName: 'Pixel Lanka', title: 'Pixel Lanka', description },
  twitter: { card: 'summary_large_image', title: 'Pixel Lanka', description },
};

export const viewport: Viewport = {
  themeColor: '#201e1c',
  viewportFit: 'cover',
};

export default function RootLayout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="en" className={pixel.variable}>
      <body>{children}</body>
    </html>
  );
}
