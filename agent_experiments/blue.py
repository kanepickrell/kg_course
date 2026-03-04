import asyncio
import random
from datetime import datetime
import json

def print_something(object: str)-> bool:
    pass
    # len()
    # open()
    # json.loads()
    # json.dumps()
    # datetime.now()
    # dict.get()
    # try/except
    # os.path.exists('somefile.txt')  ... os.path.join('folder', 'somefile.txt')

def is_pdf(filename: str)-> bool:
    # root, extension = filename.split('.')
    # extension.lower()
    # if extension == "pdf":
    #     return True

    return filename.lower().endswith('.pdf')

def count_true_probes(probes: dict):
    count = 0
    for key in probes:
        if probes[key] == True:
            count += 1
    return count

def check_for_tags(classification_dict: dict):
    key_att = classification_dict.get("keyAttributes", {})
    tags = key_att.get("tags", [])

    if tags and len(tags) > 0:
        return len(tags)

    return "No tags"


async def process_document(doc_id: str) -> dict:
    """
    Simulate processing a single document.
    This represents calling an LLM, extracting text, etc.
    """
    # Simulate processing time (0.5 to 2 seconds)
    processing_time = random.uniform(0.5, 2.0)
    print(f"🔄 Processing {doc_id}...")
    
    await asyncio.sleep(processing_time)
    
    print(f"✅ Finished {doc_id} in {processing_time:.2f}s")
    
    return {
        "doc_id": doc_id,
        "status": "completed",
        "processing_time": processing_time
    }


async def batch_process_documents(doc_ids: list) -> dict:
    """
    
    Process all documents concurrently and return results.
    
    Should return:
    {
        "results": [list of result dicts],
        "total_time": float,
        "processed_count": int
    }
    """
    starttime = datetime.now()
    print(starttime)

    tasks = [process_document(doc_id) for doc_id in doc_ids]
    print(tasks)

    results = await asyncio.gather(*tasks)
    print(results)

    endtime = datetime.now()
    print(endtime)

    processed_count = len(results)
    total_time = (endtime - starttime).total_seconds()

    return {
        "results": results,
        "total_time": total_time,
        "processed_count": processed_count
    }

def analyze_feedback_log(log: str):
#     {
#     "total_reviews": 5,
#     "approved": 3,
#     "modified": 1,
#     "rejected": 1,
#     "approval_rate": 0.6,  # approved / total
#     "avg_response_time": 6000.0,  # in milliseconds
#     "confidence_breakdown": {
#         "high": 3,
#         "medium": 1,
#         "low": 1
#     }
# }

    total_reviews = 0
    approved = 0
    modified = 0
    rejected = 0
    approval_rate = 0
    total_response_time = 0
    avg_response_time = 0
    confidence_counts= {"high": 0, "medium": 0, "low": 0}

    lines = log.strip().split("\n")
    
    # feedback = log.get("user_feedback", {})
    # decision = feedback.get("approved", [])
    # print(len(decision))

    for line in lines:
        if not line.strip(): 
            continue

        entry = json.loads(line)

        feedback = entry.get("user_feedback", {})
        decision = feedback.get("decision", "")
        response = feedback.get("response_time_ms", 0)
        confidence = feedback.get("user_confidence", "")

        if decision == "approve":
            approved += 1
        elif decision == "modified":
            modified += 1
        elif decision == "rejected":
            rejected += 1
        
        total_response_time += response

        total_reviews += 1

        if confidence in confidence_counts:
            confidence_counts[confidence] += 1
    
    approval_rate = approved / total_reviews if total_reviews > 0 else 0
    avg_response_time = total_response_time / total_reviews if total_reviews > 0 else 0


    return {
        "total_reviews": total_reviews,
        "approved": approval_rate,
        "modified": modified,
        "rejected": rejected,
        "approval_rate": approval_rate,  
        "avg_response_time": avg_response_time, 
        "confidence_breakdown": confidence_counts
        }


if __name__ == "__main__":
    # print(is_pdf("matcha.pdf"))

    probe_results = {
        "has_title": True,
        "has_date": False,
        "has_author": True,
        "has_metadata": True,
        "has_images": False,
        "has_references": True
    }

    classification = {
        "artifactId": "doc_123",
        "confidence": 0.87,
        "keyAttributes": {
            "tags": ["urgent", "financial"]
        }
    }
    

    sample_log = """
    {"artifact_id": "doc_1", "user_feedback": {"decision": "approve", "response_time_ms": 3000, "user_confidence": "high"}}
    {"artifact_id": "doc_2", "user_feedback": {"decision": "modify", "response_time_ms": 12000, "user_confidence": "medium"}}
    {"artifact_id": "doc_3", "user_feedback": {"decision": "approve", "response_time_ms": 2500, "user_confidence": "high"}}
    {"artifact_id": "doc_4", "user_feedback": {"decision": "reject", "response_time_ms": 8000, "user_confidence": "low"}}
    {"artifact_id": "doc_5", "user_feedback": {"decision": "approve", "response_time_ms": 4500, "user_confidence": "high"}}
    """

    results = analyze_feedback_log(sample_log)

    print("📊 Feedback Analysis:")
    print(f"  Total: {results['total_reviews']}")
    print(f"  Approved: {results['approved']} ({results['approval_rate']:.1%})")
    print(f"  Avg response time: {results['avg_response_time']:.0f}ms")
    print(f"  Confidence: {results['confidence_breakdown']}")