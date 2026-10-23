import Link from "next/link";
import Notice from "@/components/Notice";
import { ApiError, getDocuments, groupByFolder } from "@/lib/api";
import styles from "./Documents.module.css";

export default async function DocsPage() {
  let docs;
  try {
    docs = await getDocuments();
  } catch (e) {
    return <Notice title="Backend offline" icon="⚠">{e instanceof ApiError ? e.message : String(e)}</Notice>;
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div><h1>Documents{docs.length > 0 && <span className={styles.count}>{docs.length}</span>}</h1>
        <p>Browse your sources by collection. Open a document to explore its claims and citations.</p></div>
        {docs.length > 0 && <Link className={styles.action} href="/space#library-sync">Add documents<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 4v12M4 10h12" /></svg></Link>}
      </header>

      {docs.length === 0 ? (
        <section className={styles.empty} aria-labelledby="empty-library-title">
          <div className={styles.emptyContent}>
            <svg className={styles.folder} viewBox="0 0 48 48" aria-hidden="true"><path d="M7 17V11a3 3 0 0 1 3-3h9l4 5h14a3 3 0 0 1 3 3v21a3 3 0 0 1-3 3H10a3 3 0 0 1-3-3V17ZM17 25h14M24 18v14" /></svg>
            <h2 id="empty-library-title">Add your first documents</h2>
            <p>Bring your papers, drafts, and notes into one library. Sync a folder from your workspace to get started.</p>
            <Link className={styles.action} href="/space#library-sync">Add documents<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h12m-5-5 5 5-5 5" /></svg></Link>
            <span className={styles.formats}>PDF, Markdown, and plain text</span>
          </div>
          <footer>Documents are organized by their source folder. Citations link back to the original.</footer>
        </section>
      ) : (
        Object.entries(groupByFolder(docs)).map(([folder, ds]) => (
          <section key={folder} className="folder-group">
            <h2 className="folder-name">{folder}/ <span>{ds.length}</span></h2>
            <div className="doc-grid">
              {ds.map((d) => (
                <Link key={d.id} href={`/docs/${encodeURIComponent(d.id)}`} className="glass doc-card">
                  <div className="tags">
                    {d.year && <span className="badge">{d.year}</span>}
                    {d.version_label && <span className="badge">{d.version_label}</span>}
                    <span className="badge">{d.file_type === "pdf" ? `${d.pages} ${d.pages === 1 ? "page" : "pages"}` : d.file_type}</span>
                    {d.lang === "ja" && <span className="badge">日本語</span>}
                  </div>
                  <h2>{d.title}</h2>
                  <div className="verify">
                    {d.claims > 0 ? (
                      <>
                        <div className="meter" aria-hidden="true"><span style={{ width: `${Math.round((d.verified_claims / d.claims) * 100)}%` }} /></div>
                        <span>{d.verified_claims} of {d.claims} claims verified · {d.relations} relations</span>
                      </>
                    ) : (
                      <span>{d.relations} relations</span>
                    )}
                  </div>
                  <span className="open">Open →</span>
                </Link>
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
