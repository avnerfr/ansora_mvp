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
from rag.pipeline import process_rag, DEFAULT_TEMPLATE
from rag.loader import load_document
from rag.agents import company_analysis_agent, competition_analysis_agent
from rag.s3_utils import get_latest_company_file, save_company_file, get_company_website
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
    company_analysis = None
    competition_analysis = None
    
    if company_name:
        # Check S3 for existing company information
        company_file = get_latest_company_file(company_name)
        
        if company_file:
            # Use existing data
            company_analysis = company_file['data'].get('company_analysis')
            competition_analysis = company_file['data'].get('competition_analysis')
        else:
            # Generate new company information
            logger.info(f"Generating new company information for {company_name}")
            company_website = get_company_website(company_name)
            try:
                company_analysis = company_analysis_agent(company_name, company_website)
                competition_analysis = competition_analysis_agent(company_name, company_website)
           
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
            company_analysis=company_analysis,
            competition_analysis=competition_analysis,
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


@router.get("/icps/{company_name}")
async def get_icps_for_company(
    company_name: str,
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get ICPs (Target Audience) for a company based on its domain.
    
    Args:
        company_name: Company name
        
    Returns:
        List of ICPs for the company
    """
    try:
        # Get company information from S3
        company_file = get_latest_company_file(company_name)
        
        if not company_file or 'data' not in company_file:
            logger.warning(f"No company information found for {company_name}, returning default ICPs")
            # Return default ICPs if company info not found
            default_icps = [
                "Network & Security Operations",
                "Application & Service Delivery",
                "CIO",
                "CISO",
                "Risk and Compliance"
            ]
            return {
                "icps": default_icps,
                "target_audience": default_icps  # Also return as target_audience for compatibility
            }
        
        company_data = company_file['data']
        company_analysis = company_data.get('company_analysis', '')
        
        # Extract company_domain from company_analysis JSON
        company_domain = None
        if company_analysis:
            try:
                # Try to extract JSON from company_analysis
                json_match = re.search(r'```json\s*(.*?)\s*```', company_analysis, re.DOTALL)
                if json_match:
                    company_json = json.loads(json_match.group(1).strip())
                    company_domain = company_json.get('company_domain', '')
                else:
                    # Try parsing as direct JSON
                    company_json = json.loads(company_analysis)
                    company_domain = company_json.get('company_domain', '')
            except (json.JSONDecodeError, AttributeError) as e:
                logger.warning(f"Error parsing company_analysis for {company_name}: {e}")
        
        # Map domain to ICPs
        # This is a basic mapping - can be extended or stored in company info
        domain_to_icps = {
            'cybersecurity': [
                "Network & Security Operations",
                "CISO",
                "Security Operations",
                "Risk and Compliance"
            ],
            'software_developement_optimization': [
                "Software Engineer",
                "Engineering Manager",
                "Backend Engineer",
                "Game Developer",
                "Embedded / Firmware Engineer",
                "Build Engineer",
                "CI Engineer",
                "DevOps Engineer",
                "Platform Engineer",
                "QA Automation Engineer",
            ],
            'cloud_computing': [
                "Cloud Operations",
                "DevOps",
                "CIO",
                "Application & Service Delivery"
            ],
            'devops': [
                "DevOps",
                "Application & Service Delivery",
                "CIO",
                "Platform Engineering"
            ],
            'infrastructure': [
                "Network & Security Operations",
                "Infrastructure Operations",
                "CIO",
                "Application & Service Delivery"
            ],
            'compliance': [
                "Risk and Compliance",
                "CISO",
                "CIO",
                "Governance"
            ]
        }
        
        # Default ICPs if domain not found
        default_icps = [
            "Network & Security Operations",
            "Application & Service Delivery",
            "CIO",
            "CISO",
            "Risk and Compliance"
        ]
        
        # Find matching ICPs based on domain
        icps = default_icps
        if company_domain:
            company_domain_lower = company_domain.lower().replace(' ', '_')
            # Check for exact match or partial match
            for domain_key, domain_icps in domain_to_icps.items():
                if domain_key in company_domain_lower or company_domain_lower in domain_key:
                    icps = domain_icps
                    break
        
        logger.info(f"Returning ICPs for {company_name} (domain: {company_domain}): {icps}")
        return {
            "icps": icps,
            "target_audience": icps  # Also return as target_audience for compatibility
        }
        
    except Exception as e:
        logger.error(f"Error getting ICPs for company {company_name}: {e}", exc_info=True)
        # Return default ICPs on error
        default_icps = [
            "Network & Security Operations",
            "Application & Service Delivery",
            "CIO",
            "CISO",
            "Risk and Compliance"
        ]
        return {
            "icps": default_icps,
            "target_audience": default_icps  # Also return as target_audience for compatibility
        }


@router.get("/operational-pains/{company_name}")
async def get_operational_pains_for_company(
    company_name: str,company_file,
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get Operational Pain Points for a company based on its domain.
    
    Args:
        company_name: Company name
        
    Returns:
        List of operational pain points for the company
    """
    try:
        # Get company information from S3
        company_file = get_latest_company_file(company_name)
        
        if not company_file or 'data' not in company_file:
            logger.warning(f"No company information found for {company_name}, returning default pain points")
            # Return default pain points if company info not found
            return {
                "operational_pains": [
                    "Afraid to push a network change without knowing what will break",
                    "Security changes get stuck in CAB because no one can prove safety",
                    "Cannot verify that network policies actually work as intended",
                    "Rules accumulated over time that nobody understands or owns",
                    "Afraid to remove access because the real dependencies are unknown",
                    "Cloud and on-prem environments behave differently under the same policy",
                    "Audits fail because policy intent cannot be proven"
                ]
            }
        
        company_data = company_file['data']
        company_analysis = company_data.get('company_analysis', '')
        
        # Extract company_domain from company_analysis JSON
        company_domain = None
        if company_analysis:
            try:
                # Try to extract JSON from company_analysis
                json_match = re.search(r'```json\s*(.*?)\s*```', company_analysis, re.DOTALL)
                if json_match:
                    company_json = json.loads(json_match.group(1).strip())
                    company_domain = company_json.get('company_domain', '')
                else:
                    # Try parsing as direct JSON
                    company_json = json.loads(company_analysis)
                    company_domain = company_json.get('company_domain', '')
            except (json.JSONDecodeError, AttributeError) as e:
                logger.warning(f"Error parsing company_analysis for {company_name}: {e}")
        
        # Map domain to operational pain points
        domain_to_pains = {
            'cybersecurity': [
                "Afraid to push a network change without knowing what will break",
                "Security changes get stuck in CAB because no one can prove safety",
                "Cannot verify that network policies actually work as intended",
                "Rules accumulated over time that nobody understands or owns",
                "Afraid to remove access because the real dependencies are unknown",
                "Cloud and on-prem environments behave differently under the same policy",
                "Audits fail because policy intent cannot be proven"
            ],
            'network_security': [
                "Afraid to push a network change without knowing what will break",
                "Security changes get stuck in CAB because no one can prove safety",
                "Cannot verify that network policies actually work as intended",
                "Rules accumulated over time that nobody understands or owns",
                "Afraid to remove access because the real dependencies are unknown",
                "Cloud and on-prem environments behave differently under the same policy",
                "Audits fail because policy intent cannot be proven"
            ],
            'software_developement_optimization': [
                "Build times are too slow, blocking developer productivity",
                "Cannot reproduce build failures locally",
                "CI/CD pipelines are flaky and unreliable",
                "Code compilation takes too long, disrupting workflow",
                "Cannot parallelize builds effectively",
                "Build artifacts are inconsistent across environments",
                "Integration tests take too long to run"
            ],
            'cloud_computing': [
                "Cloud costs are unpredictable and hard to control",
                "Cannot track which services are driving costs",
                "Multi-cloud environments behave inconsistently",
                "Cloud resource provisioning is slow and error-prone",
                "Cannot verify cloud security policies work as intended",
                "Cloud and on-prem environments are difficult to manage together",
                "Cloud resource visibility is limited"
            ],
            'devops': [
                "Deployments are slow and risky",
                "Cannot reproduce production issues locally",
                "CI/CD pipelines are unreliable",
                "Infrastructure changes are difficult to track and revert",
                "Configuration drift causes unexpected failures",
                "Cannot scale infrastructure quickly when needed",
                "Monitoring and alerting gaps cause delayed incident response"
            ],
            'infrastructure': [
                "Infrastructure changes are risky and time-consuming",
                "Cannot verify changes won't break production",
                "Configuration drift causes unexpected behavior",
                "Infrastructure visibility is limited",
                "Changes take too long to implement and validate",
                "Cannot track infrastructure dependencies",
                "Infrastructure documentation is outdated or missing"
            ],
            'compliance': [
                "Audits fail because policy intent cannot be proven",
                "Cannot demonstrate compliance with regulatory requirements",
                "Compliance checks are manual and error-prone",
                "Cannot track compliance status across systems",
                "Policy violations are discovered too late",
                "Compliance reporting is time-consuming and inaccurate",
                "Cannot verify that controls are working as intended"
            ]
        }
        
        # Default pain points if domain not found
        default_pains = [
            "Afraid to push a network change without knowing what will break",
            "Security changes get stuck in CAB because no one can prove safety",
            "Cannot verify that network policies actually work as intended",
            "Rules accumulated over time that nobody understands or owns",
            "Afraid to remove access because the real dependencies are unknown",
            "Cloud and on-prem environments behave differently under the same policy",
            "Audits fail because policy intent cannot be proven"
        ]
        
        # Find matching pain points based on domain
        pains = default_pains
        if company_domain:
            company_domain_lower = company_domain.lower().replace(' ', '_')
            # Check for exact match or partial match
            for domain_key, domain_pains in domain_to_pains.items():
                if domain_key in company_domain_lower or company_domain_lower in domain_key:
                    pains = domain_pains
                    break
        
        logger.info(f"Returning operational pain points for {company_name} (domain: {company_domain}): {len(pains)} points")
        return {"operational_pains": pains}
        
    except Exception as e:
        logger.error(f"Error getting operational pain points for company {company_name}: {e}", exc_info=True)
        # Return default pain points on error
        return {
            "operational_pains": [
                "Afraid to push a network change without knowing what will break",
                "Security changes get stuck in CAB because no one can prove safety",
                "Cannot verify that network policies actually work as intended",
                "Rules accumulated over time that nobody understands or owns",
                "Afraid to remove access because the real dependencies are unknown",
                "Cloud and on-prem environments behave differently under the same policy",
                "Audits fail because policy intent cannot be proven"
            ]
        }

