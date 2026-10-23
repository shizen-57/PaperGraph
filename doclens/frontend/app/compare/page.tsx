import CompareView from "@/components/CompareView";
import Notice from "@/components/Notice";
import { getDocuments, getGraph } from "@/lib/api";

type Props = { searchParams: Promise<{ a?: string; b?: string }> };

export default async function ComparePage({ searchParams }: Props) {
  const { a, b } = await searchParams;
  let docs, graph;
  try {
    [docs, graph] = await Promise.all([getDocuments(), getGraph()]);
  } catch (e) {
    return <Notice title="Backend offline" icon="⚠">{e instanceof Error ? e.message : String(e)}</Notice>;
  }
  if (docs.length < 2) return <Notice title="Not enough documents">Comparing needs at least two documents in the space.</Notice>;
  // default: the first detected draft pair (v2 supersedes v1), else the first two documents
  const pair = graph.edges.find((e) => e.type === "supersedes");

  return (
    <>
      <div className="page-head">
        <h1>Compare</h1>
        <p>Passages are matched across the two documents. Changed ones get a one-line summary with a quote from each side, and both quotes are checked against their source.</p>
      </div>
      <CompareView docs={docs} initialA={a ?? pair?.target_id ?? docs[0].id} initialB={b ?? pair?.source_id ?? docs[1].id} />
    </>
  );
}
