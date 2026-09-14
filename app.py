from flask import Flask, render_template, request, jsonify
import requests
import threading
import time
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)


class URLMonitor:
    def __init__(self):
        self.urls = []  # [{url, interval_seconds, unit, status, last_check, status_code, next_check}]
        self.is_running = False
        self.thread = None
        self.lock = threading.Lock()
        self.default_interval = 10  # seconds
        self.default_unit = 'seconds'

    def add_url(self, url, interval=10, unit='seconds'):
        url = url.strip()
        if '://' in url:
            parts = url.split('://')
            if len(parts) == 2:
                url = parts[0] + '://' + parts[1].replace('//', '/')

        with self.lock:
            for item in self.urls:
                if item['url'] == url:
                    return False

            try:
                interval = int(interval)
                if interval < 1:
                    interval = 1
            except:
                interval = self.default_interval

            # Convert to seconds
            if unit == 'minutes':
                interval_seconds = interval * 60
            else:
                interval_seconds = interval
                unit = 'seconds'

            self.urls.append({
                'url': url,
                'interval': interval,           # value as entered by user
                'unit': unit,                   # 'seconds' or 'minutes'
                'interval_seconds': interval_seconds,  # always in seconds
                'status': 'pending',
                'last_check': None,
                'status_code': None,
                'next_check': None,
                'last_response_time': None
            })
            return True

    def remove_url(self, url):
        with self.lock:
            for i, item in enumerate(self.urls):
                if item['url'] == url:
                    self.urls.pop(i)
                    return True
            return False

    def update_interval(self, url, interval, unit='seconds'):
        with self.lock:
            for item in self.urls:
                if item['url'] == url:
                    try:
                        interval = int(interval)
                        if interval < 1:
                            interval = 1
                    except:
                        return False

                    if unit == 'minutes':
                        interval_seconds = interval * 60
                    else:
                        interval_seconds = interval
                        unit = 'seconds'

                    item['interval'] = interval
                    item['unit'] = unit
                    item['interval_seconds'] = interval_seconds
                    item['next_check'] = time.time() + interval_seconds
                    return True
            return False

    def get_urls(self):
        with self.lock:
            return [item.copy() for item in self.urls]

    def get_url_list(self):
        with self.lock:
            return [item['url'] for item in self.urls]

    def start_monitoring(self):
        with self.lock:
            if not self.is_running and len(self.urls) > 0:
                self.is_running = True
                # Set next_check for all URLs to now (immediate check)
                now = time.time()
                for item in self.urls:
                    item['next_check'] = now
                self.thread = threading.Thread(target=self._monitor_loop)
                self.thread.daemon = True
                self.thread.start()
                print(f"✅ Monitoring started with {len(self.urls)} URLs")
                return True
            return False

    def stop_monitoring(self):
        with self.lock:
            self.is_running = False
        if self.thread:
            self.thread.join(timeout=2)
        print("⏹️ Monitoring stopped")
        return True

    def _monitor_loop(self):
        """Main loop - checks each URL when its time is due (precise timing per URL)."""
        print("🔄 Monitor loop started")
        while self.is_running:
            now = time.time()
            # Snapshot the list to avoid holding lock during network call
            with self.lock:
                items = list(self.urls)

            for item in items:
                if not self.is_running:
                    break

                next_check = item.get('next_check') or 0
                if now >= next_check:
                    # Schedule next check time IMMEDIATELY so it's not blocked
                    interval_seconds = item.get('interval_seconds', 10)
                    item['next_check'] = time.time() + interval_seconds

                    # Do the actual HTTP check
                    url = item['url']
                    try:
                        print(f"📡 Calling: {url}")
                        start = time.time()
                        status_code, success = self._check_url(url)
                        elapsed = round(time.time() - start, 3)

                        item['last_check'] = datetime.now().strftime("%H:%M:%S")
                        item['status_code'] = status_code
                        item['status'] = 'success' if success else 'error'
                        item['last_response_time'] = elapsed

                        print(f"✅ {url} -> {status_code} ({elapsed}s)")
                    except Exception as e:
                        item['status'] = 'error'
                        item['last_check'] = datetime.now().strftime("%H:%M:%S")
                        item['status_code'] = None
                        item['last_response_time'] = None
                        print(f"❌ Error calling {url}: {e}")

            # Small sleep to avoid busy loop
            time.sleep(0.5)

    def _check_url(self, url):
        try:
            url = url.strip()
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive'
            }

            response = requests.get(url, timeout=10, headers=headers, allow_redirects=True)
            status_code = response.status_code
            success = 200 <= status_code < 400
            return status_code, success
        except requests.exceptions.Timeout:
            return None, False
        except requests.exceptions.ConnectionError:
            return None, False
        except requests.exceptions.RequestException:
            return None, False
        except Exception:
            return None, False

    def _call_url(self, url):
        try:
            url = url.strip()
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive'
            }

            response = requests.get(url, timeout=10, headers=headers, allow_redirects=True)
            return {"status_code": response.status_code, "success": 200 <= response.status_code < 400}
        except:
            return {"status_code": None, "success": False}


monitor = URLMonitor()


def format_interval(item):
    """Human readable interval string."""
    val = item.get('interval', 10)
    unit = item.get('unit', 'seconds')
    if unit == 'minutes':
        return f"{val} min"
    return f"{val} sec"


app.jinja_env.globals['format_interval'] = format_interval


@app.route('/')
def index():
    return render_template('index.html',
                           urls=monitor.get_urls(),
                           is_monitoring=monitor.is_running)


@app.route('/add-url', methods=['POST'])
def add_url():
    url = request.form.get('url')
    interval = request.form.get('interval', 10)
    unit = request.form.get('unit', 'seconds')
    if url:
        url = url.strip()
        try:
            interval = int(interval)
            if interval < 1:
                interval = 1
        except:
            interval = 10

        if unit not in ('seconds', 'minutes'):
            unit = 'seconds'

        if monitor.add_url(url, interval, unit):
            # Auto immediate check when URL is added
            threading.Thread(target=immediate_check, args=(url,), daemon=True).start()
            print(f"➕ URL added: {url} ({interval} {unit})")
            return jsonify({"success": True, "message": f"URL added ({interval} {unit})"})
        else:
            return jsonify({"success": False, "message": "URL already exists"})
    return jsonify({"success": False, "message": "No URL provided"})


def immediate_check(url):
    """Run an immediate check for a single URL."""
    try:
        result = monitor._call_url(url)
        with monitor.lock:
            for item in monitor.urls:
                if item['url'] == url:
                    item['status'] = 'success' if result['success'] else 'error'
                    item['status_code'] = result['status_code']
                    item['last_check'] = datetime.now().strftime("%H:%M:%S")
                    item['next_check'] = time.time() + item.get('interval_seconds', 10)
                    break
        print(f"⚡ Immediate check done for {url}: {result}")
    except Exception as e:
        print(f"Immediate check error: {e}")


@app.route('/remove-url', methods=['POST'])
def remove_url():
    url = request.form.get('url')
    if url:
        if monitor.remove_url(url):
            print(f"➖ URL removed: {url}")
            return jsonify({"success": True, "message": "URL removed successfully"})
        else:
            return jsonify({"success": False, "message": "URL not found"})
    return jsonify({"success": False, "message": "No URL provided"})


@app.route('/update-interval', methods=['POST'])
def update_interval():
    url = request.form.get('url')
    interval = request.form.get('interval')
    unit = request.form.get('unit', 'seconds')
    if url and interval:
        try:
            interval = int(interval)
            if interval < 1:
                interval = 1
        except ValueError:
            return jsonify({"success": False, "message": "Invalid interval value"})

        if unit not in ('seconds', 'minutes'):
            unit = 'seconds'

        if monitor.update_interval(url, interval, unit):
            print(f"⏱️ Interval updated: {url} -> {interval} {unit}")
            return jsonify({"success": True, "message": f"Interval updated to {interval} {unit}"})
        else:
            return jsonify({"success": False, "message": "URL not found"})
    return jsonify({"success": False, "message": "Missing data"})


@app.route('/start-monitoring', methods=['POST'])
def start_monitoring():
    if monitor.start_monitoring():
        return jsonify({"success": True, "message": "Monitoring started"})
    return jsonify({"success": False, "message": "No URLs to monitor or already running"})


@app.route('/stop-monitoring', methods=['POST'])
def stop_monitoring():
    if monitor.stop_monitoring():
        return jsonify({"success": True, "message": "Monitoring stopped"})
    return jsonify({"success": False, "message": "Monitor not running"})


@app.route('/get-urls')
def get_urls():
    return jsonify({"urls": monitor.get_urls(), "is_monitoring": monitor.is_running})


@app.route('/manual-call', methods=['POST'])
def manual_call():
    url = request.form.get('url')
    if url:
        try:
            url = url.strip()
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            result = monitor._call_url(url)

            with monitor.lock:
                for item in monitor.urls:
                    if item['url'] == url:
                        item['status'] = 'success' if result['success'] else 'error'
                        item['status_code'] = result['status_code']
                        item['last_check'] = datetime.now().strftime("%H:%M:%S")
                        break

            return jsonify({"success": result['success'], "status_code": result['status_code']})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})
    return jsonify({"success": False, "message": "No URL provided"})


@app.route('/api/refresh-all-status', methods=['GET', 'POST'])
def refresh_all_status():
    urls = monitor.get_urls()
    results = []

    for item in urls:
        url = item['url']
        try:
            result = monitor._call_url(url)
            results.append({
                "url": url,
                "interval": item.get('interval', 10),
                "unit": item.get('unit', 'seconds'),
                "success": result['success'],
                "status_code": result['status_code']
            })
        except Exception as e:
            results.append({
                "url": url,
                "interval": item.get('interval', 10),
                "unit": item.get('unit', 'seconds'),
                "success": False,
                "error": str(e)
            })

    return jsonify({
        "message": f"Refreshed {len(urls)} targets",
        "refreshed": len(urls),
        "status": "completed",
        "success": True,
        "targets": results
    })


if __name__ == '__main__':
    print("🚀 MAHIR URL Monitor starting...")
    print("📍 Server running on: http://localhost:9414")
    app.run(debug=True, host='0.0.0.0', port=9414)
