import logging
import os
import re
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, render_template_string

# Handle Selenium imports with fallback
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logging.warning("Selenium not available. Install with: pip install selenium webdriver-manager")

import csv

# Create folders if they don't exist
os.makedirs('logs', exist_ok=True)
os.makedirs('csv', exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/l10n_testing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# =================== CONFIGURATION ===================
CONFIG = {
    'timeout': 10,
    'user_agent': 'LocalizationTester/1.0',
    'max_links_per_page': 200,
    'selenium_wait_time': 15,
    'exclude_patterns': [
        r'javascript:', r'data:', r'mailto:', r'tel:', r'#',
        r'\.doc$', r'\.docx$', r'\.zip$', r'\.exe$', r'pag='
    ],
    'supported_languages': {
        'fr': ['/fr/', '/fr-fr/', '/french/', '/francais/'],
        'es': ['/es/', '/es-es/', '/spanish/', '/espanol/'],
        'de': ['/de/', '/de-de/', '/german/', '/deutsch/'],
        'it': ['/it/', '/it-it/', '/italian/', '/italiano/'],
        'ru': ['/ru/', '/ru-ru/', '/russian/', '/russkiy/']
    }
}


# =================== STATUS CONSTANTS ===================
class Status:
    SUCCESS = 'success'
    ERROR = 'error'
    DEFECT = 'defect'
    WARNING = 'warning'
    LOCALIZATION_DEFECT = 'localization_defect'


# =================== IMPROVED HTML TEMPLATE ===================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>🌐 Bulk Localization Link Checker</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; color: #333; }
        .form-group input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
        .btn { background: #007bff; color: white; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; margin-right: 10px; }
        .btn:hover { background: #0056b3; }
        .error-status { color: #dc3545; font-weight: bold; }
        .success-status { color: #28a745; font-weight: bold; }
        .warning-status { color: #ffc000; font-weight: bold; }
        .defect-status { color: #fd7e14; font-weight: bold; }
        .example { font-style: italic; color: #666; margin-top: 5px; font-size: 14px;}
        .stats { background: #e9ecef; padding: 20px; border-radius: 6px; margin: 20px 0; }
        .stats h3 { margin-top: 0; color: #495057; }
        .link-item { padding: 10px; border-bottom: 1px solid #eee; }
        .link-item:hover { background: #f8f9fa; }
        .link-item:last-child { border-bottom: none; }
        .alert { padding: 15px; border-radius: 4px; margin-bottom: 20px; }
        .alert-warning { background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
        .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .localization-info { background: #d1ecf1; padding: 20px; border-radius: 6px; margin: 20px 0; border-left: 4px solid #17a2b8; }
        .test-section { background: #e3f2fd; padding: 20px; border-radius: 6px; margin: 20px 0; border-left: 4px solid #2196f3; }
        .test-section h3 { margin-top: 0; color: #1976d2; }
        .loading { font-style: italic; margin-top: 10px; display: none; color: #007bff; font-weight: bold; }
        .grid-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
    </style>
    <script>
        function showLoading() {
            document.querySelector('.loading').style.display = 'block';
            document.querySelector('.btn').disabled = true;
            const result = document.querySelector('.result');
            if (result) result.style.display = 'none';
        }
    </script>
</head>
<body>
    <div class="container">
        <h1>🌐 Bulk Localization Link Checker</h1>
        <p><strong>Purpose:</strong> Check all links on localized webpages to ensure they work correctly and point to proper localized versions.</p>
        
        <div class="test-section">
            <h3>🔍 Bulk Link Analysis</h3>
            <form method="post" onsubmit="showLoading()">
                <div class="form-group">
                    <label for="localization_urls">Enter Localization URLs (one per line):</label>
                    <textarea id="localization_urls" name="localization_urls" 
                              placeholder="https://www.nakivo.com/de/&#10;https://www.nakivo.com/fr/&#10;https://www.nakivo.com/es/" 
                              rows="8" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px;"></textarea>
                    <div class="example">Example: Enter multiple URLs, one per line</div>
                </div>
                
                <button type="submit" class="btn">🔍 Check All URLs</button>
                <div class="loading">⏳ Analyzing multiple pages... This may take several minutes.</div>
            </form>
        </div>
        
        <div class="result">
            {% if stats and stats.get('error') %}
            <div class="alert alert-warning">
                <strong>❌ Error:</strong> {{ stats.error }}
            </div>
            {% endif %}
    
            {% if stats and stats.get('warning') %}
            <div class="alert alert-warning">
                <strong>⚠️ Warning:</strong> {{ stats.warning }}
            </div>
            {% endif %}
    
            {% if stats and not stats.get('error') and not stats.get('warning') %}
            <div class="alert alert-success">
                <strong>✅ Analysis Complete!</strong>
                    
                    With {{stats.total_urls}} URL, tool found {{ stats.total_links }} links 
                    {% set results = [] %}
                    
                    {% if stats.total_working_links > 0 %}
                        {% set results = results + [stats.total_working_links|string + ' success'] %}
                    {% endif %}
                    
                    {% if stats.total_broken_links > 0 %}
                        {% set results = results + [stats.total_broken_links|string + ' broken'] %}
                    {% endif %}
                    
                    {% if stats.total_localization_defects > 0 %}
                        {% set results = results + [stats.total_localization_defects|string + ' defect'] %}
                    {% endif %}
                    
                    {% if stats.total_warning_links > 0 %}
                        {% set results = results + [stats.total_warning_links|string + ' warning'] %}
                    {% endif %}
                    
                    {% if results %}
                        ({{ results|join(', ') }})
                    {% endif %}
                    
                    with {{ stats.overall_success_rate|round(1) }}% overall success rate.
            </div>
            {% endif %}
    
            {% if bulk_results %}
                <div class="stats">
                    <h3>📊 Bulk Analysis Summary</h3>
                    <div class="grid-stats">
                        <div><strong>Total URLs:</strong> {{ stats.total_urls }}</div>
                        <div><strong>Successful URLs:</strong> <span class="success-status">{{ stats.successful_urls }}</span></div>
                        <div><strong>Error URLs:</strong> <span class="error-status">{{ stats.error_urls }}</span></div>
                        <div><strong>Warning URLs:</strong> <span class="warning-status">{{ stats.warning_urls }}</span></div>
                        <div><strong>Total Links:</strong> {{ stats.total_links }}</div>
                        <div><strong>Localization Defects:</strong> <span class="defect-status">{{ stats.total_localization_defects }}</span></div>
                        <div><strong>Broken Links:</strong> <span class="error-status">{{ stats.total_broken_links }}</span></div>
                        <div><strong>Warning Links:</strong> <span class="warning-status">{{ stats.total_warning_links }}</span></div>
                        <div><strong>Success Rate:</strong> <span class="success-status">{{ (stats.overall_success_rate or 0)| round(1) }}%</span></div>
                        <div><strong>Processing Time:</strong> {{ "%.2f"|format(stats.processing_time) }}s</div>
                    </div>
                </div>
                
                <h3>🔗 Detailed Results by URL</h3>
                {% for result in bulk_results %}
                <div class="link-item" style="border: 2px solid #ddd; margin: 10px 0; padding: 15px;">
                    <h4 style="margin-top: 0;">
                        <span class="{{ 'success-status' if result.status == 'success' 
                        else 'error-status' if result.status == 'error' 
                        else 'warning-status' if result.status == 'warning'}}">
                            {{ result.url }}
                        </span>
                    </h4>
                    
                    {% if result.message %}
                    <div style="margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 4px;">
                        <strong>Message:</strong> {{ result.message }}
                    </div>
                    {% endif %}
                    
                    {% if result.stats %}
                    <div style="margin: 10px 0;">
                        <strong>Language:</strong> {{ result.stats.language_detected.upper() }} | 
                        <strong>Links:</strong> {{ result.stats.total_links }} | 
                        <strong>Success Rate:</strong> {{(result.stats.success_rate or 0)|round(1)}}%  |||  
                        <strong>Defect:</strong> {{ result.stats.localization_defects }} | 
                        <strong>Broken:</strong> {{ result.stats.broken_links }} | 
                        <strong>Warning:</strong> {{ result.stats.warning_links }}
                    </div>
                    {% endif %}
                    
                    {% if result.links %}
                    <div style="margin-top: 10px;">
                        <strong>Link Details:</strong>
                        {% for link in result.links[:50] %}  <!-- Show first 50 links -->
                        <div style="margin: 5px 0; padding: 5px; background: #f8f9fa; font-size: 12px;">
                            <span class="{{ 'success-status' if link.status == 'success' 
                            else 'error-status' if link.status == 'error' 
                            else 'defect-status' if link.status == 'localization_defect' 
                            else 'warning-status' if link.status == 'warning'}}">
                                {{ link.status_code or 'N/A' }} - {{ link.status.replace('_', ' ').title() }}
                            </span>
                            <br><a href="{{ link.url }}" target="_blank">{{ link.url }}</a>
                            
                            {% if link.link_text %}
                            <div style="margin-top: 5px; font-size: 12px">
                                <strong>Link Text:</strong> "{{ link.link_text[:80] }}{% if link.link_text |length > 80 %}...{% endif %}"
                            </div>
                            {% endif %}
                            {% if link.issue %}
                                <div style="margin-top: 5px; font-size: 12px;">
                                <strong>Issue:</strong> {{ link.issue}}
                                </div>
                            {% endif %}
                        </div>
                        {% endfor %}
                        
                        {% if result.links|length > 50 %}
                        <div style="font-style: italic; color: #666;">... and {{ result.links|length - 50 }} more links</div>
                        {% endif %}
                    </div>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </div>
</body>
</html>
"""


# =================== MAIN LINK CHECKER CLASS ===================
class LinkChecker:
    """Main class for handling link checking operations"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': CONFIG['user_agent']})
        self.chrome_driver = None

    def get_chrome_driver(self):
        """Get Chrome driver with proper configuration"""
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium not available. Install with: pip install selenium webdriver-manager")

        if self.chrome_driver is None:
            try:
                options = Options()
                options.add_argument("--headless")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")
                options.add_argument("--disable-extensions")
                options.add_argument(f"--user-agent={CONFIG['user_agent']}")

                service = Service(ChromeDriverManager().install())
                self.chrome_driver = webdriver.Chrome(service=service, options=options)
                logger.info("✅ Chrome driver initialized successfully")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Chrome driver: {e}")
                raise RuntimeError(f"Chrome driver initialization failed: {e}")
        return self.chrome_driver

    def cleanup(self):
        """Clean up resources"""
        if self.chrome_driver:
            try:
                self.chrome_driver.quit()
            except:
                pass
            self.chrome_driver = None

    def is_file_link(self, url: str) -> bool:
        """Return True if the URL points to a file (pdf, zip, docx, etc.)"""
        return bool(re.search(r'\.(pdf|zip|docx?|xlsx?|pptx?|exe|rar|tar\.gz|7z)$', url, re.IGNORECASE))

    def is_valid_url(self, url: str) -> bool:
        """Check if URL is valid"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc]) and result.scheme in ['http', 'https']
        except:
            return False

    def has_locale_prefix(self, url: str) -> bool:
        """Check if URL has locale prefix"""
        parsed = urlparse(url)
        return bool(re.match(r'^/([a-z]{2})(?:-[a-z]{2})?/', parsed.path))

    def detect_language(self, url: str) -> str:
        """Detect language from URL"""
        parsed = urlparse(url)
        path = parsed.path.lower()

        for lang, patterns in CONFIG['supported_languages'].items():
            if any(pattern in path for pattern in patterns):
                return lang
        return "en"

    def is_url_redirect(self, url: str) -> Dict:
        """Simple function to check if URL redirects to another URL"""
        try:
            # Use GET to follow redirects and get the final URL
            headers = {'User-Agent': CONFIG['user_agent']}
            response = self.session.get(url, timeout=CONFIG['timeout'], headers=headers, allow_redirects=True)
            response.raise_for_status()

            # Simple comparison - normalize URLs
            is_redirect = response.url.rstrip('/') != url.rstrip('/')

            return {
                'redirected': is_redirect,
                'final_url': response.url,
                'status_code': 200,
                'error': None
            }
        except Exception as e:
            return {
                'redirected': False,
                'final_url': None,
                'status_code': None,
                'error': str(e)
            }

    def extract_links(self, url: str) -> Tuple[List[Dict], str]:
        """Extract links from webpage"""
        try:
            # Try requests first (faster)
            response = self.session.get(url, timeout=CONFIG['timeout'])
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            links = self._parse_links(soup, url)
            page_title = self._get_page_title(soup)

            if links:
                logger.info(f"🔗 Found {len(links)} links using requests")
                return links, page_title

        except Exception as e:
            logger.warning(f"Requests failed, trying Selenium: {e}")

        # Fallback to Selenium
        if SELENIUM_AVAILABLE:
            try:
                driver = self.get_chrome_driver()
                driver.get(url)
                time.sleep(CONFIG['selenium_wait_time'])

                soup = BeautifulSoup(driver.page_source, 'html.parser')
                links = self._parse_links(soup, url)
                page_title = self._get_page_title(soup)

                logger.info(f"🔗 Found {len(links)} links using Selenium")
                return links, page_title

            except Exception as e:
                logger.error(f"❌ Selenium failed: {e}")

        logger.error("❌ Both requests and Selenium failed")
        return [], "Error loading page"

    def _get_page_title(self, soup: BeautifulSoup) -> str:
        """Safely extract page title"""
        try:
            if soup.title and soup.title.string:
                return soup.title.string.strip()
        except:
            pass
        return "No title"

    def _parse_links(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Parse links from BeautifulSoup object"""
        links = []

        for source in self.get_main_content_sections(soup):
            for link in source.find_all('a', href=True):
                href = link.get('href', '').strip()

                # Exclude links matching exclude_patterns (see next section)
                if any(re.search(pattern, href, re.IGNORECASE) for pattern in CONFIG['exclude_patterns']):
                    continue

                full_url = urljoin(base_url, href)
                link_text = link.get_text(strip=True)

                links.append({
                    'url': full_url,
                    'link_text': link_text,
                    'original_href': href
                })

        # Remove duplicates and limit
        seen = set()
        unique_links = []
        for link in links:
            if link['url'] not in seen:
                seen.add(link['url'])
                unique_links.append(link)

        if len(unique_links) > CONFIG['max_links_per_page']:
            logger.warning(f"⚠️ Limiting to {CONFIG['max_links_per_page']} links")
            unique_links = unique_links[:CONFIG['max_links_per_page']]

        return unique_links

    def get_main_content_sections(self, soup):
        """Get main or section or body tags."""
        main = soup.find('main')
        if not main:
            main = soup.body.find('main')
        if main and hasattr(main, 'find_all'):
            logger.info("Extracting links from <main> tag.")
            return [main]
        elif soup.body:
            sections = soup.body.find_all('section')
            if sections:
                logger.info("No <main> tag found. Extracting links from <section> tags in <body>.")
                return sections
            else:
                logger.info("No <main> or <section> tags found. Extracting links from <body>.")
                return [soup.body]
        else:
            logger.warning("No <main>, <section>, or <body> tag found. Extracting links from full page.")
            return [soup]

    def check_link_localization(self, link_url: str, locale: str) -> Dict:
        """Check if link is properly localized"""
        try:
            # First check if original link works
            response = self.session.get(link_url, timeout=CONFIG['timeout'], allow_redirects=True)
            if response.status_code != 200:
                return {
                    'status': Status.ERROR,
                    'status_code': response.status_code,
                    'issue': f"Link is broken (HTTP {response.status_code})"
                }
            parsed_link = urlparse(link_url)
            path = parsed_link.path.lower()

            # Check if the link not containing "nakivo.com" in its domain -> return message, do not run localization checks for these links
            if "nakivo.com" not in parsed_link.netloc.lower():
                return {
                    'status': Status.WARNING,
                    'status_code': response.status_code,
                    'issue': f"Not match nakivo.com"
                }

            # --- Custom logic for localized file links ---
            # e.g., /file_es.pdf, /file-es.pdf, /file_ES.pdf, /file-ES.pdf
            locale_pattern = rf"(_|-){locale}\.pdf$"
            if self.is_file_link(link_url) and re.search(locale_pattern, path, re.IGNORECASE):
                return self._check_localized_link(link_url)

            # --- Normal logic for HTML links ---
            # Check if link is already localized (for HTML pages)
            if re.match(rf'^/{locale}(/|$)', parsed_link.path):
                return self._check_localized_link(link_url)
            else:
                # Check if link is not localized
                return self._check_non_localized_link(link_url, locale)

        except Exception as e:
            logger.exception(f"❌ Error checking link {link_url}: {e}")
            return {
                'status': Status.ERROR,
                'status_code': None,
                'issue': f"Error checking link: {str(e)}"
            }

    def _check_localized_link(self, link_url: str) -> Dict:
        """Check already localized link, with custom logic for files"""
        try:
            response = self.session.get(link_url, timeout=CONFIG['timeout'], allow_redirects=True)
            if response.status_code == 200:
                # If the final URL is the same with the verify link -> success
                if response.url.rstrip('/') == link_url.rstrip('/'):
                    return {
                        'status': Status.SUCCESS,
                        'status_code': 200,
                        'issue': None
                    }
                # If the final URL is different with the verify link -> success, but warning redirect issue
                else:
                    return {
                        'status': Status.SUCCESS,
                        'status_code': 200,
                        'issue': f"Redirected to: {response.url}"
                    }
            # If the final link responds non-200 -> localization defect
            else:
                return {
                    'status': Status.LOCALIZATION_DEFECT,
                    'status_code': response.status_code,
                    'issue': f"Localized link returns {response.status_code}, {response.url}"
                }
        except Exception as e:
            return {
                'status': Status.ERROR,
                'status_code': None,
                'issue': f"Error check localized link: {str(e)}"
            }

    def _check_non_localized_link(self, link_url: str, locale: str) -> Dict:
        """Check non-localized link for potential localization issues"""
        # First check if original link works
        response = self.session.get(link_url, timeout=CONFIG['timeout'], allow_redirects=True)
        if response.status_code != 200:
            return {
                'status': Status.ERROR,
                'status_code': response.status_code,
                'issue': f"Link is broken (HTTP {response.status_code})"
            }

        # Check if a localized version should exist
        expected_localized = self._get_expected_localized_url(link_url, locale)
        if expected_localized and expected_localized != link_url:
            # Check if localized version exists
            try:
                resp = self.session.get(expected_localized, timeout=CONFIG['timeout'], allow_redirects=True)
                final_url = resp.url

                if resp.status_code == 200:
                    # Normalize URLs by removing fragments for comparison
                    original_link_clean = self._remove_fragments(link_url)
                    expected_localized_clean = self._remove_fragments(expected_localized)
                    final_url_clean = self._remove_fragments(final_url)

                    # If the final link is different with non-localized link and expected localized link -> warning message
                    if final_url_clean != original_link_clean and final_url_clean != expected_localized_clean:
                        return {
                            'status': Status.SUCCESS,
                            'status_code': 200,
                            'issue': f"Final link - {final_url} is different with non-localized link and expected localized link {expected_localized}"
                        }
                    # If the final link and the expected localized URL exists as a real page, but the link does not point to it -> localization defect
                    elif final_url_clean != original_link_clean and final_url_clean == expected_localized_clean:
                        return {
                            'status': Status.LOCALIZATION_DEFECT,
                            'status_code': 200,
                            'issue': f"Should link to localized version: {expected_localized}"
                        }
                    # If the final link is different with expected localized link, the same with non-localized link -> no localized version exists, redirect to default version
                    # final_url_clean == original_link_clean and final_url_clean == expected_localized_clean:
                    else:
                        return {
                            'status': Status.SUCCESS,
                            'status_code': 200,
                            'issue': f"No localized version exists - {expected_localized}; so redirects to default version: {final_url}"
                        }
                else:
                    # Localization expected link: redirect return 404 or other error: not exist -> no defect
                    return {
                        'status': Status.SUCCESS,
                        'status_code': None,
                        'issue': f"{resp.status_code} - No localized version exists - {expected_localized}"
                    }
            except Exception as e:
                return {
                    'status': Status.ERROR,
                    'status_code': None,
                    'issue': f"Error check non-localized link: {str(e)}"
                }
        else:
            return {
                'status': Status.SUCCESS,
                'status_code': 200,
                'issue': f"No localized version exists - {expected_localized}"
            }

    def _remove_fragments(self, url: str) -> str:
        """Remove query parameters and fragments from URL for comparison"""
        try:
            parsed = urlparse(url)
            # Reconstruct URL without query and fragment
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            return clean_url.rstrip('/')
        except:
            return url.rstrip('/')

    def _get_expected_localized_url(self, url: str, locale: str) -> Optional[str]:
        """Get expected localized URL with custom PDF logic"""
        parsed = urlparse(url)
        path = parsed.path

        # Custom logic for PDF files
        if path.lower().endswith('.pdf'):
            base_path = path[:-4]  # Remove .pdf
            if locale.lower() == 'es':
                localized_path = f"{base_path}_ES.pdf"
            else:
                localized_path = f"{base_path}-{locale}.pdf"
            return f"{parsed.scheme}://{parsed.netloc}{localized_path}"

        # Default: add locale to path if not already present
        if not re.match(rf'^/{locale}(/|$)', parsed.path):
            localized_path = f"/{locale}{parsed.path}"
            return f"{parsed.scheme}://{parsed.netloc}{localized_path}"

        return None

    def process_bulk_urls(self, urls: List[str]) -> List[Dict]:
        """Process multiple URLs and return results for each"""
        results = []

        for i, url in enumerate(urls, 1):
            logger.info(f"Processing URL {i}/{len(urls)}: {url}")

            try:
                # Validate URL format
                if not url or not url.strip():
                    logger.warning(f"⚠️ Empty URL at position {i}")
                    results.append({
                        'url': url,
                        'status': 'error',
                        'message': 'Empty URL provided',
                        'links': [],
                        'stats': None
                    })
                    continue

                url = url.strip()

                # Use existing validation logic
                if not self.is_valid_url(url):
                    logger.warning(f"⚠️ Invalid URL format: {url}")
                    results.append({
                        'url': url,
                        'status': 'error',
                        'message': f'Invalid URL format: {url}',
                        'links': [],
                        'stats': None
                    })
                    continue

                if not self.has_locale_prefix(url):
                    logger.warning(f"⚠️ Missing locale prefix: {url}")
                    results.append({
                        'url': url,
                        'status': 'error',
                        'message': f'URL must contain locale prefix: {url}',
                        'links': [],
                        'stats': None
                    })
                    continue

                # Check redirect with safety
                logger.info(f"🔍 Checking redirect for: {url}")
                redirect_info = self.is_url_redirect(url)

                # Check for redirect errors
                if redirect_info['error']:
                    results.append({
                        'url': url,
                        'status': 'error',
                        'message': f'Cannot access URL: {redirect_info["error"]}',
                        'links': [],
                        'stats': None
                    })
                    continue

                # Check if redirected
                if redirect_info['redirected']:
                    results.append({
                        'url': url,
                        'status': 'warning',
                        'message': f'URL redirects to: {redirect_info["final_url"]}',
                        'links': [],
                        'stats': None
                    })
                    continue

                # Extract and check links (existing logic)
                logger.info(f"🔍 Extracting links from: {url}")
                links_data, page_title = self.extract_links(url)

                if not links_data:
                    logger.warning(f"⚠️ No links found on: {url}")
                    results.append({
                        'url': url,
                        'status': 'warning',
                        'message': f'No links found on page',
                        'links': [],
                        'stats': None
                    })
                    continue

                # Check each link
                locale = self.detect_language(url)
                link_results = []

                for j, link_data in enumerate(links_data, 1):
                    logger.info(f"🔍 Checking link {j}/{len(links_data)}: {link_data['url']}")

                    try:
                        result = self.check_link_localization(link_data['url'], locale)

                        link_results.append({
                            'url': link_data['url'],
                            'link_text': link_data['link_text'],
                            'status': result['status'],
                            'status_code': result['status_code'],
                            'issue': result['issue']
                        })
                    except Exception as e:
                        logger.error(f"❌ Error checking link {link_data['url']}: {e}")
                        link_results.append({
                            'url': link_data['url'],
                            'link_text': link_data.get('link_text', ''),
                            'status': Status.ERROR,
                            'status_code': None,
                            'issue': f'Error: {str(e)}'
                        })

                # Calculate stats
                total_links = len(link_results)
                working_links = len([r for r in link_results if r.get('status') == Status.SUCCESS])
                broken_links = len([r for r in link_results if r.get('status') in [Status.ERROR, Status.DEFECT]])
                localization_defects = len([r for r in link_results if r.get('status') == Status.LOCALIZATION_DEFECT])
                warning_links = len([r for r in link_results if r.get('status') == Status.WARNING])

                stats = {
                    'base_url': url,
                    'language_detected': locale,
                    'page_title': page_title or 'No title',
                    'total_links': total_links,
                    'working_links': working_links,
                    'broken_links': broken_links,
                    'localization_defects': localization_defects,
                    'warning_links': warning_links,
                    'success_rate': (working_links / total_links * 100) if total_links else 0
                }

                logger.info(f"✅ Successfully processed: {url} - {total_links} links,"
                            f" {working_links} working, {localization_defects} localization defect, {broken_links} broken")

                results.append({
                    'url': url,
                    'status': 'success',
                    'message': None,
                    'links': link_results,
                    'stats': stats
                })

            except Exception as e:
                logger.exception(f"Unexpected error processing {url}: {e}")
                results.append({
                    'url': url,
                    'status': 'error',
                    'message': f'Unexpected error processing: {str(e)}',
                    'links': [],
                    'stats': None
                })

        return results


# =================== UTILITY FUNCTIONS ===================
def generate_csv_report(results: List[Dict], base_url: str) -> str:
    """Generate CSV report"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"csv/l10n_{timestamp}.csv"

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['url', 'link_text', 'status_code', 'status', 'issue', 'base_url']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for result in results:
            writer.writerow({
                'url': result['url'],
                'link_text': result.get('link_text', ''),
                'status_code': result.get('status_code', ''),
                'status': result.get('status', ''),
                'issue': result.get('issue', ''),
                'base_url': base_url
            })

    logger.info(f"📄 CSV report generated: {filename}")
    return filename


# =================== FLASK ROUTES ===================
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        urls_input = request.form.get("localization_urls", "").strip()

        # Parse URLs with validation
        urls = [url.strip() for url in urls_input.split('\n') if url.strip()]

        if not urls:
            return render_template_string(HTML_TEMPLATE,
                                          stats={'error': 'Please enter at least one URL'},
                                          links=[])

        logger.info(f"🔄 Starting bulk processing for {len(urls)} URLs")

        # Initialize link checker
        checker = LinkChecker()

        try:
            start_time = time.time()

            # Process all URLs
            results = checker.process_bulk_urls(urls)

            # Validate results
            if results is None:
                logger.error("❌ Process_bulk_urls returned None")
                return render_template_string(HTML_TEMPLATE,
                                              stats={'error': 'Processing failed - returned None'},
                                              links=[])

            # Calculate overall stats
            total_urls = len(results)
            successful_urls = len([r for r in results if r.get('status') == 'success'])
            error_urls = len([r for r in results if r.get('status') == 'error'])
            warning_urls = len([r for r in results if r.get('status') == 'warning'])

            total_links = sum(len(r.get('links', [])) for r in results if r.get('links'))
            total_working_links = sum(r.get('stats', {}).get('working_links', 0) for r in results if r.get('stats'))
            total_broken_links = sum(r.get('stats', {}).get('broken_links', 0) for r in results if r.get('stats'))
            total_warning_links = sum(r.get('stats', {}).get('warning_links', 0) for r in results if r.get('stats'))
            total_localization_defects = sum(
                r.get('stats', {}).get('localization_defects', 0) for r in results if r.get('stats'))

            processing_time = time.time() - start_time

            # Safe calculation for success rate
            overall_success_rate = 0
            if total_links > 0:
                overall_success_rate = (total_working_links / total_links * 100)

            overall_stats = {
                'total_urls': total_urls,
                'successful_urls': successful_urls,
                'error_urls': error_urls,
                'warning_urls': warning_urls,
                'total_links': total_links,
                'total_working_links': total_working_links,
                'total_broken_links': total_broken_links,
                'total_localization_defects': total_localization_defects,
                'total_warning_links': total_warning_links,
                'overall_success_rate': overall_success_rate,
                'processing_time': processing_time
            }

            logger.info(f"✅ Bulk processing completed: {successful_urls}/{total_urls} URLs successful")

            return render_template_string(HTML_TEMPLATE,
                                          stats=overall_stats,
                                          bulk_results=results)

        except Exception as e:
            logger.exception(f"❌ Unexpected error in bulk processing: {e}")
            return render_template_string(HTML_TEMPLATE,
                                          stats={'error': f'Unexpected error in bulk processing: {str(e)}'},
                                          links=[])
        finally:
            # Clean up resources
            checker.cleanup()

    return render_template_string(HTML_TEMPLATE, stats=None, links=None)


if __name__ == "__main__":
    logger.info("🚀 Starting Bulk Localization Link Checker")
    app.run(debug=True, host="0.0.0.0", port=4200)
