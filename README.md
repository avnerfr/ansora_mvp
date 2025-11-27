# Marketing MVP

A production-ready web application for refining marketing materials using RAG (Retrieval-Augmented Generation) technology. This app combines Next.js frontend with a FastAPI backend, leveraging LangChain and Qdrant for intelligent document processing and content refinement.

## Architecture

This is a monorepo containing:

- **Frontend** (`/frontend`): Next.js 14 with TypeScript, Tailwind CSS, and React Query
- **Backend** (`/backend`): FastAPI with Python, LangChain, Qdrant, and SQLite

## Features

- 🔐 User authentication (JWT-based)
- 📄 Document upload (PDF, PPT, Images)
- 🎯 Background selection for context
- 🤖 AI-powered marketing material refinement
- 📊 Source tracking and references
- ⚙️ Customizable prompt templates
- 🐳 Docker support for easy deployment

## Prerequisites

- Node.js 18+ and npm/yarn
- Python 3.11+
- Docker and Docker Compose (for backend services)
- OpenAI API key

## Quick Start

### 1. Backend Setup

Navigate to the backend directory:

```bash
cd backend
```

Create a `.env` file:

```bash
cp .env.example .env
```

Edit `.env` and set your configuration:

```env
JWT_SECRET=your-secret-key-change-this-in-production
OPENAI_API_KEY=your-openai-api-key
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=
ALLOWED_ORIGINS=http://localhost:3000
```

### 2. Start Backend Services with Docker

From the project root:

```bash
docker-compose up --build
```

This will start:

- Qdrant vector database (port 6333)
- FastAPI backend (port 8000)

### 3. Frontend Setup

Open a new terminal and navigate to the frontend directory:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Create a `.env.local` file:

```env
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

Start the development server:

```bash
npm run dev
```

The frontend will be available at `http://localhost:3000`.

## Development

### Backend Development (Without Docker)

If you prefer to run the backend locally without Docker:

1. **Install Python dependencies:**

```bash
cd backend
pip install -r requirements.txt
```

2. **Start Qdrant locally:**

```bash
docker run -p 6333:6333 qdrant/qdrant:latest
```

3. **Update `.env`:**

```env
QDRANT_URL=http://localhost:6333
```

4. **Run the backend:**

```bash
cd backend
uvicorn main:app --reload
```

### Frontend Development

The frontend runs with hot reload enabled:

```bash
cd frontend
npm run dev
```

## Deployment

### Frontend Deployment (Vercel)

1. Push your code to a Git repository
2. Import the project in Vercel
3. Set the environment variable:
   - `NEXT_PUBLIC_BACKEND_URL`: Your backend API URL
4. Deploy

### Backend Deployment

The backend can be deployed using Docker:

1. **Build the image:**

```bash
cd backend
docker build -t marketing-mvp-backend .
```

2. **Run with docker-compose (recommended):**

```bash
docker-compose up -d
```

Or deploy to a container service (AWS ECS, Google Cloud Run, Azure Container Instances, etc.) with:

- Environment variables configured
- Qdrant accessible (either as a service or external instance)
- Persistent storage for the database and uploaded files

## Environment Variables

### Frontend (`.env.local`)

- `NEXT_PUBLIC_BACKEND_URL`: Backend API base URL

### Backend (`.env`)

- `JWT_SECRET`: Secret key for JWT token signing
- `OPENAI_API_KEY`: OpenAI API key for LLM
- `QDRANT_URL`: Qdrant service URL
- `QDRANT_API_KEY`: Qdrant API key (optional)
- `ALLOWED_ORIGINS`: Comma-separated list of allowed CORS origins
- `STORAGE_PATH`: Path for storing uploaded files (default: `./storage`)

## API Endpoints

### Authentication

- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - Login user
- `GET /api/v1/auth/me` - Get current user info

### Documents

- `POST /api/v1/documents/upload` - Upload documents
- `GET /api/v1/documents/list` - List user documents

### RAG

- `POST /api/v1/rag/process` - Process marketing material
- `GET /api/v1/rag/results/{job_id}` - Get processing results
- `GET /api/v1/rag/prompt-template` - Get prompt template
- `POST /api/v1/rag/prompt-template` - Save prompt template

## Project Structure

```
mvp_marketing_app/
├── backend/
│   ├── api/              # API routes
│   ├── core/             # Core configuration and auth
│   ├── rag/              # RAG pipeline and vector store
│   ├── models.py         # Database and Pydantic models
│   ├── db.py             # Database setup
│   ├── main.py           # FastAPI app entry point
│   ├── requirements.txt  # Python dependencies
│   └── Dockerfile        # Backend Docker image
├── frontend/
│   ├── app/              # Next.js App Router pages
│   ├── components/       # React components
│   ├── lib/              # Utilities and API client
│   └── package.json      # Node dependencies
├── docker-compose.yml    # Docker services configuration
└── README.md            # This file
```

## Usage

1. **Register/Login**: Create an account or sign in
2. **Select Backgrounds**: Choose relevant backgrounds (e.g., cybersecurity, marketing)
3. **Upload Documents**: Upload PDFs, PowerPoint files, or images
4. **Provide Marketing Material**: Paste or type your current marketing content
5. **Customize Template** (Optional): Edit the prompt template
6. **Process**: Click "Process" to refine your material
7. **View Results**: Results open in a new tab with refined content and source references

## Troubleshooting

### Backend won't start

- Check that Qdrant is running and accessible
- Verify all environment variables are set
- Check Docker logs: `docker-compose logs backend`

### Frontend can't connect to backend

- Verify `NEXT_PUBLIC_BACKEND_URL` is set correctly
- Check CORS settings in backend `.env`
- Ensure backend is running on the correct port

### Document upload fails

- Check file size limits (backend has no explicit limit, but consider adding one)
- Verify file types are supported
- Check storage directory permissions

### RAG processing errors

- Verify OpenAI API key is valid
- Check that documents were successfully uploaded and indexed
- Review backend logs for detailed error messages

## License

This project is provided as-is for development and learning purposes.

## Contributing

This is a template/production-ready starter project. Feel free to extend and customize it for your needs.
