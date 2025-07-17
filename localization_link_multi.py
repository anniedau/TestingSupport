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


# =================== UPDATED HTML TEMPLATE ===================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>🌐 Multi-Localization Link Checker</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; color: #333; }
        .form-group input[type="text"] { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
        .checkbox-group { display: flex; flex-wrap: wrap; gap: 15px; margin-top: 10px; }
        .checkbox-item { display: flex; align-items: center; }
        .checkbox-item input { margin-right: 5px; }
        .btn { background: #007bff; color: white; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; margin-right: 10px; }
        .btn:hover { background: #0056b3; }
        .error-status { color: #dc3545; font-weight: bold; }
        .success-status { color: #28a745; font-weight: bold; }
        .warning-status { color: #ffc000; font-weight: bold; }
        .defect-status { color: #fd7e14; font-weight: bold; }
        .example { font-style: italic; color: #666; margin-top: 5px; font-size: 14px; }
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
        .grid-stats { display: flex; flex-wrap: wrap; gap: 15px; align-items: flex-start; }
        .grid-stats > div { min-width: 180px; flex: 1 1 auto; word-break: break-all; /* For long URLs */ overflow-wrap: anywhere; }
        .localization-results { margin-top: 30px; }
        .localization-group { border: 1px solid #ddd; border-radius: 6px; margin-bottom: 20px; overflow: hidden; }
        .localization-header { background: #f8f9fa; padding: 15px; border-bottom: 1px solid #ddd; }
        .localization-header h4 { margin: 0; color: #495057; }
        .localization-content { padding: 15px; }
        .select-locale {
            display: flex;
            align-items: center; /* vertically align */
            gap: 8px; /* space between label and button (optional) */
        }
        .select-all-btn { background: #28a745; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; margin-left: 10px; }
        .select-all-btn:hover { background: #218838; }
    </style>
    <script>
        function showLoading() {
            document.querySelector('.loading').style.display = 'block';
            document.querySelector('.btn').disabled = true;
            const result = document.querySelector('.result');
            if (result) result.style.display = 'none';
        }
        
        function toggleAll() {
            const checkboxes = document.querySelectorAll('.checkbox-item input[type="checkbox"]');
            const allChecked = Array.from(checkboxes).every(cb => cb.checked);
            checkboxes.forEach(cb => cb.checked = !allChecked);
            updateSelectAllButton();
        }
        
        function updateSelectAllButton() {
            const checkboxes = document.querySelectorAll('.checkbox-item input[type="checkbox"]');
            const allChecked = Array.from(checkboxes).every(cb => cb.checked);
            const button = document.querySelector('.select-all-btn');
            button.textContent = allChecked ? 'Deselect All' : 'Select All';
        }
        
        document.addEventListener('DOMContentLoaded', function() {
            const checkboxes = document.querySelectorAll('.checkbox-item input[type="checkbox"]');
            checkboxes.forEach(cb => cb.addEventListener('change', updateSelectAllButton));
            updateSelectAllButton();
        });
    </script>
</head>
<body>
    <div class="container">
        <h1>🌐 Multi-Localization Link Checker</h1>
        <p><strong>Purpose:</strong> Check links across multiple localized versions of a webpage to ensure they work correctly.</p>
        
        <div class="test-section">
            <h3>🔍 Multi-Localization Analysis</h3>
            <form method="post" onsubmit="showLoading()">
                <div class="form-group">
                    <label for="base_url">Enter Base URL (Non-localized):</label>
                    <input type="text" id="base_url" name="base_url" 
                           placeholder="https://www.nakivo.com/" required>
                    <div class="example">Example: https://www.nakivo.com/ (without language prefix)</div>
                </div>
                
                <div class="form-group">
                    <div class ="select-locale"> 
                        <label>Select Localizations to Check:</label> 
                        <button type="button" class="select-all-btn" onclick="toggleAll()">Select All</button>
                    </div>
                    <div class="checkbox-group">
                        <div class="checkbox-item">
                            <input type="checkbox" id="de" name="localizations" value="de">
                            <label for="de">German (de)</label>
                        </div>
                        <div class="checkbox-item">
                            <input type="checkbox" id="fr" name="localizations" value="fr">
                            <label for="fr">French (fr)</label>
                        </div>
                        <div class="checkbox-item">
                            <input type="checkbox" id="es" name="localizations" value="es">
                            <label for="es">Spanish (es)</label>
                        </div>
                        <div class="checkbox-item">
                            <input type="checkbox" id="it" name="localizations" value="it">
                            <label for="it">Italian (it)</label>
                        </div>
                        <div class="checkbox-item">
                            <input type="checkbox" id="ru" name="localizations" value="ru">
                            <label for="ru">Russian (ru)</label>
                        </div>
                    </div>
                </div>
                
                <button type="submit" class="btn">🔍 Check All Selected Localizations</button>              
                <div class="loading">⏳ Analyzing multiple localizations... This may take several minutes.</div>
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
                    Processed {{ stats.total_localizations }} localization  
                    {% if stats.total_localization_defects or stats.total_broken_links or stats.total_warning_links%}
                    ({% if stats.total_localization_defects%}{{stats.total_localization_defects}} defect{% endif %}{% if stats.total_broken_links%},
                    {{stats.total_broken_links}} broken{% endif %}{% if stats.total_warning_links%},
                    {{stats.total_warning_links}} warning{% endif %}){% endif %}
                    with {{ stats.overall_success_rate|round(1) }}% overall success rate.
                </div>
    
                <div class="localization-info">
                    <h3>📊 Overall Summary</h3>
                    <div class="grid-stats">
                        <div><strong>Base URL:</strong> <a href="{{ stats.base_url }}" target="_blank" style="color: #007bff">
                        {{  stats.base_url }}</a> </div>
                        <div><strong>Localization Checked:</strong> {{ stats.total_localizations }}</div>
                        <div><strong>Total Links:</strong> {{ stats.total_links }}</div>
                        <div><strong>Success Rate:</strong> {{ stats.overall_success_rate|round(1) }}%</div>
                        <div><strong>Working Links:</strong> {{ stats.total_working_links }}</div>
                        <div><strong>Broken Links:</strong> {{ stats.total_broken_links }}</div>
                        <div><strong>Localization Defects:</strong> {{ stats.total_localization_defects }}</div>
                        <div><strong>Warning Links:</strong> {{ stats.total_warning_links }}</div>
                        <div><strong>Processing Time:</strong> {{ "%.2f"|format(stats.processing_time) }}s</div>
                    </div>
                </div>
        
                <div class="localization-results">
                    {% for locale_result in localization_results %}
                        <div class="localization-group">
                            <div class="localization-header">
                                <h4>🌍 {{ locale_result.locale.upper() }} - <a href="{{ locale_result.localized_url }}"
                                 target="_blank" style="color: #007bff; text-decoration: none;">{{ locale_result.localized_url }}</a></h4><br>
                                <div class="grid-stats">
                                    <div><strong>Total Links:</strong> {{ locale_result.stats.total_links }}</div>
                                    <div><strong>Working:</strong> <span class="success-status">{{ locale_result.stats.working_links }}</span></div>
                                    <div><strong>Broken:</strong> <span class="error-status">{{ locale_result.stats.broken_links }}</span></div>
                                    <div><strong>Defect:</strong> <span class="defect-status">{{ locale_result.stats.localization_defects }}</span></div>
                                    <div><strong>Warning:</strong> <span class="warning-status">{{ locale_result.stats.warning_links }}</span></div>
                                    <div><strong>Success Rate:</strong> {{ locale_result.stats.success_rate|round(1) }}%</div>
                                </div>
                            </div>
                            
                            <div class="localization-content">
                                {% if locale_result.error %}
                                <div class="alert alert-warning">
                                    <strong>❌ Error:</strong> {{ locale_result.error }}
                                </div>
                                {% else %}
                                
                                <strong>🔗 Link Details</strong>
                                {% for result in locale_result.links %}
                                <div class="link-item">
                                    <div style="display: flex; justify-content: space-between; align-items: center;">
                                        <span class="{{ 'success-status' if result.status == 'success' 
                                        else 'error-status' if result.status == 'error' 
                                        else 'defect-status' if result.status == 'localization_defect' 
                                        else 'warning-status' if result.status == 'warning'}}">
                                            {{ result.status_code or 'N/A' }} - {{ result.status.replace('_', ' ').title() }}
                                        </span>
                                    </div>
                                    <div style="margin-top: 5px;">
                                        <a href="{{ result.url }}" target="_blank" style="color: #007bff; text-decoration: none;">
                                        {{ result.url }}</a>
                                    </div>
                                    {% if result.link_text %}
                                    <div style="margin-top: 5px; font-size: 12px;">
                                        <strong>Link Text:</strong> "{{ result.link_text[:80] }}{% if result.link_text|length > 80 %}...{% endif %}"
                                    </div>
                                    {% endif %}
                                    {% if result.issue %}
                                    <div style="margin-top: 5px; font-size: 12px;">
                                        <strong>Issue:</strong> {{ result.issue }}
                                    </div>
                                    {% endif %}
                                </div>
                                {% endfor %}
                                {% endif %}
                            </div>
                        </div>
                    {% endfor %}
                </div>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""


# =================== LINK CHECKER CLASS (REUSING EXISTING LOGIC) ===================
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

    def create_localized_url(self, base_url: str, locale: str) -> str:
        """Create localized URL from base URL"""
        parsed = urlparse(base_url)
        # Add locale prefix to path
        localized_path = f"/{locale}{parsed.path}".rstrip('/')
        if not localized_path.endswith('/'):
            localized_path += '/'
        return f"{parsed.scheme}://{parsed.netloc}{localized_path}"

    def is_url_accessible(self, url: str) -> Tuple[bool, Optional[str]]:
        """Check if URL is accessible"""
        try:
            response = self.session.get(url, timeout=CONFIG['timeout'], allow_redirects=True)
            if response.status_code == 200:
                return True, None
            else:
                return False, f"HTTP {response.status_code}"
        except Exception as e:
            return False, str(e)

    def is_url_redirect(self, url: str) -> Dict:
        """Check if URL redirects to another URL"""
        try:
            # Use GET to follow redirects and get the final URL
            response = self.session.get(url, timeout=CONFIG['timeout'], allow_redirects=True)
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

    def check_url_redirect(self, url: str) -> Dict:
        """Check if URL redirects and return appropriate status"""
        redirect_info = self.is_url_redirect(url)

        # If there's an error accessing the URL
        if redirect_info['error']:
            return {'error': f'Cannot access URL: {redirect_info["error"]}'}
        # If URL redirects to a different URL
        elif redirect_info['redirected']:
            return {
                'warning': f'URL redirects to other link: {redirect_info["final_url"]}. Input link: {url}'}
        # URL is accessible and doesn't redirect (success case)
        else:
            return {'success': f'URL is accessible and doesn\'t redirect: {url}'}

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

                # Exclude links matching exclude_patterns
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
            main = soup.body.find('main') if soup.body else None
        if main and hasattr(main, 'find_all'):
            logger.info("Extracting links from <main> tag.")
            return [main]
        elif soup.body:
            sections = soup.body.find_all('section')
            if sections:
                logger.info("No <main> tag found. Extracting links from <section> tags in <body>.")
                return sections
            else:
                logger.info("No <main>, <section>, or <body> tag found. Extracting links from <body>.")
                return [soup.body]
        else:
            logger.warning("No <main>, <section>, or <body> tag found. Extracting links from full page.")
            return [soup]

    def check_link_localization(self, link_url: str, base_url: str, locale: str) -> Dict:
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
                return self._check_non_localized_link(link_url, base_url, locale)

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

    def _check_non_localized_link(self, link_url: str, base_url: str, locale: str) -> Dict:
        """Check non-localized link for potential localization issues"""
        # First check if original link works
        response = self.session.get(link_url, timeout=CONFIG['timeout'], allow_redirects=True)
        if response.status_code != 200:
            return {
                'status': Status.ERROR,
                'status_code': response.status_code,
                'issue': f"Link is broken (HTTP {response.status_code})"
            }

        try:
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
        except Exception as e:
            return {
                'status': Status.ERROR,
                'status_code': None,
                'issue': f"Error: {str(e)}"
            }

    def _remove_fragments(self, url: str) -> str:
        """Remove query parameters and fragments from URL for comparison"""
        try:
            parsed = urlparse(url)
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

    def process_single_localization(self, base_url: str, locale: str) -> Dict:
        """Process a single localization and return results"""
        logger.info(f"🌍 Processing localization: {locale}")

        # Create localized URL
        localized_url = self.create_localized_url(base_url, locale)

        try:
            # Check if localized URL is accessible
            accessible, error_msg = self.is_url_accessible(localized_url)
            if not accessible:
                return {
                    'locale': locale,
                    'localized_url': localized_url,
                    'error': f'Localized URL not accessible: {error_msg}',
                    'links': [],
                    'stats': {}
                }

            # Check for redirects
            redirect_info = self.is_url_redirect(localized_url)
            if redirect_info['error']:
                return {
                    'locale': locale,
                    'localized_url': localized_url,
                    'error': f'Cannot access URL: {redirect_info["error"]}',
                    'links': [],
                    'stats': {}
                }

            # Extract links
            links_data, page_title = self.extract_links(localized_url)
            if not links_data:
                return {
                    'locale': locale,
                    'localized_url': localized_url,
                    'error': f'No links found on the localized page',
                    'links': [],
                    'stats': {}
                }

            # Check each link
            results = []
            for link_data in links_data:
                result = self.check_link_localization(link_data['url'], localized_url, locale)
                results.append({
                    'url': link_data['url'],
                    'link_text': link_data['link_text'],
                    'status': result['status'],
                    'status_code': result['status_code'],
                    'issue': result['issue']
                })

            # Calculate statistics
            total_links = len(results)
            working_links = len([r for r in results if r['status'] == Status.SUCCESS])
            broken_links = len([r for r in results if r['status'] in [Status.ERROR, Status.DEFECT]])
            localization_defects = len([r for r in results if r['status'] == Status.LOCALIZATION_DEFECT])
            warning_links = len([r for r in results if r['status'] == Status.WARNING])

            stats = {
                'total_links': total_links,
                'working_links': working_links,
                'broken_links': broken_links,
                'localization_defects': localization_defects,
                'warning_links': warning_links,
                'success_rate': (working_links / total_links * 100) if total_links else 0,
                'page_title': page_title
            }

            logger.info(f"✅ Successfully processed {locale}: {localized_url} - {total_links} links,"
                        f" {working_links} working, {localization_defects} localization defect, {broken_links} broken")

            return {
                'locale': locale,
                'localized_url': localized_url,
                'error': None,
                'links': results,
                'stats': stats
            }

        except Exception as e:
            logger.exception(f"❌ Error processing localization {locale}: {e}")
            return {
                'locale': locale,
                'localized_url': localized_url,
                'error': f'Unexpected error: {str(e)}',
                'links': [],
                'stats': {}
            }


# =================== UTILITY FUNCTIONS ===================
def generate_csv_report(localization_results: List[Dict], base_url: str) -> str:
    """Generate CSV report for multiple localizations"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"csv/multi_l10n_{timestamp}.csv"

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['locale', 'localized_url', 'url', 'link_text', 'status_code', 'status', 'issue', 'base_url']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for locale_result in localization_results:
            if locale_result['error']:
                writer.writerow({
                    'locale': locale_result['locale'],
                    'localized_url': locale_result['localized_url'],
                    'url': '',
                    'link_text': '',
                    'status_code': '',
                    'status': 'error',
                    'issue': locale_result['error'],
                    'base_url': base_url
                })
            else:
                for result in locale_result['links']:
                    writer.writerow({
                        'locale': locale_result['locale'],
                        'localized_url': locale_result['localized_url'],
                        'url': result['url'],
                        'link_text': result.get('link_text', ''),
                        'status_code': result.get('status_code', ''),
                        'status': result.get('status', ''),
                        'issue': result.get('issue', ''),
                        'base_url': base_url
                    })

    logger.info(f"📄 Multi-localization CSV report generated: {filename}")
    return filename


# =================== FLASK ROUTES ===================
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # Required: Non-localized link: https://example.com/ and at least localization version [de, fr, es] checkboxes
        base_url = request.form.get("base_url", "").strip()
        selected_localizations = request.form.getlist("localizations")

        # Input validation
        if not base_url:
            return render_template_string(HTML_TEMPLATE,
                                          stats={'error': 'Please enter a base URL'},
                                          localization_results=[])

        if not selected_localizations:
            return render_template_string(HTML_TEMPLATE,
                                          stats={'error': 'Please select at least one localization'},
                                          localization_results=[])

        # Initialize link checker
        checker = LinkChecker()

        try:
            start_time = time.time()

            # Validate base URL
            if not checker.is_valid_url(base_url):
                return render_template_string(HTML_TEMPLATE,
                                              stats={'error': f'Invalid URL format: {base_url}'},
                                              localization_results=[])

            # Check if base URL has locale prefix (it shouldn't)
            if checker.has_locale_prefix(base_url):
                return render_template_string(HTML_TEMPLATE,
                                              stats={
                                                  'error': f'Base URL should not contain locale prefix: {base_url}. Please use non-localized URL.'},
                                              localization_results=[])

            # Check if base URL is accessible and handle redirects
            redirect_check = checker.check_url_redirect(base_url)
            if 'error' in redirect_check:
                return render_template_string(HTML_TEMPLATE,
                                              stats=redirect_check,
                                              localization_results=[])

            # If there's a redirect warning, log it but continue processing
            elif 'warning' in redirect_check:
                return render_template_string(HTML_TEMPLATE,
                                              stats=redirect_check,
                                              localization_results=[])

            # Process each selected localization
            localization_results = []
            for locale in selected_localizations:
                logger.info(f"🔍 Checking links for localization: {locale}")
                result = checker.process_single_localization(base_url, locale)
                localization_results.append(result)

            # Calculate overall statistics
            total_localizations = len(localization_results)
            successful_localizations = len([r for r in localization_results if not r['error']])
            total_links = sum(len(r['links']) for r in localization_results if not r['error'])
            total_working_links = sum(
                r['stats'].get('working_links', 0) for r in localization_results if not r['error'])
            total_broken_links = sum(
                r['stats'].get('broken_links', 0) for r in localization_results if not r['error'])
            total_localization_defects = sum(
                r['stats'].get('localization_defects', 0) for r in localization_results if not r['error'])
            total_warning_links = sum(
                r['stats'].get('warning_links', 0) for r in localization_results if not r['error'])

            overall_success_rate = (total_working_links / total_links * 100) if total_links > 0 else 0
            processing_time = time.time() - start_time

            overall_stats = {
                'base_url': base_url,
                'total_localizations': total_localizations,
                'successful_localizations': successful_localizations,
                'total_links': total_links,
                'total_working_links': total_working_links,
                'total_broken_links': total_broken_links,
                'total_warning_links': total_warning_links,
                'total_localization_defects': total_localization_defects,
                'overall_success_rate': overall_success_rate,
                'processing_time': processing_time
            }

            logger.info(
                f"✅ Bulk processing completed: {successful_localizations}/{total_localizations} URLs successful")

            # Generate CSV report
            report_filename = generate_csv_report(localization_results, base_url)

            return render_template_string(HTML_TEMPLATE,
                                          stats=overall_stats,
                                          localization_results=localization_results,
                                          report_filename=report_filename)

        except Exception as e:
            logger.exception(f"❌ Unexpected error: {e}")
            return render_template_string(HTML_TEMPLATE,
                                          stats={'error': f'Unexpected error: {str(e)}'},
                                          localization_results=[])

        finally:
            # Clean up resources
            checker.cleanup()

    return render_template_string(HTML_TEMPLATE, stats=None, localization_results=None)


if __name__ == "__main__":
    logger.info("🚀 Starting Multi-Localization Link Checker")
    app.run(debug=True, host="0.0.0.0", port=3200)