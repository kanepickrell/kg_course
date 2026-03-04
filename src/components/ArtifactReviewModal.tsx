const ArtifactReviewModal = ({ assessment, onApprove }) => {
  return (
    <div className="neo-card">
      <h2>Review: Library Module</h2>
      
      {/* Metadata Preview */}
      <section>
        <h3>📊 What Goes in the Graph (Metadata)</h3>
        <div className="metadata-preview">
          {assessment.metadata_fields.map(field => (
            <div key={field}>
              <strong>{field}:</strong> {truncate(data[field])}
            </div>
          ))}
        </div>
        <p className="text-muted">
          Size: {assessment.metadata_size} bytes
        </p>
      </section>
      
      {/* Payload Preview */}
      <section>
        <h3>📦 What Gets Stored at URL (Payload)</h3>
        <div className="payload-preview">
          <code>{assessment.suggested_url_pattern}</code>
          <p>Fields: {assessment.payload_fields.join(', ')}</p>
          <p>Size: {assessment.payload_size} bytes</p>
        </div>
      </section>
      
      {/* LLM Reasoning */}
      <section>
        <h3>🤖 Why This Split?</h3>
        <p>{assessment.reasoning}</p>
      </section>
      
      <div className="actions">
        <button onClick={() => onApprove(assessment)}>
          ✓ Approve & Create
        </button>
        <button onClick={() => onEdit(assessment)}>
          ✎ Edit Schema
        </button>
      </div>
    </div>
  );
};