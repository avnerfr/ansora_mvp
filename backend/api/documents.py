from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import os
import shutil
import uuid
from datetime import datetime

from db import get_db
from models import User, Document, DocumentUploadResponse, DocumentListResponse
from core.auth import get_current_user
from core.config import settings
from rag.loader import load_document, chunk_documents
from rag.vectorstore import vector_store

router = APIRouter()


def get_file_type(filename: str) -> str:
    """Get MIME type from filename extension."""
    ext = filename.lower().split('.')[-1]
    type_map = {
        'pdf': 'application/pdf',
        'ppt': 'application/vnd.ms-powerpoint',
        'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'gif': 'image/gif',
    }
    return type_map.get(ext, 'application/octet-stream')


@router.post("/upload", response_model=List[DocumentUploadResponse])
async def upload_documents(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload and process documents."""
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided"
        )
    
    results = []
    
    # Create user storage directory
    user_storage_dir = os.path.join(settings.STORAGE_PATH, str(current_user.id))
    os.makedirs(user_storage_dir, exist_ok=True)
    
    for file in files:
        try:
            # Get file info
            file_type = get_file_type(file.filename)
            file_size = 0
            
            # Save file
            file_id = str(uuid.uuid4())
            file_extension = file.filename.split('.')[-1] if '.' in file.filename else ''
            saved_filename = f"{file_id}.{file_extension}" if file_extension else file_id
            file_path = os.path.join(user_storage_dir, saved_filename)
            
            with open(file_path, "wb") as buffer:
                content = await file.read()
                file_size = len(content)
                buffer.write(content)
            
            # Create database record
            db_document = Document(
                user_id=current_user.id,
                filename=file.filename,
                file_type=file_type,
                file_path=file_path,
                file_size=file_size
            )
            db.add(db_document)
            db.commit()
            db.refresh(db_document)
            
            # Load and process document
            try:
                documents = load_document(file_path, file_type)
                chunks = chunk_documents(documents)
                
                # Add to vector store
                vector_store.add_documents(
                    user_id=current_user.id,
                    documents=chunks,
                    file_id=db_document.id,
                    filename=file.filename,
                    file_type=file_type
                )
            except Exception as e:
                print(f"Error processing document {file.filename}: {e}")
                # Continue even if vectorization fails
            
            results.append(DocumentUploadResponse(
                document_id=db_document.id,
                filename=file.filename,
                file_type=file_type,
                status="success"
            ))
            
        except Exception as e:
            print(f"Error uploading file {file.filename}: {e}")
            results.append(DocumentUploadResponse(
                document_id=0,
                filename=file.filename,
                file_type=get_file_type(file.filename),
                status=f"error: {str(e)}"
            ))
    
    return results


@router.get("/list", response_model=List[DocumentListResponse])
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all documents for the current user."""
    documents = db.query(Document).filter(Document.user_id == current_user.id).all()
    return [DocumentListResponse(
        id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        created_at=doc.created_at
    ) for doc in documents]

