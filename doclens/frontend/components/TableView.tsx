import type { Table } from "@/lib/types";

export default function TableView({ table }: { table: Table }) {
  return (
    <div className="table-scroll"><table className="tbl">
      <thead>
        <tr>{table.header.map((h, i) => <th key={i}>{h}</th>)}</tr>
      </thead>
      <tbody>
        {table.rows.map((r, i) => (
          <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>
        ))}
      </tbody>
    </table></div>
  );
}
