// lib/powerbiSync.ts
// Real-time sync utility for ProtoGraph → Power BI pipeline

export type ChangeType =
    | "node_selection"
    | "node_updated"
    | "node_created"
    | "node_deleted"
    | "edge_created"
    | "edge_deleted"
    | "gem_saved"
    | "graph_filtered";

interface SyncOptions {
    debounceMs?: number;
    enabled?: boolean;
}

const DEFAULT_OPTIONS: SyncOptions = {
    debounceMs: 1000, // Wait 1 second before notifying
    enabled: true
};

let debounceTimer: NodeJS.Timeout | null = null;

/**
 * Notify Power BI that ProtoGraph data has changed
 * Power BI will then refresh its dataset to pull latest metrics
 */
export const notifyPowerBIUpdate = async (
    changeType: ChangeType,
    affectedNodes?: string[],
    options: SyncOptions = DEFAULT_OPTIONS
) => {
    if (!options.enabled) {
        console.log("🔇 Power BI sync disabled");
        return;
    }

    // Debounce rapid updates
    if (debounceTimer) {
        clearTimeout(debounceTimer);
    }

    debounceTimer = setTimeout(async () => {
        try {
            const response = await fetch("http://127.0.0.1:8000/analytics/notify-update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    change_type: changeType,
                    affected_nodes: affectedNodes || [],
                    timestamp: new Date().toISOString()
                })
            });

            if (response.ok) {
                console.log(`✅ Power BI notified: ${changeType}`, affectedNodes);
            } else {
                console.warn(`⚠️ Power BI notification failed: ${response.status}`);
            }
        } catch (err) {
            // Fail silently - don't break ProtoGraph if Power BI is down
            console.warn("⚠️ Power BI not available:", err);
        }
    }, options.debounceMs);
};

/**
 * Test Power BI connection
 */
export const testPowerBIConnection = async (): Promise<boolean> => {
    try {
        const response = await fetch("http://127.0.0.1:8000/analytics/team-coupling-table");
        return response.ok;
    } catch {
        return false;
    }
};

/**
 * Manually trigger Power BI refresh
 * Useful for "Sync Now" buttons in UI
 */
export const triggerManualSync = async () => {
    console.log("🔄 Manual sync triggered");
    await notifyPowerBIUpdate("graph_filtered", [], { debounceMs: 0 });
};

/**
 * Hook for React components to use Power BI sync
 */
export const usePowerBISync = (enabled: boolean = true) => {
    const notify = (changeType: ChangeType, nodeIds?: string[]) => {
        notifyPowerBIUpdate(changeType, nodeIds, { enabled });
    };

    return {
        notify,
        testConnection: testPowerBIConnection,
        triggerSync: triggerManualSync
    };
};