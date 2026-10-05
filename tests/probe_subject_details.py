"""Manual development probe: one read-only subject page; no persisted secrets."""
from scrapling.fetchers import DynamicSession
from compset.collect import _quiet_scrapling
from urllib.parse import urlsplit
import json
from pathlib import Path

operations = set()
def setup(page):
    page.on('request', lambda request: operations.add(urlsplit(request.url).path.split('/')[3]) if '/api/v3/' in request.url else None)

def action(page):
    page.wait_for_timeout(2500)
    controls = []
    for button in page.locator('button').all():
        label = (button.get_attribute('aria-label') or button.inner_text()).strip()
        if 'amenities' in label.lower():
            controls.append(label)
            if button.is_visible() and ('show all' in label.lower()):
                button.click(timeout=2500)
                page.wait_for_timeout(2000)
                break
    print('AMENITY_CONTROLS', controls)

with _quiet_scrapling(), DynamicSession(headless=True, executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', capture_xhr=r'/api/v3/', retries=1, timeout=45000, google_search=False) as session:
    result = session.fetch('https://www.airbnb.co.in/rooms/1567889913136387224?currency=AED&adults=2&check_in=2026-10-17&check_out=2026-10-20',page_setup=setup,page_action=action,wait=500)
    print('OPS', sorted(operations))
    for response in result.captured_xhr:
        if 'StaysPdpSections' in response.url:
            from compset.collect import _payload
            payload = _payload(response,response.url)
            Path('data/amenities-probe.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
            print('AMENITY_SOURCE',payload['source_url'],response.status)
