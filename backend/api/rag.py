from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid
from datetime import datetime
import logging

from db import get_db
from models import (
    User, Job, PromptTemplate,
    RAGProcessRequest, RAGProcessResponse,
    RAGResultResponse, SourceItem, PromptTemplateRequest, PromptTemplateResponse
)
from core.auth import get_current_user
from rag.pipeline import process_rag, DEFAULT_TEMPLATE

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


@router.post("/process", response_model=RAGProcessResponse)
async def process_marketing_material(
    request: RAGProcessRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
    
    if not request.marketing_text or not request.marketing_text.strip():
        logger.warning("Validation error: Empty marketing text")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Marketing text cannot be empty"
        )
    
    logger.info(f"Request validated - Backgrounds: {request.backgrounds}, Text length: {len(request.marketing_text)}")
    
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
        refined_text, sources = await process_rag(
            user_id=current_user.id,
            backgrounds=request.backgrounds,
            marketing_text=request.marketing_text,
            template=template
        )
        logger.info(f"✓ RAG pipeline completed - Output: {len(refined_text)} chars, Sources: {len(sources)}")
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
    db: Session = Depends(get_db)
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
    for s in job.sources:
        if isinstance(s, dict):
            sources.append(SourceItem(**s))
        else:
            sources.append(s)
    
    return RAGResultResponse(
        job_id=job.job_id,
        refined_text=job.refined_text,
        sources=sources,
        original_request=job.original_request,
        topics=job.topics
    )

