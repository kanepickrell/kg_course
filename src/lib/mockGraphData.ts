export const generateAdvancedMockData = () => {
    const nodes = [
        // ========== CONTENT DEV CLUSTER ==========
        // Phase P1 - Initial Requirements
        { id: "cd-dlo", label: "DLO Requirements", type: "requirement", cluster: "content_dev", importance: 0.95, size: 55 },
        { id: "cd-aor", label: "Area of Operation", type: "requirement", cluster: "content_dev", importance: 0.75, size: 42 },
        { id: "cd-apt", label: "APT Profile (APT29)", type: "profile", cluster: "content_dev", importance: 0.9, size: 50 },
        { id: "cd-os", label: "Target OS Config", type: "requirement", cluster: "content_dev", importance: 0.7, size: 40 },

        // Phase P2 - Planning
        { id: "cd-tiger", label: "Tiger Team", type: "coordination", cluster: "content_dev", importance: 0.85, size: 48 },

        // Phase D1 - Research
        { id: "cd-intel", label: "Intel IPOE", type: "research", cluster: "content_dev", importance: 0.8, size: 45 },
        { id: "cd-mpn", label: "Mission Partner Network", type: "research", cluster: "content_dev", importance: 0.7, size: 40 },
        { id: "cd-narrative", label: "Scenario Narrative", type: "design", cluster: "content_dev", importance: 0.85, size: 48 },

        // Phase D2 - Scenario Design
        { id: "cd-intel-design", label: "Intel Package", type: "design", cluster: "content_dev", importance: 0.8, size: 45 },

        // Phase D3 - Development
        { id: "cd-blue-hb", label: "Blue Team Handbook", type: "handbook", cluster: "content_dev", importance: 0.9, size: 50 },
        { id: "cd-white-hb", label: "White Cell Handbook", type: "handbook", cluster: "content_dev", importance: 0.9, size: 50 },
        { id: "cd-intel-inject", label: "Intel Injects", type: "content", cluster: "content_dev", importance: 0.75, size: 42 },

        // Phase D4 - Assembly
        { id: "cd-assembly", label: "Handbook Assembly", type: "delivery", cluster: "content_dev", importance: 0.8, size: 45 },

        // Phase E1 - Delivery
        { id: "cd-delivery", label: "Content Delivery", type: "delivery", cluster: "content_dev", importance: 0.85, size: 48 },

        // ========== RANGE CLUSTER ==========
        // Phase D2 - Range Inputs
        { id: "rng-topo", label: "Network Topology", type: "infrastructure", cluster: "range", importance: 0.9, size: 50 },
        { id: "rng-creds", label: "Credentials Vault", type: "security", cluster: "range", importance: 0.85, size: 48 },
        { id: "rng-weapons", label: "Weapon System Topo", type: "infrastructure", cluster: "range", importance: 0.8, size: 45 },

        // Phase D3 - Environment Setup
        { id: "rng-vm-setup", label: "VM Configuration", type: "infrastructure", cluster: "range", importance: 0.85, size: 48 },
        { id: "rng-network", label: "Network Build", type: "infrastructure", cluster: "range", importance: 0.9, size: 50 },

        // Phase E1 - Execution Support
        { id: "rng-monitoring", label: "Range Monitoring", type: "operations", cluster: "range", importance: 0.8, size: 45 },
        { id: "rng-clone", label: "Clone Management", type: "operations", cluster: "range", importance: 0.85, size: 48 },
        { id: "rng-validation", label: "Dead Range Validation", type: "testing", cluster: "range", importance: 0.8, size: 45 },

        // ========== OPFOR CLUSTER ==========
        // Phase D2 - OPFOR Planning
        { id: "opfor-obj", label: "Adversarial Objectives", type: "planning", cluster: "opfor", importance: 0.9, size: 50 },
        { id: "opfor-tools", label: "Tool Selection", type: "planning", cluster: "opfor", importance: 0.85, size: 48 },
        { id: "opfor-campaign", label: "Campaign Plan", type: "planning", cluster: "opfor", importance: 0.9, size: 50 },
        { id: "opfor-mitre", label: "MITRE ATT&CK TTPs", type: "planning", cluster: "opfor", importance: 0.85, size: 48 },
        { id: "opfor-iocs", label: "IOC Generation", type: "artifact", cluster: "opfor", importance: 0.8, size: 45 },

        // Phase D3 - Execution Planning
        { id: "opfor-sequence", label: "Attack Sequence", type: "execution", cluster: "opfor", importance: 0.9, size: 50 },

        // Phase E1 - Live Execution
        { id: "opfor-live", label: "Live Range Execution", type: "execution", cluster: "opfor", importance: 0.95, size: 55 },
        { id: "opfor-cert", label: "Certification", type: "validation", cluster: "opfor", importance: 0.9, size: 50 },

        // Phase D4 - Documentation
        { id: "opfor-reddoc", label: "Red Team Docs", type: "documentation", cluster: "opfor", importance: 0.8, size: 45 },
        { id: "opfor-handbook", label: "Red Handbook Entry", type: "documentation", cluster: "opfor", importance: 0.85, size: 48 },
        { id: "opfor-confluence", label: "Confluence Docs", type: "documentation", cluster: "opfor", importance: 0.75, size: 42 },
        { id: "opfor-opnotes", label: "Operation Notes", type: "documentation", cluster: "opfor", importance: 0.7, size: 40 },

        // ========== AUTOMATION CLUSTER ==========
        // Phase D1 - Capability Building
        { id: "auto-sliver", label: "Sliver C2 Library", type: "development", cluster: "automation", importance: 0.85, size: 48 },
        { id: "auto-cobalt", label: "CobaltStrike Library", type: "development", cluster: "automation", importance: 0.85, size: 48 },

        // Phase P1 - Requirements
        { id: "auto-req", label: "Automation Requirements", type: "requirement", cluster: "automation", importance: 0.8, size: 45 },

        // Phase D2 - Build Execution
        { id: "auto-ttp", label: "TTP Automation Scripts", type: "script", cluster: "automation", importance: 0.9, size: 50 },
        { id: "auto-listener", label: "C2 Listener Setup", type: "script", cluster: "automation", importance: 0.85, size: 48 },

        // Phase D3 - Testing
        { id: "auto-test", label: "Automation Testing", type: "testing", cluster: "automation", importance: 0.85, size: 48 },

        // Phase E1 - Delivery
        { id: "auto-playbook", label: "Attack Playbook", type: "delivery", cluster: "automation", importance: 0.9, size: 50 },
        { id: "auto-beacon", label: "Beacon Automation", type: "script", cluster: "automation", importance: 0.8, size: 45 },
        { id: "auto-exfil", label: "Exfiltration Scripts", type: "script", cluster: "automation", importance: 0.85, size: 48 },
    ];

    const edges = [
        // ========== CONTENT DEV INTERNAL FLOWS ==========
        // Requirements flow
        { source: "cd-dlo", target: "cd-apt", weight: 0.9, type: "defines" },
        { source: "cd-dlo", target: "cd-aor", weight: 0.8, type: "specifies" },
        { source: "cd-dlo", target: "cd-os", weight: 0.85, type: "determines" },

        // Planning phase
        { source: "cd-tiger", target: "cd-dlo", weight: 0.9, type: "coordinates" },

        // Research phase
        { source: "cd-apt", target: "cd-intel", weight: 0.9, type: "informs" },
        { source: "cd-intel", target: "cd-mpn", weight: 0.8, type: "contextualizes" },
        { source: "cd-intel", target: "cd-narrative", weight: 0.85, type: "drives" },
        { source: "cd-mpn", target: "cd-narrative", weight: 0.75, type: "shapes" },

        // Design phase
        { source: "cd-narrative", target: "cd-intel-design", weight: 0.9, type: "guides" },

        // Development phase
        { source: "cd-intel-design", target: "cd-blue-hb", weight: 0.9, type: "populates" },
        { source: "cd-intel-design", target: "cd-white-hb", weight: 0.85, type: "populates" },
        { source: "cd-intel-design", target: "cd-intel-inject", weight: 0.8, type: "creates" },

        // Assembly and delivery
        { source: "cd-blue-hb", target: "cd-assembly", weight: 0.95, type: "compiles" },
        { source: "cd-white-hb", target: "cd-assembly", weight: 0.95, type: "compiles" },
        { source: "cd-assembly", target: "cd-delivery", weight: 0.9, type: "publishes" },

        // ========== RANGE INTERNAL FLOWS ==========
        { source: "rng-topo", target: "rng-network", weight: 0.95, type: "defines" },
        { source: "rng-creds", target: "rng-vm-setup", weight: 0.9, type: "secures" },
        { source: "rng-weapons", target: "rng-network", weight: 0.85, type: "integrates" },
        { source: "rng-vm-setup", target: "rng-monitoring", weight: 0.8, type: "enables" },
        { source: "rng-network", target: "rng-validation", weight: 0.9, type: "validates" },
        { source: "rng-validation", target: "rng-clone", weight: 0.85, type: "precedes" },

        // ========== OPFOR INTERNAL FLOWS ==========
        { source: "opfor-obj", target: "opfor-tools", weight: 0.9, type: "drives" },
        { source: "opfor-tools", target: "opfor-campaign", weight: 0.85, type: "enables" },
        { source: "opfor-campaign", target: "opfor-mitre", weight: 0.9, type: "maps" },
        { source: "opfor-mitre", target: "opfor-iocs", weight: 0.85, type: "generates" },
        { source: "opfor-campaign", target: "opfor-sequence", weight: 0.95, type: "details" },
        { source: "opfor-sequence", target: "opfor-live", weight: 0.95, type: "executes" },
        { source: "opfor-live", target: "opfor-cert", weight: 0.9, type: "validates" },
        { source: "opfor-live", target: "opfor-reddoc", weight: 0.85, type: "documents" },
        { source: "opfor-reddoc", target: "opfor-handbook", weight: 0.9, type: "feeds" },
        { source: "opfor-reddoc", target: "opfor-confluence", weight: 0.85, type: "publishes" },
        { source: "opfor-live", target: "opfor-opnotes", weight: 0.8, type: "records" },

        // ========== AUTOMATION INTERNAL FLOWS ==========
        { source: "auto-sliver", target: "auto-cobalt", weight: 0.7, type: "complements" },
        { source: "auto-req", target: "auto-ttp", weight: 0.9, type: "specifies" },
        { source: "auto-cobalt", target: "auto-listener", weight: 0.85, type: "implements" },
        { source: "auto-ttp", target: "auto-test", weight: 0.95, type: "validates" },
        { source: "auto-listener", target: "auto-test", weight: 0.85, type: "validates" },
        { source: "auto-test", target: "auto-playbook", weight: 0.9, type: "finalizes" },
        { source: "auto-ttp", target: "auto-beacon", weight: 0.85, type: "includes" },
        { source: "auto-ttp", target: "auto-exfil", weight: 0.8, type: "includes" },

        // ========== CROSS-TEAM COLLABORATION ==========

        // Content Dev → Range
        { source: "cd-narrative", target: "rng-topo", weight: 0.9, type: "requires" },
        { source: "cd-blue-hb", target: "rng-creds", weight: 0.85, type: "references" },
        { source: "cd-intel-design", target: "rng-weapons", weight: 0.8, type: "defines" },
        { source: "cd-delivery", target: "rng-validation", weight: 0.85, type: "triggers" },

        // Content Dev → OPFOR
        { source: "cd-apt", target: "opfor-obj", weight: 0.95, type: "defines" },
        { source: "cd-narrative", target: "opfor-campaign", weight: 0.9, type: "guides" },
        { source: "cd-intel-design", target: "opfor-mitre", weight: 0.85, type: "specifies" },
        { source: "cd-tiger", target: "opfor-campaign", weight: 0.8, type: "coordinates" },

        // Content Dev → Automation
        { source: "cd-tiger", target: "auto-req", weight: 0.85, type: "coordinates" },

        // OPFOR → Automation
        { source: "opfor-tools", target: "auto-req", weight: 0.95, type: "requests" },
        { source: "opfor-mitre", target: "auto-ttp", weight: 0.9, type: "specifies" },
        { source: "opfor-sequence", target: "auto-playbook", weight: 0.95, type: "integrates" },
        { source: "opfor-campaign", target: "auto-listener", weight: 0.85, type: "requires" },

        // Automation → OPFOR
        { source: "auto-playbook", target: "opfor-live", weight: 0.95, type: "enables" },
        { source: "auto-beacon", target: "opfor-live", weight: 0.9, type: "supports" },
        { source: "auto-exfil", target: "opfor-live", weight: 0.85, type: "supports" },

        // Automation → Range
        { source: "auto-playbook", target: "rng-monitoring", weight: 0.85, type: "executes-on" },
        { source: "auto-test", target: "rng-validation", weight: 0.8, type: "validates-on" },

        // Range → OPFOR
        { source: "rng-validation", target: "opfor-live", weight: 0.95, type: "enables" },
        { source: "rng-clone", target: "opfor-cert", weight: 0.85, type: "preserves" },
        { source: "rng-monitoring", target: "opfor-opnotes", weight: 0.8, type: "informs" },

        // Final documentation collaboration
        { source: "opfor-reddoc", target: "cd-assembly", weight: 0.8, type: "contributes" },
        { source: "auto-playbook", target: "opfor-reddoc", weight: 0.85, type: "documents" },
        { source: "rng-clone", target: "opfor-reddoc", weight: 0.75, type: "artifacts" },
    ];

    return { nodes, edges };
};

// Export a ready instance for reuse
export const mockGraphData = generateAdvancedMockData();