import type { Metadata } from "next";
import { Inter, Noto_Sans_JP } from "next/font/google";
import Nav from "@/components/Nav";
import ShaderBackground from "@/components/ShaderBackground";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], axes: ["opsz"], variable: "--font-inter", display: "block" });
const jp = Noto_Sans_JP({ subsets: ["latin"], variable: "--font-jp", weight: ["400", "500", "700"] });

export const metadata: Metadata = {
  title: "DocLens",
  description: "Extract fields and ask questions about business PDFs. Every answer points back to its source.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${jp.variable}`} suppressHydrationWarning>
      <body>
        <ShaderBackground />
        <a className="skip-link" href="#main-content">Skip to content</a>
        <div className="shell">
          <Nav />
          <main id="main-content" tabIndex={-1}>{children}</main>
        </div>
      </body>
    </html>
  );
}
