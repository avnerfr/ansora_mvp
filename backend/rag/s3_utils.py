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
from core.auth import get_cognito_groups_from_token
from rag.agents import company_analysis_agent

logger = logging.getLogger(__name__)

# S3 bucket name
S3_BUCKET = "ansora-company-information"
ENUMERATIONS_BUCKET = "ansora-company-enumerations"


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


class S3CompanyDataManager:
    """
    Manages company data loading and caching from S3.
    Loads company information once and caches it for subsequent requests.
    """
    
    def __init__(self):
        """Initialize the company data manager with empty cache."""
        self._company_cache: Dict[str, CompanyDetails] = {}
        self._enumerations_cache: Dict[str, List[str]] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._cache_ttl_hours = 24  # Cache TTL in hours (24 hours default)
        self._s3_client = None
    
    def _get_s3_client(self):
        """Get or create S3 client. Uses AWS credentials from environment or IAM role."""
        if self._s3_client is None:
            self._s3_client = boto3.client('s3', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        return self._s3_client
    
    def _normalize_company_name(self, company_name: str) -> str:
        """
        Normalize company name for file naming.
        Replaces spaces with underscores and converts to lowercase.
        
        Args:
            company_name: Company name (e.g., "CyberArk" or "AlgoSec")
            
        Returns:
            Normalized name (e.g., "cyberark" or "algosec")
        """
        return company_name.lower().replace(' ', '_')
    
    def _format_filename(self, company_name: str, date: datetime) -> str:
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
    
    def _is_cache_valid(self, company_name: str) -> bool:
        """
        Check if cached data for a company is still valid.
        
        Args:
            company_name: Company name
            
        Returns:
            True if cache is valid, False otherwise
        """
        if company_name not in self._cache_timestamps:
            return False
        
        cache_time = self._cache_timestamps[company_name]
        cache_age = datetime.now() - cache_time
        return cache_age < timedelta(hours=self._cache_ttl_hours)
    
    def _load_company_file_from_s3(self, company_name: str) -> Optional[CompanyDetails]:
        """
        Load company information from S3 (bypasses cache).
        
        Args:
            company_name: Company name
            
        Returns:
            CompanyDetails object, or None if not found
        """
        try:
            s3_client = self._get_s3_client()
            normalized_name = self._normalize_company_name(company_name)
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
    
    def load_company_data(self, company_name: str, force_reload: bool = False) -> Optional[CompanyDetails]:
        """
        Load company data from S3 with caching.
        If data is already cached and valid, returns cached data.
        Otherwise, loads from S3 and caches it.
        
        Args:
            company_name: Company name
            force_reload: If True, bypass cache and reload from S3
            
        Returns:
            CompanyDetails object, or None if not found
        """
        if not company_name:
            return None
        
        # Check cache first (unless force_reload is True)
        if not force_reload and company_name in self._company_cache and self._is_cache_valid(company_name):
            logger.info(f"Using cached company data for {company_name}")
            return self._company_cache[company_name]
        
        # Load from S3
        logger.info(f"Loading company data from S3 for {company_name}")
        company_details = self._load_company_file_from_s3(company_name)
        
        # Cache the result (even if None, to avoid repeated S3 calls)
        if company_details:
            self._company_cache[company_name] = company_details
            self._cache_timestamps[company_name] = datetime.now()
            logger.info(f"Cached company data for {company_name}")
        else:
            # Cache None with a shorter TTL to allow retry
            self._cache_timestamps[company_name] = datetime.now() - timedelta(hours=self._cache_ttl_hours - 1)
        
        return company_details
    
    def get_company_data(self, company_name: str) -> Optional[CompanyDetails]:
        """
        Get company data from cache or load from S3 if not cached.
        This is a convenience method that calls load_company_data.
        
        Args:
            company_name: Company name
            
        Returns:
            CompanyDetails object, or None if not found
        """
        return self.load_company_data(company_name)
    
    def get_company_context(self, company_name: str) -> Optional[Dict[str, Any]]:
        """
        Get company context information.
        
        Args:
            company_name: Company name
            
        Returns:
            Dict with 'company_information' key containing CompanyContext, or None if not found
        """
        company_details = self.get_company_data(company_name)
        if not company_details:
            return None
        
        return {
            'company_information': company_details.company_context
        }
    
    def _load_company_enumerations_from_s3(self, company_name: str) -> List[str]:
        """
        Load company enumerations from S3 (bypasses cache).
        
        Args:
            company_name: Company name
            
        Returns:
            List of enumerations, or empty list if not found
        """
        try:
            s3_client = self._get_s3_client()
            key = company_name.lower() + '_enumerations.json'
            logger.info(f"Reading company enumerations from S3: {key}")
            response = s3_client.get_object(Bucket=ENUMERATIONS_BUCKET, Key=key)
            return json.loads(response['Body'].read().decode('utf-8'))
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.info(f"No enumerations file found for {company_name}")
            else:
                logger.error(f"Error accessing enumerations from S3: {e}")
            return []
        except Exception as e:
            logger.error(f"Error loading company enumerations: {e}", exc_info=True)
            return []
    
    def load_company_enumerations(self, company_name: str, force_reload: bool = False) -> List[str]:
        """
        Load company enumerations from S3 with caching.
        
        Args:
            company_name: Company name
            force_reload: If True, bypass cache and reload from S3
            
        Returns:
            List of enumerations
        """
        if not company_name:
            return []
        
        # Check cache first (unless force_reload is True)
        if not force_reload and company_name in self._enumerations_cache and self._is_cache_valid(company_name):
            logger.info(f"Using cached enumerations for {company_name}")
            return self._enumerations_cache[company_name]
        
        # Load from S3
        logger.info(f"Loading company enumerations from S3 for {company_name}")
        enumerations = self._load_company_enumerations_from_s3(company_name)
        
        # Cache the result
        self._enumerations_cache[company_name] = enumerations
        self._cache_timestamps[company_name] = datetime.now()
        logger.info(f"Cached {len(enumerations)} enumerations for {company_name}")
        
        return enumerations
    
    def get_company_enumerations(self, company_name: str) -> List[str]:
        """
        Get company enumerations from cache or load from S3 if not cached.
        
        Args:
            company_name: Company name
            
        Returns:
            List of enumerations
        """
        return self.load_company_enumerations(company_name)
    
    def clear_cache(self, company_name: Optional[str] = None):
        """
        Clear cache for a specific company or all companies.
        
        Args:
            company_name: If provided, clear cache for this company only.
                         If None, clear all caches.
        """
        if company_name:
            self._company_cache.pop(company_name, None)
            self._enumerations_cache.pop(company_name, None)
            self._cache_timestamps.pop(company_name, None)
            logger.info(f"Cleared cache for {company_name}")
        else:
            self._company_cache.clear()
            self._enumerations_cache.clear()
            self._cache_timestamps.clear()
            logger.info("Cleared all company data caches")
    
    def save_company_file(self, company_name: str, company_analysis: str) -> str:
        """
        Save company information to S3 and update cache.
        
        Args:
            company_name: Company name
            company_analysis: Company analysis JSON string from company_analysis_agent
            
        Returns:
            S3 file key of saved file
        """
        try:
            s3_client = self._get_s3_client()
            normalized_name = self._normalize_company_name(company_name)
            today = datetime.now()
            file_key = self._format_filename(normalized_name, today)
            
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
            
            # Reload and cache the newly saved file
            company_details = self._load_company_file_from_s3(company_name)
            if company_details:
                self._company_cache[company_name] = company_details
                self._cache_timestamps[company_name] = datetime.now()
                logger.info(f"Updated cache with newly saved company data for {company_name}")
            
            return file_key
            
        except Exception as e:
            logger.error(f"Error saving company file to S3: {e}")
            raise


# Global instance for backward compatibility
_company_data_manager = S3CompanyDataManager()


# Backward compatibility functions
def get_s3_client():
    """Get S3 client. Uses AWS credentials from environment or IAM role."""
    return _company_data_manager._get_s3_client()


def normalize_company_name(company_name: str) -> str:
    """Normalize company name for file naming."""
    return _company_data_manager._normalize_company_name(company_name)


def format_filename(company_name: str, date: datetime) -> str:
    """Format filename for company information JSON file."""
    return _company_data_manager._format_filename(company_name, date)


def get_latest_company_file(company_name: str) -> Optional[CompanyDetails]:
    """
    Get the latest company information from S3 as a CompanyDetails object.
    Uses cached data if available.
    
    Args:
        company_name: Company name
        
    Returns:
        CompanyDetails object, or None if not found
    """
    return _company_data_manager.get_company_data(company_name)


def save_company_file(company_name: str, company_analysis: str) -> str:
    """
    Save company information to S3.
    
    Args:
        company_name: Company name
        company_analysis: Company analysis JSON string from company_analysis_agent
        
    Returns:
        S3 file key of saved file
    """
    return _company_data_manager.save_company_file(company_name, company_analysis)


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


def get_company_enumerations(company_name: str) -> List[str]:
    """
    Get company enumerations from S3 bucket.
    Uses cached data if available.
    
    Args:
        company_name: Company name
        
    Returns:
        List of enumerations
    """
    return _company_data_manager.get_company_enumerations(company_name)


def get_company_data_from_credentials(token, company: str) -> Optional[CompanyDetails]:
    """
    Get company data from credentials.
    
    Args:
        token: JWT token
        company: Company name from request (for administrators) or None
        
    Returns:
        CompanyDetails object, or None if not found
    """
    groups = get_cognito_groups_from_token(token)
    is_administrator = 'Administrators' in groups
    logger.info(f"User is administrator: {is_administrator}")

    logger.info(f"$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")    
    # Determine company name
    company_name = None
    if is_administrator:
        # For administrators, company MUST come from the request (dialog), not from Cognito
        if company:
            company_name = company
            logger.info(f"Administrator: Using company from request (dialog): {company_name}")
        else:
            # This should not happen if validation is correct, but log warning
            logger.warning("Administrator user but no company provided in request")
    else:
        # For non-admin users, get company from Cognito groups
        if company:
            # Non-admin user provided company in request (shouldn't normally happen, but allow it)
            company_name = company
            logger.info(f"Non-admin user: Using company from request: {company_name}")
        else:
            # Get company from Cognito groups (non-admin users)
            # Filter out Administrators group
            company_groups = [g for g in groups if g != 'Administrators']
            if company_groups:
                company_name = company_groups[0]  # Use first non-admin group
                logger.info(f"Non-admin user: Using company from Cognito groups: {company_name}")
            else:
                logger.warning("No company found in Cognito groups and no company in request")
    logger.info(f"$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
    
    # Get or generate company information
    company_details = None
    company_analysis = None
     
    if company_name:
        # Check cache/S3 for existing company information (returns CompanyDetails object)
        company_details = _company_data_manager.get_company_data(company_name)
        
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
           
                # Save to S3 (this will also update the cache)
                _company_data_manager.save_company_file(company_name, company_analysis)
                logger.info(f"Saved company information to S3 for {company_name}")
                
                # Get the newly saved file (from cache now)
                company_details = _company_data_manager.get_company_data(company_name)
            except Exception as e:
                logger.error(f"Error generating company information: {e}")
                # Continue without company information rather than failing
 
    return company_details


# Export the manager instance for direct access if needed
def get_company_data_manager() -> S3CompanyDataManager:
    """
    Get the global company data manager instance.
    
    Returns:
        S3CompanyDataManager instance
    """
    return _company_data_manager
