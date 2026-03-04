import { useState, useEffect } from "react";

export default function TestGraph() {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        fetch('http://localhost:8000/graph')
            .then(r => r.json())
            .then(d => {
                console.log('Got data:', d);
                setData(d);
            })
            .catch(e => {
                console.error('Error:', e);
                setError(e.message);
            });
    }, []);

    if (error) return <div>Error: {error}</div>;
    if (!data) return <div>Loading...</div>;

    return (
        <div>
            <h1>Test Graph</h1>
            <p>Nodes: {data.nodes?.length}</p>
            <p>Edges: {data.edges?.length}</p>
            <pre>{JSON.stringify(data, null, 2)}</pre>
        </div>
    );
}
```

Navigate to this page - does it load the data?

---

## 📊 What the Diagnostics Tell Us
```
✅ Root endpoint: 200
✅ Graph endpoint: 200
Nodes: 11
Edges: 10