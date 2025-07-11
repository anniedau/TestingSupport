import csv
import logging
import os
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse
from urllib.parse import urlunparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, render_template_string

# Create folders if they don't exist
os.makedirs('logs', exist_ok=True)

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

# Configuration
CONFIG = {
    'timeout': 10,
    'user_agent': 'LocalizationTester/1.0',
    'valid_status_codes': [200, 201, 202, 203, 204, 205, 206],
    'max_links_per_page': 200,
    'exclude_patterns': [
        r'javascript:', r'data:', r'mailto:', r'tel:', r'#', r'\.doc$', r'\.docx$', r'\.zip$', r'\.exe$'
    ],
    'content_check_timeout': 5,
    'enable_content_validation': True
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>🌐 Localization Link Checker</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-group input { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        .btn { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; margin-right: 10px; }
        .btn:hover { background: #0056b3; }
        .btn-test { background: #17a2b8; }
        .btn-test:hover { background: #138496; }
        .error-status { color: #dc3545; font-weight: bold; }
        .success-status { color: #28a745; font-weight: bold; }
        .warning-status { color: #ffc107; font-weight: bold; font-style:italic }
        .defect-status { color: #fd7e14; font-weight: bold}
        .example {font-style: italic; }
        .stats { background: #e9ecef; padding: 15px; border-radius: 4px; margin: 20px 0; }
        .link-item { padding: 8px; border-bottom: 1px solid #eee; }
        .link-item:hover { background: #f8f9fa; }
        .export-btn { margin-right: 10px; padding: 8px 15px; border: none; border-radius: 4px; cursor: pointer; background: #28a745; color: white; }
        .localization-info { background: #d1ecf1; padding: 15px; border-radius: 4px; margin: 20px 0; }
        .test-section { background: #e3f2fd; padding: 15px; border-radius: 4px; margin: 20px 0; border-left: 4px solid #2196f3; }
        .test-section h3 { margin-top: 0; color: #1976d2; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌐 Localization Link Checker</h1>
        <p><strong>Purpose:</strong> Check all links on a localized webpage to ensure they work correctly.</p>
        
        <!-- Full Page Section -->
        <div class="test-section">
            <h3>🔍 Full Page </h3>
            <form method="post">
                <div class="form-group">
                    <label for="localization_url_full">Enter Localization URL:</label>
                    <input type="text" id="localization_url_full" name="localization_url" 
                           placeholder="https://example.com/de/ or https://example.com/fr/" required>
                    <small class="example">Example: https://www.nakivo.com/de/ (German version)</small>
                </div>
                
                <button type="submit" class="btn">🔍 Check All Links</button>
            </form>
        </div>

        {% if stats and (stats.warning or stats.error) %}
        <div class="alert-warning">
            <div style="background: #fff3cd; color: #856404; border: 1px solid #ffeeba; padding: 15px; border-radius: 4px; margin-bottom: 20px;">
            <strong>⚠️ Warning:</strong> {{ stats.warning or stats.error }}
            </div>
        </div>
        {% endif %}


        {% if stats and not (stats.warning or stats.error) %}
        <div class="localization-info">
            <h3>🌍 Localization Info</h3>
            <p><strong>Localization URL:</strong> {{ stats.base_url }}</p>
            <p><strong>Language/Region:</strong> {{ stats.language_detected }}</p>
            <p><strong>Page Title:</strong> {{ stats.page_title }}</p>
        </div>

        <div class="stats">
            <h3>📊 Link Analysis Summary</h3>
            <p><strong>Total Links Found:</strong> {{ stats.total_links }}</p>
            <p><strong>Working Links:</strong> <span class="success-status">{{ stats.working_links }}</span></p>
            <p><strong>Broken Links:</strong> <span class="error-status">{{ stats.broken_links }}</span></p>
            <p><strong>Localization Defects:</strong> <span class="defect-status">{{ stats.localization_defects }}</span></p>
            <p><strong>Success Rate:</strong> {{ "%.1f"|format(stats.success_rate) }}%</p>
            <p><strong>Processing Time:</strong> {{ "%.2f"|format(stats.processing_time) }}s</p>
        </div>
        
        <br>
        <h3>🔍 Link Results</h3>
        <div>
            {% for result in links %}
            <div class="link-item">
                <strong class="{{ 'success-status' if result.status == 'success' else 'error-status' if 'error' in result.status else 'defect-status' if result.status == 'localization_defect' else 'warning-status' }}">
                    {{ result.status_code or 'N/A' }} - {{ result.status.replace('_', ' ').title() }}
                </strong>
                <br>
                <a href="{{ result.url }}" target="_blank">{{ result.url }}</a>
                {% if result.link_text %}
                <br><small>Link Text: "{{ result.link_text[:50] }}{% if result.link_text|length > 50 %}...{% endif %}"</small>
                {% endif %}
                {% if result.localization_issue %}
                <br><small class="defect-status">Localization Issue: {{ result.localization_issue }}</small>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

def is_valid_url(url):
    regex = re.compile(
        r'^(?:http|https)://'  # http:// or https://
        r'\S+'  # domain...
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.match(regex, url) is not None


def has_locale_prefix(url):
    """Check if the URL contains a locale prefix like /de/, /fr/, etc."""
    parsed = urlparse(url)
    # Accepts /de/, /fr/, /es/, etc. at the start of the path
    return bool(re.match(r'^/([a-z]{2})(?:-[a-z]{2})?/', parsed.path))


def is_url_available(url):
    """Check if the URL is well-formed, uses http/https and responds with HTTP 200."""
    try:
        result = urlparse(url)
        if not (result.scheme in ('http', 'https') and result.netloc):
            return False
        if len(url) > 2048:
            return False
        for pattern in CONFIG['exclude_patterns']:
            if re.search(pattern, url, re.IGNORECASE):
                return False
        headers = {'User-Agent': CONFIG['user_agent']}
        response = requests.head(url, timeout=CONFIG['timeout'], headers=headers, allow_redirects=True)
        return response.status_code == 200
    except Exception as e:
        logger.exception(f"❌ URL available check failed: {e}")
        return False


def get_expected_localization_url(url, base_url):
    """Get the expected localization URL for a given link, supporting cross-domain localization"""
    parsed_base = urlparse(base_url)
    parsed_url = urlparse(url)
    base_lang = detect_language_from_url(base_url).lower()

    # If same domain, apply same localization
    if parsed_url.netloc == parsed_base.netloc:
        lang_match = re.search(r'/([a-z]{2})(?:-[a-z]{2})?/', parsed_base.path)

        if lang_match:
            lang = lang_match.group(1)
            # Replace or add language to the target URL
            target_path = parsed_url.path
            if re.search(r'/[a-z]{2}(?:-[a-z]{2})?/', target_path):
                # Replace existing language
                target_path = re.sub(r'/[a-z]{2}(?:-[a-z]{2})?/', f'/{lang}/', target_path)
            else:
                # Add language at the beginning
                target_path = f'/{lang}{target_path}'
            # Rebuild URL with fragment
            localized_url = urlunparse((
                parsed_url.scheme,
                parsed_url.netloc,
                target_path,
                parsed_url.params,
                parsed_url.query,
                parsed_url.fragment
            ))
            return localized_url

    # If different domain, try the detected language first
    if base_lang not in ['es', 'fr', 'de', 'it', 'ru']:
        base_lang = ''  # fallback to 'en' if not detected

    # Add the expected localization to the link to get the localized_url
    if not re.match(rf'^/{base_lang}(/|$)', parsed_url.path):
        localized_path = f'/{base_lang}{parsed_url.path}'
        localized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{localized_path}"
        try:
            headers = {'User-Agent': CONFIG['user_agent']}
            resp = requests.head(localized_url, timeout=CONFIG['timeout'], headers=headers, allow_redirects=True)
            if resp.status_code == 200:
                # Rebuild URL with fragment
                localized_url = urlunparse((
                    parsed_url.scheme,
                    parsed_url.netloc,
                    localized_path,
                    parsed_url.params,
                    parsed_url.query,
                    parsed_url.fragment
                ))
                return localized_url
        except Exception as e:
            logger.exception(f"❌ Error checking expected localization URL: {e}")

    # If no localized version found, return original
    return url


def extract_links_from_main_content(url):
    """Extract all links from the <main> tag of a webpage."""
    try:
        logger.info(f"🌐 Fetching webpage: {url}")
        headers = {'User-Agent': CONFIG['user_agent']}
        response = requests.get(url, timeout=CONFIG['timeout'], headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract links from the <main> tag
        main = soup.find('main')
        if not main or not hasattr(main, 'find_all'):
            logger.warning("No <main> tag found, falling back to <body> or full page.")
            main = soup.body if soup.body else soup  # fallback to whole page

        if not hasattr(main, 'find_all'):
            logger.exception("Main content is not a tag, cannot extract links.")
            return [], "Error"

        links = []
        for link in main.find_all('a', href=True):
            href = link.get('href').strip()
            link_text = link.get_text().strip()
            # ❌ Skip links containing ?pag=
            if 'pag=' in href:
                continue
            links.append({
                'url': urljoin(url, href),
                'link_text': link_text,
                'original_href': href
            })

        # Remove duplicates while preserving order
        seen = set()
        unique_links = []
        for link in links:
            if link['url'] not in seen:
                seen.add(link['url'])
                unique_links.append(link)

        # Limit number of links to check
        if len(unique_links) > CONFIG['max_links_per_page']:
            logger.warning(f"⚠️ Too many links ({len(unique_links)}), limiting to {CONFIG['max_links_per_page']}")
            unique_links = unique_links[:CONFIG['max_links_per_page']]

        logger.info(f"🔗 Found {len(unique_links)} valid links to check")
        return unique_links, soup.title.string if soup.title else "No title"

    except Exception as e:
        logger.exception(f"❌ Error fetching webpage: {e}")
        return [], "Error"


def check_link_localization(link_url, base_url, locale):
    """
    Check if the link on the localized page (for the already localized and not localized cases)
    """
    parsed_link = urlparse(link_url)

    # 1. Already localized: check head request status code first
    if re.match(rf'^/{locale}(/|$)', parsed_link.path):
        try:
            headers = {'User-Agent': CONFIG['user_agent']}
            resp = requests.head(link_url, timeout=CONFIG['timeout'], headers=headers, allow_redirects=True)
            if resp.status_code == 200:
                response = requests.get(link_url, timeout=CONFIG['timeout'], headers=headers, allow_redirects=True)
                final_url = response.url

                if response.status_code == 200:
                    # If the final URL is the same with the verify link -> success
                    if final_url.rstrip('/') == link_url.rstrip('/'):
                        return 'success', 200, None
                    # If the final URL is different with the verify link -> success, but warning redirect issue
                    if final_url.rstrip('/') != link_url.rstrip('/'):
                        return 'success', 200, f'Redirect: Final link is redirect to other valid link - {final_url}'
                # If the final link responds non-200 -> localization defect
                else:
                    return 'localization_defect', 200, f'Final link should be the default link - {final_url}; but verify link is {link_url}'
            else:
                # If status code non-200 -> defect
                return 'defect', resp.status_code, f"Localized link responds with fail status {resp.status_code}"
        except Exception as e:
            return 'error', None, f"Error checking link: {e}"

    # 2. Not localized: check the actual localization redirect; try to generate localized version
    return check_localization_consistency(link_url, base_url)


# --- Only use redirect-based logic for localization defect detection ---
def check_localization_consistency(url, base_url):
    """
    Check if the link on the localized page points to the correct localized version.
    Only report a defect if the expected localized URL exists as a real page (not a redirect).
    """
    try:
        expected_url = get_expected_localization_url(url, base_url)
        if expected_url == url:
            return 'success', 200, None

        headers = {'User-Agent': CONFIG['user_agent']}
        resp = requests.head(expected_url, timeout=CONFIG['timeout'], headers=headers, allow_redirects=True)
        if resp.status_code == 200:
            # Use GET to follow redirects and get the final URL
            response = requests.get(expected_url, timeout=CONFIG['timeout'], headers=headers, allow_redirects=True)
            final_url = response.url

            if response.status_code == 200:
                # If the final link is different with non-localized link and expect localized link -> localization defect
                if final_url.rstrip('/') != url.rstrip('/') and final_url.rstrip('/') != expected_url.rstrip('/'):
                    return 'localization_defect', 200, f'Final link - {final_url} is different with non-localized link and expect localized link'
                # If the final link and the expected localized URL exists as a real page, but the link does not point to it -> localization defect
                if final_url.rstrip('/') != url.rstrip('/')  and final_url.rstrip('/') == expected_url.rstrip('/'):
                    return 'localization_defect', 200, f'Link should point to {expected_url} (localized version exists)'
                else:
                    # If the final link is different with expected localized link -> no localized version exists, redirect to default version
                    return 'success', 200, f'No localized version exists - {expected_url}; so redirects to default version: {final_url}'
            else:
                # Localization expected link: redirect return 404 or other error: not exist -> no defect
                return 'success', response.status_code, f'Localized link responds with fail status {resp.status_code}'
        else:
            # If status code non-200 -> defect
            return 'defect', resp.status_code, f"Localized link responds with fail status {resp.status_code}"
    except Exception as e:
        logger.exception(f"❌ Cannot verify expected localization: {e}")
        return False


def detect_language_from_url(url):
    """Detect language/region from URL path."""
    parsed = urlparse(url)
    path = parsed.path.lower()

    # Common language patterns
    language_patterns = {
        'fr': ['/fr/', '/fr-fr/', '/french/', '/francais/'],
        'es': ['/es/', '/es-es/', '/spanish/', '/espanol/'],
        'de': ['/de/', '/de-de/', '/german/', '/deutsch/'],
        'it': ['/it/', '/it-it/', '/italian/', '/italiano/'],
        'ru': ['/ru/', '/ru-ru/', '/russian/', '/russkiy/']
    }

    for lang, patterns in language_patterns.items():
        for pattern in patterns:
            if pattern in path:
                return lang

    return "en"


def generate_csv_report(results, base_url):
    """Generate CSV report of link checking results."""
    os.makedirs('csv', exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"csv/l10n_{timestamp}.csv"

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['url', 'link_text', 'status_code', 'status', 'localization_issue', 'base_url']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for result in results:
            writer.writerow({
                'url': result['url'],
                'link_text': result.get('link_text', ''),
                'status_code': result.get('status_code', ''),
                'status': result.get('status', ''),
                'localization_issue': result.get('localization_issue', ''),
                'base_url': base_url
            })

    logger.info(f"📄 CSV report generated: {filename}")
    return filename


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        localization_url = request.form.get("localization_url", "").strip()
        start_time = time.time()

        if not is_valid_url(localization_url):
            stats = {
                'warning': f'Input is not a valid URL: {localization_url}'
            }
            return render_template_string(HTML_TEMPLATE, stats=stats, links=[])

        # Input validation: locale prefix
        if not has_locale_prefix(localization_url):
            stats = {
                'warning': f'Input URL is not localized (must contain locale prefix like /de/, /fr/, etc.): {localization_url}'
            }
            return render_template_string(HTML_TEMPLATE, stats=stats, links=[])

        # Input validation: URL available
        if not is_url_available(localization_url):
            stats = {
                'warning': f'Input URL is not valid or unavailable (must respond with HTTP 200): {localization_url}'
            }
            return render_template_string(HTML_TEMPLATE, stats=stats, links=[])

        # --- Parse locale ---
        locale = detect_language_from_url(localization_url)

        # --- Full Page Test Mode ---
        links_data, page_title = extract_links_from_main_content(localization_url)
        if not links_data:
            stats = {
                'warning': 'No links found or error fetching page',
                'base_url': localization_url,
                'language_detected': locale,
                'page_title': page_title,
                'total_links': 0,
                'working_links': 0,
                'broken_links': 0,
                'localization_defects': 0,
                'success_rate': 0,
                'processing_time': 0
            }
            return render_template_string(HTML_TEMPLATE, stats=stats, links=[])

        # Return the status, status code, defect information for each link after extracting link list from main content
        results = []
        for link in links_data:
            status, status_code, defect = check_link_localization(link['url'], localization_url, locale)
            results.append({
                'url': link['url'],
                'link_text': link['link_text'],
                'status': status,
                'status_code': status_code,
                'localization_issue': defect
            })

        # Response the result information
        total_links = len(results)
        working_links = len([r for r in results if r['status'] == 'success'])
        defects = len([r for r in results if r['status'] in ('error','defect')])
        localization_defects = len([r for r in results if r['status'] == 'localization_defect'])
        processing_time = time.time() - start_time
        stats = {
            'base_url': localization_url,
            'language_detected': locale,
            'page_title': page_title,
            'total_links': total_links,
            'working_links': working_links,
            'broken_links': defects,
            'localization_defects': localization_defects,
            'success_rate': (working_links / total_links * 100) if total_links else 0,
            'processing_time': processing_time
        }
        report_filename = generate_csv_report(results, localization_url)
        return render_template_string(HTML_TEMPLATE, stats=stats, links=results, report_filename=report_filename)

    return render_template_string(HTML_TEMPLATE, stats=None, links=None)


if __name__ == "__main__":
    logger.info("Starting Localization Link Checker")
    app.run(debug=True, host="0.0.0.0", port=1000)
