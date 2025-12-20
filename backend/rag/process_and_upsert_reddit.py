"""
Process and upsert Reddit posts to vector store.
"""
import json
import logging
from typing import List, Dict, Any
import uuid
from openai import OpenAI
import os
from rag.vectorstore import vector_store
logger = logging.getLogger(__name__)
from qdrant_client.models import PointStruct

DETAILS_EXTRACTION_PROMPT = f"""

You are an expert in extracting the most important insights from Reddit posts and replies.

You are provided with a post in a JSON format.
There are 3 data levels:
- Level 1: post
- Level 2: thread
- Level 3: reply

The JSON contains a post with multiple threads, and each thread may contain multiple replies.

Your goal is to identify the key issue discussed across the post and all replies, provide a detailed description of the discussion, and extract problems, pains, topics, solutions, emotional signals, and the inferred ICP role of the users.

INSTRUCTIONS:

1. Review the JSON carefully.
2. Extract all relevant text from the "selftext" and "body" fields across post, threads, and replies.
3. Identify the primary discussion type (e.g., "technical", "human resource", "cry for help", "incident analysis", etc.).
4. Determine the overall tone of the conversation.
5. Provide a list of keywords and domain-specific terms used in the conversation.

IMPORTANT - PAIN, EMOTION & PRACTITIONER LANGUAGE EXTRACTION (HIGH PRIORITY):

In addition to technical summarization, you MUST explicitly extract raw language that indicates:

- Pain points (loss of control, lack of visibility, unknown access, security risk, operational stress, fear of compromise)
- Emotional signals (confusion, anxiety, urgency, frustration, suspicion, distrust)
- Trigger moments (unexpected behavior, anomaly detection, activity that “should not happen”)
- Practitioner language that reflects real-world thinking rather than polished explanations

Focus especially on:
- Questions expressing uncertainty or concern
- First-person statements indicating responsibility or pressure
- Sentences describing unexplained access, hidden behavior, or lack of attribution
- Informal or emotionally charged phrasing

Preserve original wording as much as possible.
Do NOT normalize or rewrite these phrases into generic or marketing language.

6. Return the following structured keys in the output:

- 'summary': 1-2 sentences describing the core problem, pain, topic, or solution
- 'detailed_description': up to 2000 characters explaining the discussion in detail
- 'type': one of ["problem", "pain", "solution", "key_topic"]
- 'citation': an exact sentence copied verbatim from the source text
- 'citation_start_time': the timestamp when that sentence begins (if not available, return null)
- 'ICP_role': inferred role of the primary participants (e.g., Network Engineer, Security Engineer, SOC Analyst, DevOps)
- 'tone': overall tone of the discussion
- 'classification': classification of the conversation type
- 'key_issues': list of the main technical or operational issues identified

ADDITIONAL REQUIRED KEYS (CRITICAL FOR DOWNSTREAM RAG & MARKETING USE):

- 'pain_phrases': array of short, verbatim quotes that express pain, fear, stress, or uncertainty
- 'emotional_triggers': array describing what triggered concern or urgency in the discussion
- 'buyer_language': array of raw practitioner phrases that could be reused directly in marketing or sales messaging
- 'implicit_risks': array of risks implied by the users, even if not stated explicitly (e.g., breach risk, compliance exposure, unauthorized access)

FORMAT REQUIREMENTS:

- Return ONLY a JSON array
- No explanations, no intro text, no markdown
- Do not include emojis
- Do not include fields that were not requested
- Do not leave 'pain_phrases' or 'buyer_language' empty if the discussion contains concern, uncertainty, or risk

conversation_json:
                {{conversation_json}}
"""



def clean_comments_json(posts_json):
    if len(posts_json) == 0:
        return posts_json

    # extract only the interesting keys
    for post in posts_json:
        if len(post) == 0:
            continue

        data = post[0].get("data")
        post_data = data.get("children")[0].get("data")
        post_threads = post[1].get("data").get("children")
        threads = []

        for thread in post_threads:
            thread_data = thread.get("data")
            thread_replies = thread_data.get("replies")

            # `replies` is often an empty string when there are no replies; only
            # descend into it if it's a dict with a `data` field
            if isinstance(thread_replies, dict):
                thread_replies = thread_replies.get("data", {}).get("children", [])
            else:
                thread_replies = []

            clean_replies = []
            for reply in thread_replies:
                # Some reply objects are already the comment data; others may be
                # a Listing with `children`. Handle both safely.
                reply_data_obj = reply.get("data", {}) or {}
                children = reply_data_obj.get("children")
                if isinstance(children, list) and children and isinstance(children[0], dict):
                    reply_data = children[0].get("data", {}) or {}
                else:
                    reply_data = reply_data_obj or {}

                clean_reply = {
                    "body": reply_data.get("body"),
                    "author_fullname": reply_data.get("author_fullname"),
                    "date_created_utc": reply_data.get("created_utc"),
                    "url": "https://www.reddit.com" + reply_data.get("permalink"),
                    "ups": reply_data.get("ups"),
                }
                clean_replies.append(clean_reply)
                
            clean_thread = {
                "body": thread_data.get("body"),    
                "author_fullname": thread_data.get("author_fullname"),
                "date_created_utc": thread_data.get("created_utc"),
                "url": "https://www.reddit.com" + thread_data.get("permalink"),
                "ups": thread_data.get("ups"),
                "replies": clean_replies
                }
            threads.append(clean_thread)


        clean_post = {
                "title": post_data.get('title', 'N/A'),
                "id": post_data.get("id"),
                "selftext": post_data.get("selftext"),
                "thread_author": post_data.get("author"),  
                "date_created_utc": post_data.get("created_utc"),   
                "subreddit": post_data.get("subreddit"),
                "flair_text": post_data.get("link_flair_text"),
                "ups": post_data.get("ups"),
                "thread_url": "https://www.reddit.com" + post_data.get("permalink"),
                "score": post_data.get("score"),
                "threads": threads
        }
    return clean_post

def clean_and_split_comments(posts_json):
    if len(posts_json) == 0:
        return posts_json

    clean_posts = []
    # extract only the interesting keys
    for post in posts_json:
        if len(post) == 0:
            continue

        data = post[0].get("data")
        post_data = data.get("children")[0].get("data")
        post_threads = post[1].get("data").get("children")
        threads = []

        for thread in post_threads:
            thread_data = thread.get("data")
            thread_replies = thread_data.get("replies")

            # `replies` is often an empty string when there are no replies; only
            # descend into it if it's a dict with a `data` field
            if isinstance(thread_replies, dict):
                thread_replies = thread_replies.get("data", {}).get("children", [])
            else:
                thread_replies = []

            clean_replies = []
            for reply in thread_replies:
                # Some reply objects are already the comment data; others may be
                # a Listing with `children`. Handle both safely.
                reply_data_obj = reply.get("data", {}) or {}
                children = reply_data_obj.get("children")
                if isinstance(children, list) and children and isinstance(children[0], dict):
                    reply_data = children[0].get("data", {}) or {}
                else:
                    reply_data = reply_data_obj or {}

                clean_reply = {
                    "body": reply_data.get("body"),
                    "author_fullname": reply_data.get("author_fullname"),
                    "date_created_utc": reply_data.get("created_utc"),
                    "url": "https://www.reddit.com" + reply_data.get("permalink"),
                    "ups": reply_data.get("ups"),
                }
                clean_replies.append(clean_reply)
                
            clean_thread = {
                "body": thread_data.get("body"),    
                "author_fullname": thread_data.get("author_fullname"),
                "date_created_utc": thread_data.get("created_utc"),
                "url": "https://www.reddit.com" + thread_data.get("permalink"),
                "ups": thread_data.get("ups"),
                "replies": clean_replies
                }
            threads.append(clean_thread)


        clean_post = {
                "title": post_data.get('title', 'N/A'),
                "id": post_data.get("id"),
                "selftext": post_data.get("selftext"),
                "thread_author": post_data.get("author"),  
                "date_created_utc": post_data.get("created_utc"),   
                "subreddit": post_data.get("subreddit"),
                "flair_text": post_data.get("link_flair_text"),
                "ups": post_data.get("ups"),
                "thread_url": "https://www.reddit.com" + post_data.get("permalink"),
                "score": post_data.get("score"),
                "threads": threads
        }
        clean_posts.append(clean_post)

    return clean_posts


def extract_summary_for_post(prompt):
    response = OpenAI(api_key=os.getenv("OPENAI_API_KEY")).chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=2000
    )
    return response.choices[0].message.content


def convert_comments_to_detailed(post, prompt):
    try:
        summary_str = extract_summary_for_post(prompt.format(conversation_json=json.dumps(post)))
        summary_json = json.loads(summary_str)
        if len(summary_json) > 1:
            logger.info("Summary is not a single json object")
            logger.info(summary_json)
            
        #print(summary_json)
        post.update(summary_json[0])
        #logger.info(summary_json)
        return post

    except Exception as e:
        #logger.error(f"Error processing {post}: {e}")
        logger.error(f"Error processing {post["id"]}: {e}")

def upsert_posts(collection_name: str, posts: List[Dict[str, Any]], text_fields: List[str]):

    points = []
    text_chunks = []

    for text_field in text_fields:
        for post in posts:
            # remove threads array and all children from post
            post.pop("threads", None)
            post["doc_type"] = "reddit_post"
            #check if the text_field is in chunk keys
            if text_field in post.keys():
                text_chunks.append(vector_store.chunking(text=post[text_field], model="nltk"))  

            for text_chunk in text_chunks:
                for item in text_chunk:
                    print("upserting item:", item)
                    vector_store.upsert_document(collection_name=collection_name, text=item, metadata=post)


def process_and_upsert_reddit(
    data: List[Dict[str, Any]],
    collection_name: str
) -> int:
    """
    Process Reddit posts data and upsert to vector store.
    
    Args:
        data: List of Reddit post dictionaries from JSON file
        collection_name: Target Qdrant collection name
    
    Returns:
        Number of records successfully upserted
    """
    detailed_posts = []
    clean_posts = clean_and_split_comments(data)
    for post in clean_posts[:1]:
        print(post["id"])

        detailed_post = convert_comments_to_detailed(post, DETAILS_EXTRACTION_PROMPT)
        detailed_posts.append(detailed_post)
        #store detailed json in a S3 bucket
        #s3_client = boto3.client('s3')
        #s3_client.put_object(Bucket='your-bucket-name', Key=f'detailed_posts/{post["id"]}.json', Body=json.dumps(detailed))
       
        reddit_text_fields = ["title","selftext","detailed_description", "discussion_description", "summary"]

    upsert_posts(collection_name, detailed_posts, reddit_text_fields)

    return len(detailed_posts)

