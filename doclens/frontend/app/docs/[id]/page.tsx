import Link from "next/link";
import DocView from "@/components/DocView";
import Notice from "@/components/Notice";
import { ApiError, getDocument, getDocuments } from "@/lib/api";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ q?: string; el?: string }> };

export default async function DocPage({ params, searchParams }: Props) {
  const { id } = await params;
  const { q, el } = await searchParams; // el: an element to highlight on open (from a citation elsewhere)
  try {
    const [doc, all] = await Promise.all([getDocument(id), getDocuments()]);
    const titles = Object.fromEntries(all.map((d) => [d.id, d.title]));
    return <DocView doc={doc} titles={titles} initialElement={el} initialQuestion={q} />;
  } catch (e) {
    const notFound = e instanceof ApiError && e.status === 404;
    return (
      <>
        <Notice title={notFound ? "Document not found" : "Backend offline"} icon="⚠">
          {e instanceof ApiError ? e.message : String(e)}
        </Notice>
        <p style={{ marginTop: 16 }}>
          <Link className="badge" href="/docs">← All documents</Link>
        </p>
      </>
    );
  }
}
