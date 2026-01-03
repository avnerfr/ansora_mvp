from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import uuid
from datetime import datetime
import logging
import os
import tempfile
from pathlib import Path

from db import get_db
from models import (
    User, Job, PromptTemplate,
    RAGProcessRequest, RAGProcessResponse,
    RAGResultResponse, SourceItem, PromptTemplateRequest, PromptTemplateResponse
)
from core.auth import get_current_user, get_cognito_groups_from_token
from rag.pipeline import process_rag, DEFAULT_TEMPLATE
from rag.loader import load_document
from rag.agents import company_analysis_agent, competition_analysis_agent
from rag.s3_utils import get_latest_company_file, save_company_file, get_company_website
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
    logger.info(f"POST /api/v1/rag/process - User: {current_user.email} (ID: {current_user.id})")
    
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
    company_analysis = None
    competition_analysis = None
    
    if company_name:
        # Check S3 for existing company information
        company_file = get_latest_company_file(company_name)
        
        if company_file:
            # Use existing data
            company_analysis = company_file['data'].get('company_analysis')
            competition_analysis = company_file['data'].get('competition_analysis')
            logger.info(f"~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
            logger.info(f"Using cached company information from {company_file['date']}")
            logger.info(f"~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
        else:
            # Generate new company information
            logger.info(f"Generating new company information for {company_name}")
            company_website = get_company_website(company_name)
            logger.info(f"~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
            logger.info(f"company_website: {company_website}")
            logger.info(f"~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
            try:
                company_analysis = company_analysis_agent(company_name, company_website)
                competition_analysis = competition_analysis_agent(company_name, company_website)
                logger.info(f"~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
                logger.info(f"company_analysis: {company_analysis}")
                logger.info(f"~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")            
                logger.info(f"~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
                logger.info(f"competition_analysis: {competition_analysis}")
                logger.info(f"~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")                
                # Save to S3
                save_company_file(company_name, company_analysis, competition_analysis)
                logger.info(f"Saved company information to S3 for {company_name}")
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
        logger.info("Calling RAG pipeline...")
        refined_text, sources, retrieved_docs, final_prompt, email_content = await process_rag(
            user_id=current_user.id,
            backgrounds=request.backgrounds,
            marketing_text=request.marketing_text,
            asset_type=request.asset_type,
            icp=request.icp,
            template=template,
            company_name=company_name,
            company_analysis=company_analysis,
            competition_analysis=competition_analysis,
            is_administrator=is_administrator,
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

