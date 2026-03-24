flowchart TD

    %% ── INGESTION ──
    subgraph INGESTION["🔵 Ingestion"]
        WIZ["Module Wizard\nLibraryModuleWizard.tsx"]
        GEN["Generic Ingest\nDataIngestionModal.tsx"]
        UPL["Bulk Upload\nDataUpload.tsx"]
        ONT["Ontology Manager\nOntologyManager.tsx"]
    end

    %% ── BACKEND ──
    subgraph BACKEND["⚙️ FastAPI Backend · main.py"]
        API["POST /api/ingest/commit\nPOST /api/ingest/ttl\nGET  /api/ingest/types"]
    end

    %% ── ONTOLOGY LAYER ──
    subgraph ONTOLOGY["🟣 Ontology Layer"]
        OWL["OWL Classes\nLibraryModule, TTP, ExecutionPlan…"]
        SKOS["SKOS Taxonomies\nTactics, risk levels, owners"]
        REL["Relationship Types\nLEADS_TO, CONTAINS, REFERENCES…"]
        SHACL["SHACL Shapes\nField validation on commit"]
        GDB_ADAPTER["GraphDB Adapter\ngraph_db.py · ingestion_core.py"]
    end

    %% ── STORAGE ──
    subgraph STORAGE["🟡 Storage"]
        GRAPHDB["GraphDB · localhost:7200\nRDF triples · SPARQL"]
        PAYLOAD["Payload Files\n./data/payloads/*.json"]
    end

    %% ── API ENDPOINTS ──
    subgraph ENDPOINTS["⚪ Serve Layer"]
        GRAPH_EP["GET /graph\nnodes + edges JSON"]
        NL_EP["GET /api/query/natural\nNL → SPARQL"]
        OP_EP["GET /operator/modules\nPlugin data route"]
    end

    %% ── CONSUMERS ──
    subgraph CONSUMERS["🔴 Consumers"]
        EXPLORER["Graph Explorer\nD3 force graph"]
        CONSOLE["Intelligence Console\nNL query + subgraph viz"]
        LUMEN["Lumen\nCampaign canvas"]
        OPERATOR["Operator Plugin\nTTP library"]
    end

    %% ── FLOWS ──
    WIZ     --> API
    GEN     --> API
    UPL     --> API
    ONT     --> API

    API     --> OWL
    API     --> SKOS
    API     --> REL
    API     --> SHACL

    OWL     --> GDB_ADAPTER
    SKOS    --> GDB_ADAPTER
    REL     --> GDB_ADAPTER
    SHACL   --> GDB_ADAPTER

    GDB_ADAPTER --> GRAPHDB
    GDB_ADAPTER --> PAYLOAD

    GRAPHDB --> GRAPH_EP
    GRAPHDB --> NL_EP
    GRAPHDB --> OP_EP

    GRAPH_EP  --> EXPLORER
    GRAPH_EP  --> LUMEN
    NL_EP     --> CONSOLE
    OP_EP     --> OPERATOR

    PAYLOAD   -.->|on-demand| LUMEN

    %% ── STYLES ──
    classDef ingestion  fill:#1D9E75,stroke:#0F6E56,color:#E1F5EE
    classDef backend    fill:#888780,stroke:#5F5E5A,color:#F1EFE8
    classDef ontology   fill:#7F77DD,stroke:#534AB7,color:#EEEDFE
    classDef storage    fill:#BA7517,stroke:#854F0B,color:#FAEEDA
    classDef endpoint   fill:#5F5E5A,stroke:#444441,color:#F1EFE8
    classDef consumer   fill:#D85A30,stroke:#993C1D,color:#FAECE7

    class WIZ,GEN,UPL,ONT ingestion
    class API backend
    class OWL,SKOS,REL,SHACL,GDB_ADAPTER ontology
    class GRAPHDB,PAYLOAD storage
    class GRAPH_EP,NL_EP,OP_EP endpoint
    class EXPLORER,CONSOLE,LUMEN,OPERATOR consumer