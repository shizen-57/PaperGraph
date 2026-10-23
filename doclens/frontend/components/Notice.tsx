export default function Notice({ title, children, icon = "ⓘ" }: { title: string; children: React.ReactNode; icon?: string }) {
  return (
    <div className="glass notice" role="status">
      <span style={{ fontSize: 22, lineHeight: 1 }} aria-hidden="true">{icon}</span>
      <div>
        <h2>{title}</h2>
        <p>{children}</p>
      </div>
    </div>
  );
}
