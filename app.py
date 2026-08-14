# app.py
from flask import Flask, render_template, request, jsonify, session
import requests
import threading
import time
import json
from datetime import datetime
import os
import re

app = Flask(__name__)
app.secret_key = os.urandom(24)

# গ্লোবাল ভেরিয়েবল
urls = []
monitoring_thread = None
is_monitoring = False
response_logs = []

class URLMonitor:
    def __init__(self):
        self.urls = []  # [{url: "https://...", interval: 10, status: "pending"}]
        self.is_running = False
        self.thread = None
        self.logs = []
        self.default_interval = 10
    
    def add_url(self, url, interval=10):
        url = url.strip()
        if '://' in url:
            parts = url.split('://')
            if len(parts) == 2:
                url = parts[0] + '://' + parts[1].replace('//', '/')
        
        for item in self.urls:
            if item['url'] == url:
                return False
        
        self.urls.append({
            'url': url,
            'interval': int(interval) if interval else self.default_interval,
            'status': 'pending',  # pending, success, error
            'last_check': None,
            'status_code': None
        })
        return True
    
    def remove_url(self, url):
        for i, item in enumerate(self.urls):
            if item['url'] == url:
                self.urls.pop(i)
                return True
        return False
    
    def update_interval(self, url, interval):
        for item in self.urls:
            if item['url'] == url:
                item['interval'] = int(interval)
                return True
        return False
    
    def get_urls(self):
        return self.urls.copy()
    
    def get_url_list(self):
        return [item['url'] for item in self.urls]
    
    def start_monitoring(self):
        if not self.is_running and len(self.urls) > 0:
            self.is_running = True
            self.thread = threading.Thread(target=self._monitor_loop)
            self.thread.daemon = True
            self.thread.start()
            print(f"✅ Monitoring started with {len(self.urls)} URLs")
            return True
        return False
    
    def stop_monitoring(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=1)
        print("⏹️ Monitoring stopped")
        return True
    
    def _monitor_loop(self):
        print("🔄 Monitor loop started")
        while self.is_running:
            for item in self.urls:
                url = item['url']
                interval = item.get('interval', self.default_interval)
                try:
                    print(f"📡 Calling: {url}")
                    status_code, success = self._check_url(url)
                    
                    # Update status
                    item['last_check'] = datetime.now().strftime("%H:%M:%S")
                    item['status_code'] = status_code
                    item['status'] = 'success' if success else 'error'
                    
                    print(f"✅ Response from: {url} - Status: {status_code}")
                except Exception as e:
                    item['status'] = 'error'
                    item['last_check'] = datetime.now().strftime("%H:%M:%S")
                    item['status_code'] = None
                    print(f"❌ Error calling {url}: {str(e)}")
                time.sleep(interval)
    
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
            
            # 200-299 মানে সফল
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

@app.route('/')
def index():
    return render_template('index.html', 
                         urls=monitor.get_urls(), 
                         is_monitoring=monitor.is_running)

@app.route('/add-url', methods=['POST'])
def add_url():
    url = request.form.get('url')
    interval = request.form.get('interval', 10)
    if url:
        url = url.strip()
        try:
            interval = int(interval)
            if interval < 1:
                interval = 1
        except:
            interval = 10
            
        if monitor.add_url(url, interval):
            print(f"➕ URL added: {url} (interval: {interval}s)")
            return jsonify({"success": True, "message": f"URL added successfully with {interval}s interval"})
        else:
            return jsonify({"success": False, "message": "URL already exists"})
    return jsonify({"success": False, "message": "No URL provided"})

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
    if url and interval:
        try:
            interval = int(interval)
            if interval < 1:
                interval = 1
            if monitor.update_interval(url, interval):
                print(f"⏱️ Interval updated: {url} -> {interval}s")
                return jsonify({"success": True, "message": f"Interval updated to {interval} seconds"})
            else:
                return jsonify({"success": False, "message": "URL not found"})
        except ValueError:
            return jsonify({"success": False, "message": "Invalid interval value"})
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
            
            # Manual call এর জন্য URL এর স্ট্যাটাস আপডেট
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
                "success": result['success'],
                "status_code": result['status_code']
            })
        except Exception as e:
            results.append({
                "url": url,
                "interval": item.get('interval', 10),
                "success": False,
                "error": str(e)
            })
    
    return jsonify({
        "message": f"Refreshing status for {len(urls)} targets...",
        "method": "GET",
        "refreshed": len(urls),
        "status": "completed",
        "success": True,
        "targets": results
    })

if __name__ == '__main__':
    print("🚀 MAHIR URL Monitor starting...")
    print(f"📍 Server running on: http://localhost:9414")
    app.run(debug=True, host='0.0.0.0', port=9414)