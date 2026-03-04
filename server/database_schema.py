"""
ArangoDB Schema & Queries for Connection Review System

This document defines the database structure and queries needed
to support the LLM ensemble connection review workflow.
"""

# ===========================================================================
# COLLECTIONS
# ===========================================================================

"""
1. llm_proposed_edges (Edge Collection)
   - Stores connections suggested by the LLM ensemble
   - Each edge awaits user review before being promoted to production
   
   Schema:
   {
       _key: "edge_<timestamp>_<random>",
       _from: "artifacts/<node_id>",  // Source node
       _to: "artifacts/<node_id>",     // Target node
       
       // LLM Suggestion Data
       relationship_type: "uses|depends_on|calls|etc",
       confidence: 0.75,  // 0.0 to 1.0
       llm_reasoning: "Why the LLM thinks they're connected",
       llm_model: "claude-sonnet-4|gpt-4|ensemble",
       llm_ensemble_votes: [
           { model: "claude-sonnet-4", vote: "uses", confidence: 0.8 },
           { model: "gpt-4", vote: "uses", confidence: 0.7 }
       ],
       
       // Review Status
       status: "pending_review|approved|rejected|modified|skipped",
       
       // Review Data (populated after user review)
       reviewed_by: "user_id",
       reviewed_at: "2024-11-20T10:30:00Z",
       review_decision: "approve|reject|modify",
       review_feedback: "User's explanation",
       corrected_relationship: "depends_on",  // Only if modified
       
       // Metadata
       created_at: "2024-11-19T08:00:00Z",
       created_by: "llm_ensemble",
       batch_id: "batch_20241119_001",  // For tracking ensemble runs
       
       // Additional context
       co_occurrence_count: 5,  // How often they appear together in logs
       temporal_proximity: 0.9,  // How close in time they typically occur
       semantic_similarity: 0.65,  // Embedding similarity score
   }

2. llm_review_history (Document Collection)
   - Tracks all reviews for analytics and LLM training
   
   Schema:
   {
       _key: "review_<timestamp>",
       connection_id: "edge_xxx",
       original_relationship: "uses",
       llm_confidence: 0.75,
       
       user_decision: "approve|reject|modify",
       corrected_relationship: "depends_on",  // If modified
       user_feedback: "Actually depends on, not just uses",
       
       reviewed_by: "user_id",
       reviewed_at: "2024-11-20T10:30:00Z",
       review_duration_seconds: 45,  // Time spent on review
       
       // For training analysis
       was_correct: true|false,
       confidence_bucket: "high|medium|low",
       cluster_cross: true|false,  // Was it a cross-cluster connection?
   }

3. llm_training_feedback (Document Collection)
   - Aggregated feedback for improving the LLM ensemble
   
   Schema:
   {
       _key: "feedback_<date>",
       date: "2024-11-20",
       
       // Accuracy metrics
       total_reviews: 50,
       approved_count: 35,
       rejected_count: 10,
       modified_count: 5,
       
       accuracy_by_confidence: {
           "high": { correct: 30, total: 32, accuracy: 0.94 },
           "medium": { correct: 5, total: 12, accuracy: 0.42 },
           "low": { correct: 0, total: 6, accuracy: 0.0 }
       },
       
       accuracy_by_relationship: {
           "uses": { correct: 15, total: 20, accuracy: 0.75 },
           "depends_on": { correct: 12, total: 15, accuracy: 0.80 },
           // etc...
       },
       
       // Common mistakes
       common_misclassifications: [
           { 
               predicted: "uses",
               actual: "depends_on",
               count: 5,
               example_ids: ["edge_001", "edge_023"]
           }
       ],
       
       // Model performance
       model_performance: {
           "claude-sonnet-4": { accuracy: 0.85, count: 25 },
           "gpt-4": { accuracy: 0.78, count: 25 }
       }
   }
"""

# ===========================================================================
# KEY QUERIES
# ===========================================================================

# ---------------------------------------------------------------------------
# 1. Fetch Pending Connections (for review UI)
# ---------------------------------------------------------------------------

FETCH_PENDING_CONNECTIONS = """
FOR edge IN llm_proposed_edges
    FILTER edge.status == 'pending_review'
    
    // Get full node details
    LET source = DOCUMENT(edge._from)
    LET target = DOCUMENT(edge._to)
    
    // Sort by confidence (low first) to handle dubious cases first
    SORT edge.confidence ASC
    
    LIMIT @limit
    
    RETURN {
        id: edge._key,
        source_node: {
            id: source._key,
            label: source.label,
            type: source.type,
            cluster: source.cluster,
            description: source.description,
            importance: source.importance,
            metadata: source.metadata
        },
        target_node: {
            id: target._key,
            label: target.label,
            type: target.type,
            cluster: target.cluster,
            description: target.description,
            importance: target.importance,
            metadata: target.metadata
        },
        proposed_relationship: edge.relationship_type,
        confidence: edge.confidence,
        reasoning: edge.llm_reasoning,
        llm_model: edge.llm_model,
        created_at: edge.created_at
    }
"""

# ---------------------------------------------------------------------------
# 2. Approve Connection (move to production)
# ---------------------------------------------------------------------------

APPROVE_CONNECTION = """
FOR edge IN llm_proposed_edges
    FILTER edge._key == @connection_id
    
    // Update status
    UPDATE edge WITH {
        status: 'approved',
        reviewed_by: @reviewed_by,
        reviewed_at: @reviewed_at,
        review_decision: 'approve',
        review_feedback: @feedback
    } IN llm_proposed_edges
    
    // Copy to production edges collection
    LET new_edge = INSERT {
        _from: edge._from,
        _to: edge._to,
        relationship_type: edge.relationship_type,
        weight: edge.confidence,
        source: 'llm_approved',
        approved_at: @reviewed_at,
        original_llm_edge_id: edge._key,
        metadata: {
            llm_reasoning: edge.llm_reasoning,
            llm_model: edge.llm_model,
            llm_confidence: edge.confidence
        }
    } INTO edges OPTIONS { keepNull: false }
    
    RETURN new_edge
"""

# ---------------------------------------------------------------------------
# 3. Modify Connection (correct relationship type)
# ---------------------------------------------------------------------------

MODIFY_CONNECTION = """
FOR edge IN llm_proposed_edges
    FILTER edge._key == @connection_id
    
    // Update with correction
    UPDATE edge WITH {
        status: 'modified',
        reviewed_by: @reviewed_by,
        reviewed_at: @reviewed_at,
        review_decision: 'modify',
        review_feedback: @feedback,
        original_relationship: edge.relationship_type,
        corrected_relationship: @corrected_relationship
    } IN llm_proposed_edges
    
    // Copy to production with corrected relationship
    LET new_edge = INSERT {
        _from: edge._from,
        _to: edge._to,
        relationship_type: @corrected_relationship,
        weight: edge.confidence * 0.9,  // Slight penalty for requiring correction
        source: 'llm_corrected',
        approved_at: @reviewed_at,
        original_llm_edge_id: edge._key,
        metadata: {
            original_llm_suggestion: edge.relationship_type,
            llm_reasoning: edge.llm_reasoning,
            llm_model: edge.llm_model,
            llm_confidence: edge.confidence,
            user_correction: @corrected_relationship,
            correction_reason: @feedback
        }
    } INTO edges OPTIONS { keepNull: false }
    
    RETURN new_edge
"""

# ---------------------------------------------------------------------------
# 4. Reject Connection
# ---------------------------------------------------------------------------

REJECT_CONNECTION = """
FOR edge IN llm_proposed_edges
    FILTER edge._key == @connection_id
    
    UPDATE edge WITH {
        status: 'rejected',
        reviewed_by: @reviewed_by,
        reviewed_at: @reviewed_at,
        review_decision: 'reject',
        review_feedback: @feedback
    } IN llm_proposed_edges
    
    RETURN NEW
"""

# ---------------------------------------------------------------------------
# 5. Get Review Statistics
# ---------------------------------------------------------------------------

GET_REVIEW_STATS = """
LET pending = LENGTH(
    FOR e IN llm_proposed_edges
        FILTER e.status == 'pending_review'
        RETURN 1
)

LET reviewed_breakdown = (
    FOR e IN llm_proposed_edges
        FILTER e.status IN ['approved', 'rejected', 'modified']
        COLLECT status = e.status WITH COUNT INTO count
        RETURN { status, count }
)

LET total_reviewed = SUM(
    FOR item IN reviewed_breakdown
        RETURN item.count
)

LET approved = FIRST(
    FOR item IN reviewed_breakdown
        FILTER item.status == 'approved'
        RETURN item.count
) || 0

LET rejected = FIRST(
    FOR item IN reviewed_breakdown
        FILTER item.status == 'rejected'
        RETURN item.count
) || 0

LET modified = FIRST(
    FOR item IN reviewed_breakdown
        FILTER item.status == 'modified'
        RETURN item.count
) || 0

LET avg_confidence = AVG(
    FOR e IN llm_proposed_edges
        FILTER e.status == 'pending_review'
        RETURN e.confidence
)

LET accuracy_rate = total_reviewed > 0 
    ? (approved + modified) / total_reviewed 
    : 0

RETURN {
    total_pending: pending,
    total_reviewed: total_reviewed,
    approved_count: approved,
    rejected_count: rejected,
    modified_count: modified,
    accuracy_rate: accuracy_rate,
    avg_confidence: avg_confidence
}
"""

# ---------------------------------------------------------------------------
# 6. Get Connections by Confidence Bucket (for prioritized review)
# ---------------------------------------------------------------------------

GET_CONNECTIONS_BY_CONFIDENCE = """
FOR edge IN llm_proposed_edges
    FILTER edge.status == 'pending_review'
    
    LET confidence_bucket = (
        edge.confidence >= 0.8 ? 'high' :
        edge.confidence >= 0.6 ? 'medium' :
        'low'
    )
    
    FILTER confidence_bucket == @bucket
    
    LET source = DOCUMENT(edge._from)
    LET target = DOCUMENT(edge._to)
    
    SORT edge.confidence DESC
    
    LIMIT @limit
    
    RETURN {
        id: edge._key,
        source_node: KEEP(source, '_key', 'label', 'type', 'cluster'),
        target_node: KEEP(target, '_key', 'label', 'type', 'cluster'),
        proposed_relationship: edge.relationship_type,
        confidence: edge.confidence,
        reasoning: edge.llm_reasoning
    }
"""

# ---------------------------------------------------------------------------
# 7. Track Review History (for analytics)
# ---------------------------------------------------------------------------

INSERT_REVIEW_HISTORY = """
INSERT {
    connection_id: @connection_id,
    original_relationship: @original_relationship,
    llm_confidence: @llm_confidence,
    llm_model: @llm_model,
    
    user_decision: @user_decision,
    corrected_relationship: @corrected_relationship,
    user_feedback: @user_feedback,
    
    reviewed_by: @reviewed_by,
    reviewed_at: @reviewed_at,
    
    // Computed fields
    was_correct: @user_decision IN ['approve'],
    confidence_bucket: (
        @llm_confidence >= 0.8 ? 'high' :
        @llm_confidence >= 0.6 ? 'medium' :
        'low'
    ),
    
    _key: CONCAT('review_', DATE_ISO8601(DATE_NOW()))
} INTO llm_review_history
"""

# ---------------------------------------------------------------------------
# 8. Generate Daily Training Report
# ---------------------------------------------------------------------------

GENERATE_DAILY_TRAINING_REPORT = """
LET today = DATE_FORMAT(DATE_NOW(), '%yyyy-%mm-%dd')

LET reviews_today = (
    FOR review IN llm_review_history
        FILTER DATE_FORMAT(review.reviewed_at, '%yyyy-%mm-%dd') == today
        RETURN review
)

LET total_reviews = LENGTH(reviews_today)

LET accuracy_by_confidence = (
    FOR review IN reviews_today
        COLLECT bucket = review.confidence_bucket
        AGGREGATE 
            correct = SUM(review.was_correct ? 1 : 0),
            total = COUNT()
        RETURN {
            bucket: bucket,
            correct: correct,
            total: total,
            accuracy: total > 0 ? correct / total : 0
        }
)

LET accuracy_by_relationship = (
    FOR review IN reviews_today
        COLLECT rel = review.original_relationship
        AGGREGATE
            correct = SUM(review.was_correct ? 1 : 0),
            total = COUNT()
        RETURN {
            relationship: rel,
            correct: correct,
            total: total,
            accuracy: total > 0 ? correct / total : 0
        }
)

LET common_mistakes = (
    FOR review IN reviews_today
        FILTER review.user_decision == 'modify'
        COLLECT 
            predicted = review.original_relationship,
            actual = review.corrected_relationship
        WITH COUNT INTO mistake_count
        SORT mistake_count DESC
        LIMIT 5
        RETURN {
            predicted: predicted,
            actual: actual,
            count: mistake_count
        }
)

INSERT {
    _key: CONCAT('feedback_', today),
    date: today,
    total_reviews: total_reviews,
    accuracy_by_confidence: accuracy_by_confidence,
    accuracy_by_relationship: accuracy_by_relationship,
    common_misclassifications: common_mistakes,
    generated_at: DATE_ISO8601(DATE_NOW())
} INTO llm_training_feedback
OPTIONS { overwriteMode: "replace" }
"""

# ===========================================================================
# SAMPLE PYTHON INTEGRATION
# ===========================================================================

"""
# Example of how to use these queries in your Python backend:

from arango import ArangoClient
from datetime import datetime

class ConnectionReviewDB:
    def __init__(self, db):
        self.db = db
    
    def get_pending_connections(self, limit=100):
        cursor = self.db.aql.execute(
            FETCH_PENDING_CONNECTIONS,
            bind_vars={'limit': limit}
        )
        return list(cursor)
    
    def approve_connection(self, connection_id, reviewed_by, feedback=None):
        self.db.aql.execute(
            APPROVE_CONNECTION,
            bind_vars={
                'connection_id': connection_id,
                'reviewed_by': reviewed_by,
                'reviewed_at': datetime.utcnow().isoformat(),
                'feedback': feedback
            }
        )
    
    def modify_connection(self, connection_id, corrected_relationship, 
                         reviewed_by, feedback=None):
        self.db.aql.execute(
            MODIFY_CONNECTION,
            bind_vars={
                'connection_id': connection_id,
                'corrected_relationship': corrected_relationship,
                'reviewed_by': reviewed_by,
                'reviewed_at': datetime.utcnow().isoformat(),
                'feedback': feedback
            }
        )
    
    def reject_connection(self, connection_id, reviewed_by, feedback=None):
        self.db.aql.execute(
            REJECT_CONNECTION,
            bind_vars={
                'connection_id': connection_id,
                'reviewed_by': reviewed_by,
                'reviewed_at': datetime.utcnow().isoformat(),
                'feedback': feedback
            }
        )
    
    def get_review_stats(self):
        cursor = self.db.aql.execute(GET_REVIEW_STATS)
        return next(cursor)
    
    def generate_daily_report(self):
        self.db.aql.execute(GENERATE_DAILY_TRAINING_REPORT)

# Usage:
client = ArangoClient(hosts='http://localhost:8529')
db = client.db('protograph', username='root', password='password')
review_db = ConnectionReviewDB(db)

# Get pending connections
pending = review_db.get_pending_connections(limit=50)

# Approve a connection
review_db.approve_connection(
    connection_id='edge_001',
    reviewed_by='kane',
    feedback='Correct - test script does use this keyword'
)
"""

# ===========================================================================
# INDICES FOR PERFORMANCE
# ===========================================================================

"""
Create these indices for optimal query performance:

// On llm_proposed_edges
db.llm_proposed_edges.ensureIndex({ 
    type: "persistent", 
    fields: ["status", "confidence"] 
});

db.llm_proposed_edges.ensureIndex({ 
    type: "persistent", 
    fields: ["status", "created_at"] 
});

db.llm_proposed_edges.ensureIndex({ 
    type: "persistent", 
    fields: ["batch_id"] 
});

// On llm_review_history
db.llm_review_history.ensureIndex({ 
    type: "persistent", 
    fields: ["reviewed_at"] 
});

db.llm_review_history.ensureIndex({ 
    type: "persistent", 
    fields: ["connection_id"] 
});

db.llm_review_history.ensureIndex({ 
    type: "persistent", 
    fields: ["user_decision", "confidence_bucket"] 
});
"""