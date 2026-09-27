function Group({ title, items }) {
  return (
    <div className="struct-group">
      <h4>
        {title} ({items.length})
      </h4>
      {items.length ? (
        <div className="chips">
          {items.map((item, i) => (
            <span className="chip mono" key={i}>
              {item}
            </span>
          ))}
        </div>
      ) : (
        <p className="empty-note">None detected.</p>
      )}
    </div>
  );
}

export default function StructureView({ structure }) {
  const s = structure || {};
  return (
    <div>
      <Group title="Imports" items={s.imports || []} />
      <Group title="Classes" items={s.classes || []} />
      <Group title="Functions" items={s.functions || []} />
    </div>
  );
}
