"""
S3 utility functions for storing and retrieving company information.
"""
import boto3
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from botocore.exceptions import ClientError
import os

logger = logging.getLogger(__name__)

# S3 bucket name
S3_BUCKET = "ansora-company-information"


@dataclass
class CompanyContext:
    """Company context extracted from company_analysis"""
    company_name: str
    company_domain: str
    self_described_positioning: str
    product_surface_names: List[str]
    typical_use_cases: List[str]
    known_competitors: List[str]
    target_audience: List[str]
    operational_pains: List[str]
    usage_rules: List[str]


@dataclass
class CompanyDetails:
    """Complete company details from S3"""
    company_name: str
    date: str
    company_context: CompanyContext
    
    @classmethod
    def from_s3_data(cls, s3_data: Dict[str, Any]) -> Optional['CompanyDetails']:
        """
        Parse S3 company file data into CompanyDetails object.
        
        Args:
            s3_data: Raw data from S3 file containing company_name, date, and company_analysis
            
        Returns:
            CompanyDetails object or None if parsing fails
        """
        try:
            company_name = s3_data.get('company_name', '')
            date = s3_data.get('date', '')
            company_analysis_str = s3_data.get('company_analysis', '')
            
            # Parse the nested JSON string in company_analysis
            if isinstance(company_analysis_str, str):
                company_analysis = json.loads(company_analysis_str)
            else:
                company_analysis = company_analysis_str
            
            # Extract company_context
            context_data = company_analysis.get('company_context', {})
            usage_rules = company_analysis.get('usage_rules', [])
            
            company_context = CompanyContext(
                company_name=context_data.get('company_name', company_name),
                company_domain=context_data.get('company_domain', ''),
                self_described_positioning=context_data.get('self_described_positioning', ''),
                product_surface_names=context_data.get('product_surface_names', []),
                typical_use_cases=context_data.get('typical_use_cases', []),
                known_competitors=context_data.get('known_competitors', []),
                target_audience=context_data.get('target_audience', []),
                operational_pains=context_data.get('operational_pains', []),
                usage_rules=usage_rules
            )
            
            return cls(
                company_name=company_name,
                date=date,
                company_context=company_context
            )
            
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"Error parsing company data: {e}", exc_info=True)
            return None


# Initialize S3 client
def get_s3_client():
    """Get S3 client. Uses AWS credentials from environment or IAM role."""
    return boto3.client('s3', region_name=os.getenv('AWS_REGION', 'us-east-1'))


def normalize_company_name(company_name: str) -> str:
    """
    Normalize company name for file naming.
    Replaces spaces with underscores and converts to lowercase.
    
    Args:
        company_name: Company name (e.g., "CyberArk" or "AlgoSec")
        
    Returns:
        Normalized name (e.g., "cyberark" or "algosec")
    """
    return company_name.lower().replace(' ', '_')


def format_filename(company_name: str, date: datetime) -> str:
    """
    Format filename for company information JSON file.
    Format: company_name-dd-mm-yyyy.json
    
    Args:
        company_name: Normalized company name
        date: Date to use in filename
        
    Returns:
        Formatted filename
    """
    date_str = date.strftime("%d-%m-%Y")
    return f"{company_name}-{date_str}.json"


def get_latest_company_file(company_name: str) -> Optional[CompanyDetails]:
    """
    Get the latest company information from S3 as a CompanyDetails object.
    
    Args:
        company_name: Company name
        
    Returns:
        CompanyDetails object, or None if not found
    """
    try:
        s3_client = get_s3_client()
        normalized_name = normalize_company_name(company_name)
        # List all files for this company
        prefix = f"{normalized_name}-"
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            logger.info(f"No files found for company: {company_name}")
            return None
        
        # Find the latest file by date in filename
        latest_file = None
        latest_date = None
        
        for obj in response['Contents']:
            file_key = obj['Key']
            # Extract date from filename (format: company_name-dd-mm-yyyy.json)
            try:
                # Remove prefix and .json extension
                date_part = file_key.replace(prefix, '').replace('.json', '')
                file_date = datetime.strptime(date_part, "%d-%m-%Y")
                
                if latest_date is None or file_date > latest_date:
                    latest_date = file_date
                    latest_file = file_key
            except ValueError:
                logger.warning(f"Could not parse date from filename: {file_key}")
                continue
        
        if latest_file is None:
            return None
        
        # Check if file is within last 6 months
        six_months_ago = datetime.now() - timedelta(days=180)
        if latest_date < six_months_ago:
            logger.info(f"Latest file for {company_name} is older than 6 months: {latest_date}")
            return None
        
        # Read the file
        obj_response = s3_client.get_object(Bucket=S3_BUCKET, Key=latest_file)
        file_content = obj_response['Body'].read().decode('utf-8')
        data = json.loads(file_content)
        
        # Parse into CompanyDetails object
        company_details = CompanyDetails.from_s3_data(data)
        
        if company_details:
            logger.info(f"✓ Loaded company details for {company_name}: "
                       f"{len(company_details.company_context.target_audience)} target audiences, "
                       f"{len(company_details.company_context.operational_pains)} operational pains")
        else:
            logger.warning(f"Failed to parse company details for {company_name}")
        
        return company_details
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchBucket':
            logger.warning(f"S3 bucket {S3_BUCKET} does not exist")
        else:
            logger.error(f"Error accessing S3: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting company file: {e}", exc_info=True)
        return None


def save_company_file(company_name: str, company_analysis: str) -> str:
    """
    Save company information to S3.
    
    Args:
        company_name: Company name
        company_analysis: Company analysis JSON string from company_analysis_agent
        
    Returns:
        S3 file key of saved file
    """
    try:
        s3_client = get_s3_client()
        normalized_name = normalize_company_name(company_name)
        today = datetime.now()
        file_key = format_filename(normalized_name, today)
        
        # Prepare data to save
        data = {
            'company_name': company_name,
            'date': today.isoformat(),
            'company_analysis': company_analysis
        }
        
        # Upload to S3
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=file_key,
            Body=json.dumps(data, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"Saved company information to S3: {file_key}")
        return file_key
        
    except Exception as e:
        logger.error(f"Error saving company file to S3: {e}")
        raise


def get_company_website(company_name: str) -> str:
    """
    Get company website URL based on company name.
    For now, uses a simple mapping. Can be extended to use a database or API.
    
    Args:
        company_name: Company name
        
    Returns:
        Website URL
    """
    # Simple mapping for known companies
    company_websites = {
        'Algosec': 'https://algosec.com',
        'CyberArk': 'https://cyberark.com',
        'JFrog': 'https://jfrog.com',
        'Cloudinary': 'https://cloudinary.com',
        'Incredibuild': 'https://incredibuild.com',
    }
    
    # Try exact match first
    if company_name in company_websites:
        return company_websites[company_name]
    
    # Try case-insensitive match
    for name, url in company_websites.items():
        if name.lower() == company_name.lower():
            return url
    
    # Default: construct from company name
    normalized = company_name.lower().replace(' ', '')
    return f"https://{normalized}.com"
