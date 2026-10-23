import AskWorkspace from "@/components/AskWorkspace";
import Notice from "@/components/Notice";
import { getDocuments } from "@/lib/api";

type Props = { searchParams: Promise<{ q?: string; folder?: string }> };

export default async function AskPage({ searchParams }: Props) {
  const { q, folder } = await searchParams; // handed over by the homepage ask bar
  try {
    return <AskWorkspace docs={await getDocuments()} initialQuestion={q} initialFolder={folder} />;
  } catch (e) {
    return <Notice title="Backend offline" icon="⚠">{e instanceof Error ? e.message : String(e)}</Notice>;
  }
}
