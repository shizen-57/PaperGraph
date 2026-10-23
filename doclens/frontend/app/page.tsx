import HeroHome from "@/components/HeroHome";
import { ApiError, getDocuments } from "@/lib/api";
import type { DocumentSummary } from "@/lib/types";

export default async function Home() {
  let docs: DocumentSummary[] = [];
  let error: string | null = null;
  try {
    docs = await getDocuments();
  } catch (e) {
    error = e instanceof ApiError ? e.message : String(e);
  }
  return <HeroHome docs={docs} error={error} />;
}
