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
    <title>🌐 Localization Link Checker</title>
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
        <h1>🌐 Localization Link Checker</h1>
        <p><strong>Purpose:</strong> Check all links on a localized webpage to ensure they work correctly and point to proper localized versions.</p>
        
        <div class="test-section">
            <h3>🔍 Full Page Link Analysis</h3>
            <form method="post" onsubmit="showLoading()">
                <div class="form-group">
                    <label for="localization_url">Enter Localization URL:</label>
                    <input type="text" id="localization_url" name="localization_url" 
                           placeholder="https://www.nakivo.com/de/ or https://www.nakivo.com/fr/" required>
                    <div class="example">Example: Enter localized URLs</div>
                </div>
                
                <button type="submit" class="btn">🔍 Check All Links</button>
                <div class="loading">⏳ Analyzing webpage and checking links... This may take a few moments.</div>
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
                    <strong>✅ Analysis Complete!</strong> Found {{ stats.total_links }} links
                    {% if stats.localization_defects or stats.broken_links or stats.warning_links%}
                    ({% if stats.localization_defects%}{{stats.localization_defects}} defect{% endif %}{% if stats.broken_links%},
                    {{stats.broken_links}} broken{% endif %}{% if stats.warning_links %},
                    {{stats.warning_links}} warning{% endif %}){% endif %}
                    with {{(stats.success_rate or 0)|round(1)}}% success rate.
                </div>
        
                <div class="localization-info">
                    <h3>🌍 Page Information</h3>
                    <p><strong>URL:</strong> {{ stats.base_url }}</p>
                    <p><strong>Detected Language:</strong> {{ stats.language_detected.upper() }}</p>
                    <p><strong>Page Title:</strong> {{ stats.page_title }}</p>
                    <p><strong>Processing Time:</strong> {{ "%.2f"|format(stats.processing_time) }}s</p>
                </div>
        
                <div class="stats">
                    <h3>📊 Link Analysis Results</h3>
                    <div class="grid-stats">
                        <div><strong>Total Links:</strong> {{ stats.total_links }}</div>
                        <div><strong>Working Links:</strong> <span class="success-status">{{ stats.working_links }}</span></div>
                        <div><strong>Broken Links:</strong> <span class="error-status">{{ stats.broken_links }}</span></div>
                        <div><strong>Localization Defects:</strong> <span class="defect-status">{{ stats.localization_defects }}
                        </span></div>
                        <div><strong>Warning Links:</strong> <span class="warning-status">{{ stats.warning_links }}</span></div>
                    </div>
                </div>
                
                <h3>🔗 Detailed Results</h3>
                <div>
                    {% for result in links %}
                    <div class="link-item">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <strong class="{{ 'success-status' if result.status == 'success' 
                            else 'error-status' if result.status == 'error' 
                            else 'defect-status' if result.status == 'localization_defect' 
                            else 'warning-status' if result.status == 'warning'}}">
                                {{ result.status_code or 'N/A' }} - {{ result.status.replace('_', ' ').title() }}
                            </strong>
                        </div>
                        <div style="margin-top: 5px;">
                            <a href="{{ result.url }}" target="_blank" style="color: #007bff; text-decoration: none;">
                            {{ result.url }}</a>
                        </div>
                        {% if result.link_text %}
                        <div style="margin-top: 5px; font-size: 12px">
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
        """Check if URL redirects to another URL"""
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
                logger.info("No <main> or <section> tags found. Extracting links from <body>.")
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
                            'issue': f"No localized version exists - {expected_localized}, returns status code: {resp.status_code}"
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
        localization_url = request.form.get("localization_url", "").strip()

        # Initialize link checker
        checker = LinkChecker()

        try:
            start_time = time.time()

            # Validate URL
            if not checker.is_valid_url(localization_url):
                return render_template_string(HTML_TEMPLATE, stats={'error': f'Invalid URL format: {localization_url}'},
                                              links=[])

            if not checker.has_locale_prefix(localization_url):
                return render_template_string(HTML_TEMPLATE, stats={'error': f'URL must contain locale prefix (e.g., '
                                                                             f'/de/, /fr/): {localization_url}'},
                                              links=[])

            # Check finalized redirect link
            redirect_info = checker.is_url_redirect(localization_url)

            # If there's an error accessing the URL
            if redirect_info['error']:
                return render_template_string(HTML_TEMPLATE,
                                              stats={'error': f'Cannot access URL: {redirect_info["error"]}'},
                                              links=[])

            # If URL redirects to a different URL
            if redirect_info['redirected']:
                return render_template_string(HTML_TEMPLATE, stats={
                    'warning': f'URL redirects to other link: {redirect_info["final_url"]}. Input link: {localization_url}'
                }, links=[])

            # Extract links
            links_data, page_title = checker.extract_links(localization_url)
            if not links_data:
                return render_template_string(HTML_TEMPLATE,
                                              stats={'warning': f'No links found on the page {localization_url}'},
                                              links=[])

            # Detect language
            locale = checker.detect_language(localization_url)

            # Check each link
            results = []
            for j, link_data in enumerate(links_data, 1):
                logger.info(f"🔍 Checking link {j}/{len(links_data)}: {link_data['url']}")
                result = checker.check_link_localization(link_data['url'], localization_url, locale)
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
            processing_time = time.time() - start_time

            stats = {
                'base_url': localization_url,
                'language_detected': locale,
                'page_title': page_title,
                'total_links': total_links,
                'working_links': working_links,
                'broken_links': broken_links,
                'localization_defects': localization_defects,
                'warning_links': warning_links,
                'success_rate': (working_links / total_links * 100) if total_links else 0,
                'processing_time': processing_time
            }

            logger.info(f"✅ Successfully processed: {localization_url} - {total_links} links,"
                        f" {working_links} working, {localization_defects} localization defect, {broken_links} broken")

            # Generate CSV report
            report_filename = generate_csv_report(results, localization_url)

            return render_template_string(HTML_TEMPLATE, stats=stats, links=results, report_filename=report_filename)

        except Exception as e:
            logger.exception(f"❌ Unexpected error: {e}")
            return render_template_string(HTML_TEMPLATE, stats={'error': f'Unexpected error: {str(e)}'}, links=[])

        finally:
            # Clean up resources
            checker.cleanup()

    return render_template_string(HTML_TEMPLATE, stats=None, links=None)


if __name__ == "__main__":
    logger.info("🚀 Starting Localization Link Checker")
    app.run(debug=True, host="0.0.0.0", port=4100)
