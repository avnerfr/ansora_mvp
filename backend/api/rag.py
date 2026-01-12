from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import uuid
from datetime import datetime
import logging
import os
import tempfile
from pathlib import Path
import json

from db import get_db
from models import (
    User, Job, PromptTemplate,
    RAGProcessRequest, RAGProcessResponse,
    RAGResultResponse, SourceItem, PromptTemplateRequest, PromptTemplateResponse
)
from core.auth import get_current_user, get_cognito_groups_from_token
from rag.pipeline import process_rag, DEFAULT_TEMPLATE, _load_asset_type_rules_from_dynamodb
from rag.loader import load_document
from rag.agents import company_analysis_agent
from rag.s3_utils import get_latest_company_file, save_company_file, get_company_website
from rag.dynamodb_prompts import get_latest_prompt_template
import re
from core.config import settings
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/prompt-template", response_model=PromptTemplateResponse)
async def save_prompt_template(
    template_data: PromptTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save or update user's prompt template."""
    existing = db.query(PromptTemplate).filter(PromptTemplate.user_id == current_user.id).first()
    
    if existing:
        existing.template = template_data.template
        existing.updated_at = datetime.utcnow()
    else:
        existing = PromptTemplate(
            user_id=current_user.id,
            template=template_data.template
        )
        db.add(existing)
    
    db.commit()
    db.refresh(existing)
    
    return PromptTemplateResponse(template=existing.template)


@router.get("/prompt-template", response_model=PromptTemplateResponse)
async def get_prompt_template(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's prompt template or default."""
    template_record = db.query(PromptTemplate).filter(PromptTemplate.user_id == current_user.id).first()
    
    if template_record:
        return PromptTemplateResponse(template=template_record.template)
    else:
        return PromptTemplateResponse(template=DEFAULT_TEMPLATE)


@router.get("/prompt-template/default", response_model=PromptTemplateResponse)
async def get_default_prompt_template(
    current_user: User = Depends(get_current_user),
):
    """Get the default prompt template from prompts.py."""
    return PromptTemplateResponse(template=DEFAULT_TEMPLATE)


def _guess_file_type(filename: str) -> str:
    """Lightweight MIME type detection based on file extension."""
    ext = filename.lower().split('.')[-1]
    type_map = {
        'pdf': 'application/pdf',
        'txt': 'text/plain',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'doc': 'application/msword',
    }
    return type_map.get(ext, 'application/octet-stream')


@router.post("/upload-context")
async def upload_context_documents(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Upload temporary context documents.

    - Does NOT persist anything in the database.
    - Does NOT index anything in Qdrant.
    - Returns extracted text so the frontend can append it to the context box.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided",
        )

    results = []

    for file in files:
        extracted_text = None
        try:
            file_type = _guess_file_type(file.filename)

            # Write to a temporary file so our existing loaders (PDF, DOCX, TXT)
            # can operate on a filesystem path.
            suffix = Path(file.filename).suffix or ""
            fd, temp_path = tempfile.mkstemp(
                suffix=suffix,
                prefix=f"user_{current_user.id}_",
                dir=settings.STORAGE_PATH,
            )
            os.close(fd)

            try:
                with open(temp_path, "wb") as buffer:
                    content = await file.read()
                    buffer.write(content)

                documents = load_document(temp_path, file_type)

                # Combine original document text so the frontend can append it
                # directly into the context box.
                extracted_text = "\n\n".join(
                    d.page_content
                    for d in documents
                    if getattr(d, "page_content", None)
                )
            finally:
                # Best-effort cleanup of the temporary file.
                try:
                    os.remove(temp_path)
                except OSError:
                    logger.warning(f"Failed to delete temp file: {temp_path}")

            results.append(
                {
                    "filename": file.filename,
                    "file_type": file_type,
                    "status": "success",
                    "content_text": extracted_text,
                }
            )
        except Exception as e:
            logger.error(f"Error processing context file {file.filename}: {e}")
            results.append(
                {
                    "filename": file.filename,
                    "file_type": _guess_file_type(file.filename),
                    "status": f"error: {str(e)}",
                    "content_text": None,
                }
            )

    return results


@router.post("/process", response_model=RAGProcessResponse)
async def process_marketing_material(
    request: RAGProcessRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Process marketing material through RAG pipeline."""
    import uuid as uuid_lib
    request_id = str(uuid_lib.uuid4())[:8]
    logger.info(f"[Request {request_id}] POST /api/v1/rag/process - User: {current_user.email} (ID: {current_user.id})")
    
    # Validate inputs
    if not request.backgrounds:
        logger.warning("Validation error: No backgrounds provided")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one background must be selected"
        )
    
    # Check if user is administrator
    token = credentials.credentials
    groups = get_cognito_groups_from_token(token)
    is_administrator = 'Administrators' in groups
    logger.info(f"User is administrator: {is_administrator}")
    
    # Determine company name
    company_name = None
    if request.company:
        # Administrator selected company from dropdown
        company_name = request.company
        logger.info(f"Using company from request (admin): {company_name}")
    else:
        # Get company from Cognito groups (non-admin users)
        # Filter out Administrators group
        company_groups = [g for g in groups if g != 'Administrators']
        if company_groups:
            company_name = company_groups[0]  # Use first non-admin group
            logger.info(f"Using company from Cognito groups: {company_name}")
        else:
            logger.warning("No company found in Cognito groups and no company in request")
    
    # Get or generate company information
    company_details = None
    company_analysis = None
     
    if company_name:
        # Check S3 for existing company information (returns CompanyDetails object)
        company_details = get_latest_company_file(company_name)
        
        if company_details:
            # We have a CompanyDetails object - extract company_analysis string if needed for pipeline
            # For now, we'll pass the CompanyDetails object to the pipeline
            logger.info(f"Using existing company details for {company_name}")
        else:
            # Generate new company information
            logger.info(f"Generating new company information for {company_name}")
            company_website = get_company_website(company_name)
            try:
                company_analysis = company_analysis_agent(company_name, company_website)
           
                # Save to S3
                save_company_file(company_name, company_analysis)
                logger.info(f"Saved company information to S3 for {company_name}")
                
                # Load the newly saved file as CompanyDetails
                company_details = get_latest_company_file(company_name)
            except Exception as e:
                logger.error(f"Error generating company information: {e}")
                # Continue without company information rather than failing
    
    logger.info(
        f"Request validated - Backgrounds: {request.backgrounds}, "
        f"Text length: {len(request.marketing_text)}, "
        f"Asset Type: {request.asset_type}, ICP: {request.icp}, "
        f"Company: {company_name}"
    )
    
    # Get user's template or use override
    template = request.template_override
    if not template:
        template_record = db.query(PromptTemplate).filter(PromptTemplate.user_id == current_user.id).first()
        template = template_record.template if template_record else DEFAULT_TEMPLATE
        logger.info(f"Using {'custom' if template_record else 'default'} template")
    else:
        logger.info("Using template override from request")
    
    # Process RAG
    try:
        import traceback
        logger.info(f"[Request {request_id}] Calling RAG pipeline...")
        logger.debug(f"[Request {request_id}] Call stack: {''.join(traceback.format_stack()[-3:-1])}")
        refined_text, sources, retrieved_docs, final_prompt, email_content = await process_rag(
            user_id=current_user.id,
            backgrounds=request.backgrounds,
            marketing_text=request.marketing_text,
            asset_type=request.asset_type,
            icp=request.icp,
            template=template,
            company_name=company_name,
            company_details=company_details,
            is_administrator=is_administrator,
            request_id=request_id,  # Pass request_id to track duplicate calls
        )
        logger.info(f"✓ RAG pipeline completed - Output: {len(refined_text)} chars, Sources: {len(sources)}, Retrieved Docs: {len(retrieved_docs)}")
    except Exception as e:
        logger.error(f"✗ RAG pipeline failed: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing RAG: {str(e)}"
        )
    
    # Generate job ID
    job_id = str(uuid.uuid4())
    logger.info(f"Generated job_id: {job_id}")
    
    # Save job result
    try:
        job = Job(
            job_id=job_id,
            user_id=current_user.id,
            status="completed",
            refined_text=refined_text,
            sources=[s.model_dump() if hasattr(s, 'model_dump') else s for s in sources],
            retrieved_docs=retrieved_docs,
            final_prompt=final_prompt,
            email_content=email_content if is_administrator else None,  # Only store for administrators
            original_request=request.marketing_text,
            topics=request.backgrounds
        )
        db.add(job)
        db.commit()
        logger.info("✓ Job saved to database")
    except Exception as e:
        logger.error(f"✗ Failed to save job: {str(e)}", exc_info=True)
        raise
    
    logger.info(f"✓ Request completed successfully - job_id: {job_id}")
    return RAGProcessResponse(job_id=job_id)


@router.get("/results/{job_id}", response_model=RAGResultResponse)
async def get_results(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get RAG processing results."""
    job = db.query(Job).filter(Job.job_id == job_id).first()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    if job.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Convert sources from JSON to SourceItem objects
    sources = []
    try:
        for s in job.sources:
            if isinstance(s, dict):
                # Clean up any "Unknown" strings and convert to None
                cleaned_source = {}
                for key, value in s.items():
                    if value == "Unknown" or value == "unknown":
                        cleaned_source[key] = None
                    else:
                        cleaned_source[key] = value
                try:
                    sources.append(SourceItem(**cleaned_source))
                except Exception as e:
                    logger.warning(f"⚠ Failed to create SourceItem from {cleaned_source}: {str(e)}")
                    # Create a minimal valid SourceItem
                    sources.append(SourceItem(
                        filename=cleaned_source.get("filename", "Unknown"),
                        snippet=cleaned_source.get("snippet", ""),
                        score=cleaned_source.get("score", 0.0),
                        source=cleaned_source.get("source", "unknown")
                    ))
            else:
                sources.append(s)
    except Exception as e:
        logger.error(f"❌ Error processing sources: {type(e).__name__}: {str(e)}", exc_info=True)
        # Return empty sources list if there's an error
        sources = []
    
    # Check if current user is administrator for email_content
    token = credentials.credentials
    groups = get_cognito_groups_from_token(token)
    is_administrator = 'Administrators' in groups
    
    return RAGResultResponse(
        job_id=job.job_id,
        refined_text=job.refined_text,
        sources=sources,
        retrieved_docs=job.retrieved_docs or [],
        final_prompt=job.final_prompt,
        email_content=job.email_content if is_administrator else None,  # Only return for administrators
        original_request=job.original_request,
        topics=job.topics
    )


@router.get("/company-data/{company_name}")
async def get_company_data(
    company_name: str,
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get company data (target_audience and operational_pains) from S3.
    Returns data from CompanyDetails object.
    
    Args:
        company_name: Company name
        
    Returns:
        Dict with target_audience and operational_pains arrays
    """
    try:
        # Get company details from S3 as CompanyDetails object
        company_details = get_latest_company_file(company_name)
        
        if not company_details:
            logger.warning(f"No company information found for {company_name}, returning defaults")
            return {
                "target_audience": [
                    "Network & Security Operations",
                    "Application & Service Delivery",
                    "CIO",
                    "CISO",
                    "Risk and Compliance"
                ],
                "operational_pains": [
                    "Network visibility gaps during incidents",
                    "Configuration drift and compliance failures",
                    "Alert fatigue and false positives",
                    "Slow incident response times",
                    "Cloud security misconfigurations"
                ]
            }
        
        # Extract from CompanyDetails object - clean and simple
        target_audience = company_details.company_context.target_audience
        operational_pains = company_details.company_context.operational_pains
        
        logger.info(f"✓ Returning company data for {company_name}: "
                   f"{len(target_audience)} target audiences, "
                   f"{len(operational_pains)} operational pains")
        
        return {
            "target_audience": target_audience,
            "operational_pains": operational_pains
        }

    except Exception as e:
        logger.error(f"Error getting company data for {company_name}: {e}", exc_info=True)
        return {
            "target_audience": [
                "Network & Security Operations",
                "Application & Service Delivery",
                "CIO",
                "CISO",
                "Risk and Compliance"
            ],
            "operational_pains": [
                "Network visibility gaps during incidents",
                "Configuration drift and compliance failures",
                "Alert fatigue and false positives",
                "Slow incident response times",
                "Cloud security misconfigurations"
            ]
        }
            

@router.get("/asset-types")
async def get_asset_types(
    current_user: User = Depends(get_current_user),
):
    """
    Get available asset types from DynamoDB.
    Loads all templates starting with 'asset_template_' and returns the asset type names.
    
    Returns:
        Dict with asset_types array
    """
    try:
        # Load asset type rules from DynamoDB
        asset_rules = _load_asset_type_rules_from_dynamodb()
        
        # Get the asset type names (keys from the dictionary)
        asset_types = sorted(list(asset_rules.keys()))
        
        logger.info(f"✓ Returning {len(asset_types)} asset types from DynamoDB")
        
        return {
            "asset_types": asset_types
        }
    except Exception as e:
        logger.error(f"Error getting asset types: {e}", exc_info=True)
        # Return fallback asset types
        return {
            "asset_types": [
                "email",
                "one-pager",
                "landing-page",
                "blog",
                "blog-post",
                "linkedin-post"
            ]
        }


@router.get("/competitors/{company_name}")
async def get_competitors(
    company_name: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get competitors for a company from CompanyDetails in S3.
    
    Args:
        company_name: Company name
        
    Returns:
        Dict with competitors array
    """
    try:
        # Get company details from S3
        company_details = get_latest_company_file(company_name)
        
        if not company_details:
            logger.warning(f"No company information found for {company_name}")
            return {"competitors": []}
        
        # Extract competitors from CompanyDetails
        competitors = company_details.company_context.known_competitors
        
        logger.info(f"✓ Returning {len(competitors)} competitors for {company_name}")
        
        return {
            "competitors": competitors
        }
    except Exception as e:
        logger.error(f"Error getting competitors for {company_name}: {e}", exc_info=True)
        return {"competitors": []}


@router.post("/process-battle-cards", response_model=RAGProcessResponse)
async def process_battle_cards(
    request: RAGProcessRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Process battle cards through specialized pipeline.
    
    Uses:
    1. 'battle_cards_rag_build_template' for RAG build
    2. 'asset_template_battle-cards' for asset generation
    """
    import uuid as uuid_lib
    request_id = str(uuid_lib.uuid4())[:8]
    logger.info(f"[Request {request_id}] POST /api/v1/rag/process-battle-cards - User: {current_user.email} (ID: {current_user.id})")
    
    # Validate that we have a competitor selected (stored in backgrounds)
    if not request.backgrounds or not request.backgrounds[0]:
        logger.warning("Validation error: No competitor provided for battle cards")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Competitor must be selected for battle cards"
        )
    
    competitor = request.backgrounds[0]  # First item is the competitor
    
    # Check if user is administrator
    token = credentials.credentials
    groups = get_cognito_groups_from_token(token)
    is_administrator = 'Administrators' in groups
    logger.info(f"User is administrator: {is_administrator}")
    
    # Determine company name
    company_name = None
    if request.company:
        company_name = request.company
        logger.info(f"Using company from request (admin): {company_name}")
    else:
        company_groups = [g for g in groups if g != 'Administrators']
        if company_groups:
            company_name = company_groups[0]
            logger.info(f"Using company from Cognito groups: {company_name}")
    
    # Get company details
    company_details = None
    if company_name:
        company_details = get_latest_company_file(company_name)
        if not company_details:
            logger.info(f"Generating new company information for {company_name}")
            company_website = get_company_website(company_name)
            try:
                company_analysis = company_analysis_agent(company_name, company_website)
                save_company_file(company_name, company_analysis)
                company_details = get_latest_company_file(company_name)
            except Exception as e:
                logger.error(f"Error generating company information: {e}")
    
    logger.info(f"Battle Cards Request - Competitor: {competitor}, Company: {company_name}")
    
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage
        
        # Step 1: Get the RAG build template from DynamoDB
        rag_build_template_data = get_latest_prompt_template('battle_cards_rag_build_template')
        if not rag_build_template_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Battle cards RAG build template not found in DynamoDB"
            )
        
        rag_build_template = rag_build_template_data['template_body']
        logger.info(f"✓ Loaded battle_cards_rag_build_template from DynamoDB")
        
        # Step 2: Build the prompt for RAG build using the template
        # Replace placeholders in the template
        company_context = {}
        if company_details:
            company_context = {
                'company_name': company_details.company_context.company_name,
                'company_domain': company_details.company_context.company_domain,
                'self_described_positioning': company_details.company_context.self_described_positioning,
                'product_surface_names': company_details.company_context.product_surface_names,
                'typical_use_cases': company_details.company_context.typical_use_cases,
                'known_competitors': company_details.company_context.known_competitors,
                'target_audience': company_details.company_context.target_audience,
                'operational_pains': company_details.company_context.operational_pains,
            }
        
        # Prepare template variables
        # Note: icp is the user-selected target_audience from the dropdown
        # target_audience is the full list from company details (for reference)
        template_vars = {
            'competitor': competitor,
            'company_name': company_name or '',
            'company_domain': company_context.get('company_domain', ''),
            'self_described_positioning': company_context.get('self_described_positioning', ''),
            'target_audience': request.icp or '',  # User-selected target audience from dropdown
            'icp': request.icp or '',  # Same as target_audience (for backward compatibility)
            'user_provided_text': request.marketing_text or '',
        }
        
        logger.info(f"Battle Cards RAG Build - Template Variables:")
        logger.info(f"  Competitor: {competitor}")
        logger.info(f"  Company: {company_name}")
        logger.info(f"  Target Audience (from dropdown): {request.icp}")
        logger.info(f"  User Context: {len(request.marketing_text or '')} chars")
        
        rag_build_prompt = rag_build_template.format(**template_vars)
        
        # Step 3: Run the model with RAG build prompt
        logger.info("Running RAG build model for battle cards...")
        llm = ChatOpenAI(
            model_name="deepseek-ai/DeepSeek-V3.2",
            openai_api_key=settings.DEEPINFRA_API_KEY,
            base_url=settings.DEEPINFRA_API_BASE_URL,
            temperature=1.0,
        )
        
        rag_build_messages = [HumanMessage(content=rag_build_prompt)]
        rag_build_response = await llm.ainvoke(rag_build_messages)
        rag_build_result = rag_build_response.content
        
        logger.info(f"✓ RAG build completed: {len(rag_build_result)} chars")
        logger.info(f"RAG build result (search queries): {rag_build_result}")
        
        # Step 2: Use the RAG build result as search queries for Qdrant
        logger.info("Step 2: Retrieving buyer language insights from Qdrant...")
        
        from rag.vectorstore import vector_store
        import json
        
        # Parse the RAG build result - it should contain search queries
        # Split by newlines and clean up
        search_queries = [q.strip() for q in rag_build_result.split('\n') if q.strip() and not q.strip().startswith('#')]
        logger.info(f"Extracted {len(search_queries)} search queries from RAG build")
        
        # Determine collection name using the vectorstore's resolve method
        collection_name = "cybersecurity-summaries_1_0"  # Default
        if company_details:
            try:
                company_domain = company_details.company_context.company_domain
                collection_name = vector_store.resolve_collection_name(company_domain, "summaries_1_0")
                logger.info(f"✓ Resolved collection name: {collection_name} for domain: {company_domain}")
            except Exception as e:
                logger.warning(f"Could not resolve collection name, using default: {e}")
        
        logger.info(f"Using Qdrant collection: {collection_name}")
        
        # Get company enumerations for better filtering
        # Note: Despite the type hint being List[str], the vectorstore code expects a dict
        company_enumerations = {}
        if company_name:
            try:
                import boto3
                s3 = boto3.client('s3')
                key = company_name.lower() + '_enumerations.json'
                logger.info(f"Reading company enumerations from S3: {key}")
                response = s3.get_object(Bucket='ansora-company-enumerations', Key=key)
                company_enumerations = json.loads(response['Body'].read().decode('utf-8'))
                logger.info(f"✓ Loaded company enumerations: {list(company_enumerations.keys())}")
            except Exception as e:
                logger.warning(f"Could not load company enumerations: {e}")
                company_enumerations = {
                    "domain": [company_name] if company_name else [],
                    "operational_surface": [],
                    "execution_surface": [],
                    "failure_type": []
                }

        # Search Qdrant for each query
        all_retrieved_docs = []
        
        for i, query in enumerate(search_queries[:10]):  # Limit to first 10 queries
            logger.info(f"Query {i+1}/{min(len(search_queries), 10)}: {query[:100]}...")
            try:
                # For battle cards, use direct search with minimal filtering for better recall
                # The strict company_enumerations filters are too restrictive for competitive intel
                results = vector_store.search_reddit_posts_minimal_filter(
                    query=query,
                    k=10,  # Get top 10 results per query
                    collection_name=collection_name,
                    doc_type='reddit_post'
                )
                all_retrieved_docs.extend(results)
                logger.info(f"  Retrieved {len(results)} documents (scores: {[d.metadata.get('score', 0) for d in results[:3]]})")
            except AttributeError:
                # Fallback to regular search if minimal_filter method doesn't exist
                logger.info(f"  Using standard search (no minimal_filter method)")
                results = vector_store.search_reddit_posts(
                    query=query,
                    k=10,
                    company_enumerations=company_enumerations,
                    collection_name=collection_name,
                    company_name=company_name
                )
                all_retrieved_docs.extend(results)
                logger.info(f"  Retrieved {len(results)} documents")
            except Exception as e:
                logger.warning(f"  Error searching Qdrant: {e}")
        
        logger.info(f"✓ Retrieved total of {len(all_retrieved_docs)} documents from Qdrant")
        
        # Step 2.3: Deduplicate documents by title before reranking
        logger.info("Step 2.3: Deduplicating documents by title...")
        seen_titles = {}
        deduplicated_docs = []
        
        for doc in all_retrieved_docs:
            # Get title from metadata
            metadata = doc.metadata if hasattr(doc, 'metadata') else {}
            title = metadata.get('title', '')
            
            # If no title, use content hash as fallback
            if not title:
                content = doc.page_content if hasattr(doc, 'page_content') else ''
                title = f"_content_hash_{hash(content)}"
            
            # Keep document with highest score if duplicate title found
            if title not in seen_titles:
                seen_titles[title] = doc
                deduplicated_docs.append(doc)
            else:
                # Compare scores and keep the one with higher score
                existing_score = seen_titles[title].metadata.get('score', 0) if hasattr(seen_titles[title], 'metadata') else 0
                current_score = metadata.get('score', 0)
                
                if current_score > existing_score:
                    # Replace with higher-scored document
                    deduplicated_docs.remove(seen_titles[title])
                    seen_titles[title] = doc
                    deduplicated_docs.append(doc)
        
        logger.info(f"✓ Deduplicated: {len(all_retrieved_docs)} → {len(deduplicated_docs)} documents ({len(all_retrieved_docs) - len(deduplicated_docs)} duplicates removed)")
        all_retrieved_docs = deduplicated_docs
        
        # Step 2.4: Clean documents to reduce token usage before reranking
        logger.info("Step 2.4: Cleaning documents for reranking...")
        from rag.pipeline import clean_documents_for_reranking, rerank_and_filter_battle_cards
        
        # Clean to only relevant fields before reranking
        cleaned_docs = clean_documents_for_reranking(all_retrieved_docs)
        
        # Step 2.5: Rerank and filter cleaned documents using battle cards template
        logger.info("Step 2.5: Reranking and filtering battle cards documents...")
        
        # Get company domain and competitors from company_details
        company_domain = company_details.company_context.company_domain if company_details else None
        known_competitors = company_details.company_context.known_competitors if company_details else None
        
        # Use battle-cards-specific reranking function with cleaned docs
        filtered_docs, rerank_prompt, rerank_result = await rerank_and_filter_battle_cards(
            retrieved_docs=cleaned_docs,
            company_name=company_name,
            company_domain=company_domain,
            known_competitors=known_competitors,
            target_competitor=competitor,  # The competitor selected from dropdown
            icp=request.icp  # Target audience from dropdown
        )
        
        logger.info(f"✓ After reranking: {len(filtered_docs)}/{len(cleaned_docs)} documents retained")
        
        # Step 3: Organize filtered results as JSON (already cleaned)
        logger.info("Step 3: Organizing filtered results as JSON...")
        buyer_language_insights = filtered_docs  # Already in the correct format
        
        buyer_language_json = json.dumps(buyer_language_insights, indent=2)
        logger.info(f"✓ Organized {len(buyer_language_insights)} filtered insights as JSON (using standard fields)")
        
        # Step 4: Format the battle card using asset_template_battle-cards with buyer_language_insights
        logger.info("Step 4: Formatting battle card with buyer language insights...")
        
        # Get the battle cards asset template
        battle_card_template_data = get_latest_prompt_template('asset_template_battle-cards')
        
        if not battle_card_template_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="asset_template_battle-cards not found in DynamoDB"
            )
        
        battle_card_template = battle_card_template_data['template_body']
        
        # Format the battle card using the template with buyer_language_insights
        battle_card_prompt = battle_card_template.format(
            competitor=competitor,
            company_name=company_name or '',
            target_audience=request.icp or '',
            icp=request.icp or '',
            buyer_language_insights=buyer_language_json,
            user_provided_text=request.marketing_text or '',
            company_domain=company_context.get('company_domain', ''),
            self_described_positioning=company_context.get('self_described_positioning', '')
        )
        
        # Run LLM to format the battle card
        logger.info("Running final model with buyer language insights...")
        format_messages = [HumanMessage(content=battle_card_prompt)]
        format_response = await llm.ainvoke(format_messages)
        refined_text = format_response.content
        final_prompt = battle_card_prompt
        
        logger.info(f"✓ Battle card formatted: {len(refined_text)} chars")
        
        # Prepare sources from retrieved documents (convert to SourceItem objects)
        from models import SourceItem
        sources = []
        for i, doc in enumerate(all_retrieved_docs[:20], 1):  # Limit to top 20 for sources
            try:
                # Extract metadata properly
                metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                
                # Get filename/title from metadata
                title = metadata.get('title', f'Reddit Post {i}')
                
                # Get URL from metadata (same as standard pipeline)
                doc_url = metadata.get('url', '')
                
                # Get citation (text excerpt, not URL)
                citation = metadata.get('citation', '')
                
                # Get score from metadata
                score = metadata.get('score', 0.0)
                doc_type = metadata.get('doc_type', 'reddit_post')
                source = metadata.get('source', 'reddit')
                
                # Extract fields in the same format as standard pipeline
                # Ensure these fields are always lists/arrays, not strings
                key_issues = metadata.get('key_issues', [])
                if not isinstance(key_issues, list):
                    key_issues = [key_issues] if key_issues and str(key_issues).strip() else []
                pain_phrases = metadata.get('pain_phrases', [])
                if not isinstance(pain_phrases, list):
                    pain_phrases = [pain_phrases] if pain_phrases and str(pain_phrases).strip() else []
                emotional_triggers = metadata.get('emotional_triggers', [])
                if not isinstance(emotional_triggers, list):
                    emotional_triggers = [emotional_triggers] if emotional_triggers and str(emotional_triggers).strip() else []
                buyer_language = metadata.get('buyer_language', [])
                if not isinstance(buyer_language, list):
                    buyer_language = [buyer_language] if buyer_language and str(buyer_language).strip() else []
                implicit_risks = metadata.get('implicit_risks', [])
                if not isinstance(implicit_risks, list):
                    implicit_risks = [implicit_risks] if implicit_risks and str(implicit_risks).strip() else []
                
                # Create comprehensive context excerpt from RAG metadata (same as standard pipeline)
                context_parts = []
                if key_issues and (isinstance(key_issues, list) and key_issues or str(key_issues).strip()):
                    context_parts.append(f"Key Issues: {', '.join(key_issues) if isinstance(key_issues, list) else str(key_issues)}")
                if pain_phrases and (isinstance(pain_phrases, list) and pain_phrases or str(pain_phrases).strip()):
                    context_parts.append(f"Pain Phrases: {', '.join(pain_phrases) if isinstance(pain_phrases, list) else str(pain_phrases)}")
                if emotional_triggers and (isinstance(emotional_triggers, list) and emotional_triggers or str(emotional_triggers).strip()):
                    context_parts.append(f"Emotional Triggers: {', '.join(emotional_triggers) if isinstance(emotional_triggers, list) else str(emotional_triggers)}")
                if buyer_language and (isinstance(buyer_language, list) and buyer_language or str(buyer_language).strip()):
                    context_parts.append(f"Buyer Language: {', '.join(buyer_language) if isinstance(buyer_language, list) else str(buyer_language)}")
                if implicit_risks and (isinstance(implicit_risks, list) and implicit_risks or str(implicit_risks).strip()):
                    context_parts.append(f"Implicit Risks: {', '.join(implicit_risks) if isinstance(implicit_risks, list) else str(implicit_risks)}")
                
                context_excerpt = " | ".join(context_parts) if context_parts else (citation[:500] if citation else "No context available")
                
                # Prepare source item with base fields (same format as standard pipeline)
                source_data = {
                    'filename': title,
                    'title': title,
                    'snippet': context_excerpt,  # Use context_excerpt like standard pipeline
                    'text': context_excerpt,  # Set text field to context_excerpt so frontend can parse it consistently
                    'citation': citation,
                    'score': float(score) if score else 0.0,
                    'source': source,
                    'doc_type': doc_type,
                    'key_issues': key_issues,
                    'pain_phrases': pain_phrases,
                    'emotional_triggers': emotional_triggers,
                    'buyer_language': buyer_language,
                    'implicit_risks': implicit_risks,
                    'channel': metadata.get('channel'),
                    'icp_role_type': metadata.get('icp_role_type')
                }
                
                # Add type-specific URL fields for frontend compatibility (same as standard pipeline)
                if doc_type == "reddit_post":
                    source_data['thread_url'] = doc_url  # Use doc_url directly, same as standard pipeline
                    source_data['subreddit'] = metadata.get('subreddit', '')
                    source_data['thread_author'] = metadata.get('thread_author', '')
                    source_data['selftext'] = metadata.get('selftext', '')
                elif doc_type == "yt_summary":
                    # Use same logic as standard pipeline
                    video_url = metadata.get('video_url') or metadata.get('url') or doc_url or ''
                    source_data['video_url'] = video_url
                    source_data['citation_start_time'] = metadata.get('citation_start_time', 0)
                elif doc_type == "podcast_summary":
                    # Use same logic as standard pipeline
                    episode_url = metadata.get('episode_url', '')
                    source_data['episode_url'] = episode_url
                    source_data['citation_start_time'] = metadata.get('citation_start_time', 0)
                    source_data['mp3_url'] = metadata.get('mp3_url', '')
                
                source = SourceItem(**source_data)
                sources.append(source)
                logger.debug(f"Source {i}: {title[:50]}... (score: {score}, has_text: {bool(context_excerpt)}, has_citation: {bool(citation)})")
            except Exception as e:
                logger.warning(f"Could not create SourceItem {i}: {e}")
        
        logger.info(f"✓ Created {len(sources)} source items from {len(all_retrieved_docs)} documents")
        
        # Log sample of sources for debugging
        if sources:
            logger.info(f"Sample source (first): title='{sources[0].title}', has_text={bool(sources[0].text)}, has_citation={bool(sources[0].citation)}, text_length={len(sources[0].text) if sources[0].text else 0}")
        
        # Format retrieved_docs as list of dictionaries (required by RAGResultResponse model)
        retrieved_docs = []
        for doc in all_retrieved_docs:
            if hasattr(doc, 'page_content'):
                doc_dict = {
                    'content': doc.page_content,
                    'metadata': doc.metadata if hasattr(doc, 'metadata') else {},
                    'source': 'qdrant'
                }
                retrieved_docs.append(doc_dict)
        
        # Generate technical email content for administrators (RAG pipeline details)
        email_content = None
        if is_administrator:
            logger.info("Generating technical email content for administrator...")
            email_content = f"""BATTLE CARDS RAG PIPELINE - TECHNICAL DETAILS

================================================================================
1. RAG GENERATION PROMPT (battle_cards_rag_build_template)
================================================================================

{rag_build_prompt}

================================================================================
2. RAG GENERATION RESULTS (Search Queries Generated)
================================================================================

{rag_build_result}

================================================================================
3. RERANK AND FILTER PROMPT (results_rerank_and_filter_template)
================================================================================

{rerank_prompt if rerank_prompt else 'Reranking not performed or template not available'}

================================================================================
4. RERANK AND FILTER RESULTS
================================================================================

{rerank_result if rerank_result else 'No reranking results available'}

================================================================================
5. RAG RETURNED JSON (Buyer Language Insights - After Filtering)
================================================================================

Retrieved {len(all_retrieved_docs)} documents from Qdrant collection: {collection_name}
(After reranking filter applied)

{buyer_language_json}

================================================================================
6. FINAL PROMPT (asset_template_battle-cards)
================================================================================

{battle_card_prompt}

================================================================================
END OF TECHNICAL DETAILS
================================================================================
"""
            logger.info(f"✓ Technical email content generated: {len(email_content)} chars")
        
        logger.info(f"✓ Battle cards pipeline completed - Output: {len(refined_text)} chars, Sources: {len(sources)}")
        
    except Exception as e:
        logger.error(f"✗ Battle cards pipeline failed: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing battle cards: {str(e)}"
        )
    
    # Generate job ID and save
    job_id = str(uuid.uuid4())
    logger.info(f"Generated job_id: {job_id}")
    
    try:
        job = Job(
            job_id=job_id,
            user_id=current_user.id,
            status="completed",
            refined_text=refined_text,
            sources=[s.model_dump() if hasattr(s, 'model_dump') else s for s in sources],
            retrieved_docs=retrieved_docs,
            final_prompt=final_prompt,
            email_content=email_content if is_administrator else None,
            original_request=request.marketing_text,
            topics=[f"Battle Cards: {competitor}"]
        )
        db.add(job)
        db.commit()
        logger.info("✓ Battle cards job saved to database")
    except Exception as e:
        logger.error(f"✗ Failed to save battle cards job: {str(e)}", exc_info=True)
        raise
    
    logger.info(f"✓ Battle cards request completed successfully - job_id: {job_id}")
    return RAGProcessResponse(job_id=job_id)

