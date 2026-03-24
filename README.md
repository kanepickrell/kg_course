flowchart TD

    %% ── INGESTION UI ──
    subgraph INGESTION["Ingestion UI"]
        WIZ["Module Wizard\nLibraryModuleWizard.tsx"]
        GEN["Generic Ingest\nDataIngestionModal.tsx"]
    end

    %% ── ONTOLOGY MANAGER ──
    subgraph ONT_UI["Ontology Manager UI"]
        ONT["OntologyManager.tsx\nCRUD · TTL editor"]
    end

    %% ── FASTAPI BACKEND ──
    subgraph BACKEND["FastAPI · main.py"]
        TTL_EP["POST /api/ingest/ttl\nCORS proxy → GraphDB"]
        INGEST_EP["POST /api/ingest/commit\nvalidate · types"]
        ONT_EP["GET/POST /api/ontology/*\nontology_graphdb.py"]
        GRAPH_EP["GET /graph\nnodes + edges JSON"]
        NL_EP["POST /api/query/natural\nnl_query_engine.py · + /subgraph"]
        CONN_EP["GET /connections/pending\nPOST /connections/review\nllm_edge_suggestions.json"]
        LIB_EP["GET /api/library-modules\nGraphDB + payload merge"]
    end

    %% ── INGESTION CORE ──
    subgraph INGEST_CORE["ingestion_core.py"]
        IC["OWL type lookup\nSKOS taxonomy resolve"]
        RR["Relationship rules engine\npost-commit edge creation"]
    end

    %% ── ONTOLOGY LAYER ──
    subgraph ONTOLOGY["Ontology layer"]
        GDB_ADAPTER["GraphDB adapter\ngraph_db.py · ontology_graphdb.py"]
        OWL["OWL classes\nLibraryModule · TTP · ExecutionPlan…"]
        SKOS["SKOS taxonomies\ntactics · risk levels · owners"]
    end

    %% ── STORAGE ──
    subgraph STORAGE["Storage"]
        GRAPHDB["GraphDB · localhost:7200\nRDF triples · SPARQL · SHACL on write"]
        PAYLOAD["Payload files\n./data/payloads/*.json"]
    end

    %% ── PLUGIN LAYER ──
    subgraph PLUGINS["Plugin layer"]
        REGISTRY["PluginRegistry\nbase.py · endpoints.py\n/api/plugins/*"]
        OP_ROUTE["GET /api/plugins/operator/modules\nplugin_router.py · GraphDB + payload merge"]
    end

    %% ── CONSUMERS ──
    subgraph CONSUMERS["Consumers"]
        EXPLORER["Graph Explorer\nD3 force graph"]
        CONSOLE["Intelligence Console\nNL query · subgraph viz"]
        REVIEW["Connection Review\nLLM edge approval UI"]
        LUMEN["Lumen campaign canvas · TTP library"]
    end

    %% ── WRITE PATH ──
    WIZ -->|"TTL"| TTL_EP
    WIZ -.->|"payload file"| PAYLOAD
    GEN --> INGEST_EP

    ONT <-->|"read / write"| ONT_EP
    ONT_EP --> GDB_ADAPTER

    TTL_EP -->|"raw Turtle"| GRAPHDB

    INGEST_EP --> IC
    IC --> RR
    IC --> GDB_ADAPTER
    RR --> GDB_ADAPTER

    GDB_ADAPTER --> OWL
    GDB_ADAPTER --> SKOS
    OWL --> GRAPHDB
    SKOS --> GRAPHDB
    GDB_ADAPTER -.->|"operational detail"| PAYLOAD

    %% ── READ PATH ──
    GRAPHDB --> GRAPH_EP
    GRAPHDB --> NL_EP
    GRAPHDB --> CONN_EP
    GRAPHDB --> LIB_EP
    GRAPHDB --> OP_ROUTE
    PAYLOAD -.->|"merged on request"| LIB_EP
    PAYLOAD -.->|"merged on request"| OP_ROUTE

    LIB_EP --> REGISTRY
    REGISTRY --> OP_ROUTE

    CONN_EP -->|"approved → edge insert"| GRAPHDB

    %% ── CONSUME ──
    GRAPH_EP --> EXPLORER
    GRAPH_EP --> LUMEN
    NL_EP --> CONSOLE
    CONN_EP --> REVIEW
    OP_ROUTE --> LUMEN

    %% ── STYLES ──
    classDef ingestion  fill:#1D9E75,stroke:#0F6E56,color:#085041
    classDef ontui      fill:#AFA9EC,stroke:#534AB7,color:#26215C
    classDef backend    fill:#D3D1C7,stroke:#5F5E5A,color:#2C2C2A
    classDef core       fill:#7F77DD,stroke:#534AB7,color:#EEEDFE
    classDef ontology   fill:#CECBF6,stroke:#534AB7,color:#26215C
    classDef storage    fill:#FAC775,stroke:#854F0B,color:#412402
    classDef plugin     fill:#AFA9EC,stroke:#534AB7,color:#26215C
    classDef consumer   fill:#F0997B,stroke:#993C1D,color:#4A1B0C

    class WIZ,GEN ingestion
    class ONT ontui
    class TTL_EP,INGEST_EP,ONT_EP,GRAPH_EP,NL_EP,CONN_EP,LIB_EP backend
    class IC,RR core
    class GDB_ADAPTER,OWL,SKOS ontology
    class GRAPHDB,PAYLOAD storage
    class REGISTRY,OP_ROUTE plugin
    class EXPLORER,CONSOLE,REVIEW,LUMEN consumer