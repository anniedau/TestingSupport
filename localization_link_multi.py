import logging
import os

from flask import Flask

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
                    <label>Select Localizations to Check:</label>
                    <button type="button" class="select-all-btn" onclick="toggleAll()">Select All</button>
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
                    <div><strong>Base URL:</strong> {{ stats.base_url }}</div>
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
                            <h4>🌍 {{ locale_result.locale.upper() }} - {{ locale_result.localized_url }}</h4><br>
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
