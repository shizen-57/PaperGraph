import { Inter, Manrope } from "next/font/google";
import Link from "next/link";
import "@/app/home.css";
import type { DocumentSummary } from "@/lib/types";
import styles from "./HeroHome.module.css";

const inter = Inter({ subsets: ["latin"], axes: ["opsz"], variable: "--font-inter", display: "swap" });
const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope", display: "swap" });

export default function HeroHome({ docs, error }: { docs: DocumentSummary[]; error: string | null }) {
  const collections = new Set(docs.map((d) => d.folder)).size;

  return (
    <div className={`fs ${inter.variable} ${manrope.variable} ${styles.root}`}>
      <div className="stage">
        <div className="frame">
          <input type="checkbox" id="menu" className="menu-toggle" aria-label="Menu" />
          <header className="nav">
            <Link className="brand" href="/" aria-label="DocLens home">
              <svg className="mark" viewBox="0 0 34 34" aria-hidden="true"><circle cx="17" cy="17" r="17" fill="#9C86CE" /><circle cx="17" cy="17" r="8.6" fill="#FFFFFF" /><circle cx="17" cy="17" r="3.7" fill="#151519" /></svg>
              <span className="wordmark">DocLens</span>
            </Link>
            <nav className="links" aria-label="Primary">
              <Link href="/ask">Ask</Link><Link href="/docs">Documents</Link><Link href="/compare">Compare</Link><Link href="/graph">Graph</Link><Link href="/eval">Evaluation</Link>
              <a href="/api/swagger">API</a><a href="https://github.com/enol5423" target="_blank" rel="noreferrer">GitHub</a>
            </nav>
            <Link className="cta" href="/space"><span>Get Started</span></Link>
            <label className="burger" htmlFor="menu" aria-hidden="true"><svg viewBox="0 0 17 12"><rect y="2" width="17" height="1.7" rx=".85" /><rect y="8.3" width="17" height="1.7" rx=".85" /></svg></label>
          </header>
          <div className="sheet"><div className="sheet-clip"><nav className="sheet-panel" aria-label="Mobile">
            <Link href="/space">Space</Link><Link href="/ask">Ask</Link><Link href="/docs">Documents</Link><Link href="/compare">Compare</Link><Link href="/graph">Graph</Link><Link href="/eval">Evaluation</Link>
            <a href="/api/swagger">API</a><a href="https://github.com/enol5423" target="_blank" rel="noreferrer">GitHub</a><Link className="sheet-cta" href="/space">Get Started</Link>
          </nav></div></div>
          <section className={styles.hero} aria-labelledby="home-title">
            <div className={styles.content}>
              <header className={styles.intro}>
                <h1 id="home-title">Your research,<span>connected.</span></h1>
                <p className={styles.lead}>Bring your documents together.<br />Find the ideas that connect them.</p>
                <p className={styles.description}>Explore papers, drafts, and notes in one space. Ask a question, follow the citations, and return to the exact page behind an answer.</p>
              </header>
              <Link className={styles.start} href={!error && docs.length === 0 ? "/space#library-sync" : "/space"}>
                <svg className={styles.folder} viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7ZM12 10v6m-3-3h6" /></svg>
                <span><strong>{!error && docs.length === 0 ? "Add documents" : "Open workspace"}</strong><span>{error ? "Reconnect to your research space." : docs.length ? "Pick up where your research left off." : "Bring your sources into DocLens."}</span></span>
                <svg className={styles.arrow} viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h12m-5-5 5 5-5 5" /></svg>
              </Link>
              <nav className={styles.shortcuts} aria-label="Explore your workspace">
                <Link href="/docs">Explore the library</Link>
                <Link href="/ask">Ask a question<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 15 15 5M5 5h10v10" /></svg></Link>
              </nav>
              <footer className={styles.libraryStatus}>
                <p>{error ? "Your workspace is temporarily unavailable." : docs.length ? `${docs.length} ${docs.length === 1 ? "document" : "documents"} in ${collections} ${collections === 1 ? "collection" : "collections"}` : "Start with a folder of papers, drafts, or notes."}</p>
              </footer>
            </div>
          </section>
          <footer className="proof">
            <p className="by">Built with</p>
            <div className="logos">
              <svg style={{ "--lw": 96.84 } as React.CSSProperties} viewBox="0 0 97 33" role="img" aria-label="Docling"><text x="0" y="25" fontSize="30" textLength="96" lengthAdjust="spacingAndGlyphs">Docling</text></svg>
              <svg style={{ "--lw": 67.29 } as React.CSSProperties} viewBox="0 0 68 33" role="img" aria-label="Qwen"><text x="0" y="25" fontSize="30" textLength="67" lengthAdjust="spacingAndGlyphs">Qwen</text></svg>
              <svg style={{ "--lw": 88.68 } as React.CSSProperties} viewBox="0 0 89 33" role="img" aria-label="FastAPI"><text x="0" y="25" fontSize="27" textLength="88" lengthAdjust="spacingAndGlyphs">FastAPI</text></svg>
            </div>
          </footer>
        </div>
      </div>
    </div>
  );
}


