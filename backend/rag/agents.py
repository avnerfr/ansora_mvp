"""
Company analysis agents for extracting company information and competitor analysis.
Based on agents from simple_agents_2.ipynb
"""
from langchain_openai import ChatOpenAI
from core.config import settings
import logging
import os

logger = logging.getLogger(__name__)

# Initialize LLM
llm = ChatOpenAI(
    model="deepseek-ai/DeepSeek-V3.2",
    api_key=os.getenv("DEEPINFRA_API_KEY"),
    base_url=os.getenv("DEEPINFRA_API_BASE_URL"),
    temperature=0.05,
    max_tokens=5000,
)


def company_analysis_agent(company_name: str, company_website: str) -> str:
    """
    Extract company's main delivery and product from the website.
    Provides a short description and list of latest announcements and products.
    
    Args:
        company_name: Name of the company
        company_website: Website URL of the company
        
    Returns:
        String containing company analysis
    """
    try:
        prompt = f"""
        You are an agentic expert in extracting the company's main delivery and product from their website.
        Provide a short description for the company's main delivery and product.
        Provide a list of the company's latest announcements and products.
        return a json object with the following keys:
        - company_domain: the company's domain (e.g. cybersecurity, gaming, cloud_computing, etc.)
        - company_value_proposition: the company's value proposition
        - company_products: a list of the company's latest announcements and products
        - latest_anouncements: a list of the company's latest announcements
        The company you need to assess is {company_name} and their website is: {company_website}
        """
        
        response = llm.invoke(prompt)
        return response.content
    except Exception as e:
        logger.error(f"Error in company_analysis_agent: {e}")
        raise


def competition_analysis_agent(company_name: str, company_website: str) -> str:
    """
    Find competitors and their products.
    Uses competitor finder tools to identify relevant competitors.
    
    Args:
        company_name: Name of the company
        company_website: Website URL of the company
        
    Returns:
        String containing competitor analysis
    """
    try:
        prompt = f"""
        You are an expert in finding competitors and their products.
        Find the most relevant competitors to the provided company by website and their products.
        Use the following websites to find competitors:
        https://www.semrush.com/free-tools/competitor-finder/
        https://www.similarweb.com/website
        The company you need to assess is {company_name} and their website is: {company_website}
        """
        
        response = llm.invoke(prompt)
        return response.content
    except Exception as e:
        logger.error(f"Error in competition_analysis_agent: {e}")
        raise

