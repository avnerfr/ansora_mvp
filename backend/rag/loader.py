from langchain_community.document_loaders import PyPDFLoader, UnstructuredPowerPointLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List
from langchain_core.documents import Document
import os
from PIL import Image
import pytesseract


def load_document(file_path: str, file_type: str) -> List[Document]:
    """Load a document and return LangChain Document objects."""
    documents = []
    
    try:
        if file_type in ["application/pdf", "pdf"]:
            loader = PyPDFLoader(file_path)
            documents = loader.load()
        elif file_type in [
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "pptx",
            "ppt"
        ]:
            loader = UnstructuredPowerPointLoader(file_path)
            documents = loader.load()
        elif file_type in ["image/png", "image/jpeg", "image/jpg", "image/gif"]:
            # Basic OCR for images (placeholder)
            # In production, you might want to use more advanced OCR
            try:
                image = Image.open(file_path)
                text = pytesseract.image_to_string(image)
                documents = [Document(page_content=text, metadata={"source": file_path})]
            except Exception as e:
                # Fallback: create a document with a note
                documents = [Document(
                    page_content=f"Image file: {os.path.basename(file_path)}. OCR extraction not available.",
                    metadata={"source": file_path}
                )]
        else:
            # For other file types, create a placeholder document
            documents = [Document(
                page_content=f"File content not extracted: {os.path.basename(file_path)}",
                metadata={"source": file_path}
            )]
    except Exception as e:
        # Return a document with error info
        documents = [Document(
            page_content=f"Error loading document: {str(e)}",
            metadata={"source": file_path, "error": True}
        )]
    
    return documents


def chunk_documents(documents: List[Document], chunk_size: int = 1000, chunk_overlap: int = 200) -> List[Document]:
    """Split documents into chunks."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    chunks = text_splitter.split_documents(documents)
    return chunks

