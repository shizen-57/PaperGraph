import GraphView from "@/components/GraphView";
import Notice from "@/components/Notice";
import { getGraph } from "@/lib/api";

export default async function GraphPage() {
  let graph;
  try {
    graph = await getGraph();
  } catch (e) {
    return <Notice title="Backend offline" icon="⚠">{e instanceof Error ? e.message : String(e)}</Notice>;
  }
  return (
    <>
      <div className="page-head">
        <h1>Relations</h1>
        <p>How the documents in the space connect. Every edge is built from evidence you can inspect: a version name, a reference list entry, closest passages, or a mention.</p>
      </div>
      {graph.nodes.length === 0 ? <Notice title="No documents yet">Run the ingest from the Space page first.</Notice> : <GraphView graph={graph} />}
    </>
  );
}
