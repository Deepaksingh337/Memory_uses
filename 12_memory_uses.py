
import psutil
import time
import signal
import sys
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from collections import defaultdict

# ---------------- CONFIG ----------------
APPLICATION_NAMES = [
    "VMS_WPFClient.exe",
    "VMS_WPFConfigurationClient.exe",
    "chrome.exe"
]

SAMPLING_INTERVAL = 1  # seconds
OUTPUT_PDF = "System_Usage_Report.pdf"
# ----------------------------------------

log = []
start_time = datetime.now()

# Prime CPU counters
for p in psutil.process_iter():
    try:
        p.cpu_percent(None)
    except Exception:
        pass

net_prev = psutil.net_io_counters()
disk_prev = psutil.disk_io_counters()

# ---------------- DATA COLLECTION ----------------
def collect_metrics():
    global net_prev, disk_prev

    timestamp = datetime.now().strftime("%H:%M:%S")

    net_now = psutil.net_io_counters()
    disk_now = psutil.disk_io_counters()

    net_mbps = ((net_now.bytes_sent + net_now.bytes_recv) -
                (net_prev.bytes_sent + net_prev.bytes_recv)) * 8 / 1_000_000
    disk_mb = ((disk_now.read_bytes + disk_now.write_bytes) -
               (disk_prev.read_bytes + disk_prev.write_bytes)) / (1024 * 1024)

    net_prev, disk_prev = net_now, disk_now

    for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            if proc.info['name'] in APPLICATION_NAMES:
                cpu = proc.cpu_percent(None)
                mem = proc.info['memory_info'].rss / (1024 * 1024)

                entry = {
                    "time": timestamp,
                    "name": proc.info['name'],
                    "pid": proc.info['pid'],
                    "cpu": round(cpu, 2),
                    "mem": round(mem, 2),
                    "disk": round(disk_mb, 2),
                    "net": round(net_mbps, 2)
                }
                log.append(entry)

                # ---- LIVE TERMINAL OUTPUT (per PID) ----
                print(
                    f"[{timestamp}] "
                    f"{entry['name']:<32} "
                    f"PID {entry['pid']:>6} | "
                    f"CPU {entry['cpu']:>6}% | "
                    f"MEM {entry['mem']:>8} MB | "
                    f"DISK {entry['disk']:>6} MB/s | "
                    f"NET {entry['net']:>6} Mbps",
                    flush=True
                )

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

# ---------------- AVERAGE (PER APPLICATION) ----------------
def compute_averages_per_application():
    stats = defaultdict(lambda: {
        "cpu_sum": 0.0,
        "mem_sum": 0.0,
        "disk_sum": 0.0,
        "net_sum": 0.0,
        "count": 0
    })

    for e in log:
        app = e["name"]
        stats[app]["cpu_sum"] += e["cpu"]
        stats[app]["mem_sum"] += e["mem"]
        stats[app]["disk_sum"] += e["disk"]
        stats[app]["net_sum"] += e["net"]
        stats[app]["count"] += 1

    averages = []
    for app, s in stats.items():
        c = s["count"]
        averages.append({
            "name": app,
            "cpu": round(s["cpu_sum"] / c, 2),
            "mem": round(s["mem_sum"] / c, 2),
            "disk": round(s["disk_sum"] / c, 2),
            "net": round(s["net_sum"] / c, 2)
        })

    return averages

# ---------------- PDF GENERATION ----------------
def generate_pdf():
    if not log:
        print("No data collected.")
        return

    averages = compute_averages_per_application()

    c = canvas.Canvas(OUTPUT_PDF, pagesize=A4)
    width, height = A4
    y = height - 40

    # -------- PAGE 1+: DETAILED DATA --------
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Windows Application Resource Usage Report")
    y -= 20

    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Start Time: {start_time}")
    y -= 15
    c.drawString(40, y, f"End Time:   {datetime.now()}")
    y -= 30

    headers = ["Time", "Application", "PID", "CPU%", "Memory(MB)", "Disk(MB/s)", "Network(Mbps)"]
    x = [40, 90, 290, 340, 390, 470, 550]

    c.setFont("Helvetica-Bold", 9)
    for i, h in enumerate(headers):
        c.drawString(x[i], y, h)

    y -= 10
    c.line(40, y, width - 40, y)
    y -= 14
    c.setFont("Helvetica", 9)

    for e in log:
        if y < 40:
            c.showPage()
            y = height - 40
            c.setFont("Helvetica", 9)

        c.drawString(x[0], y, e["time"])
        c.drawString(x[1], y, e["name"])
        c.drawString(x[2], y, str(e["pid"]))
        c.drawString(x[3], y, str(e["cpu"]))
        c.drawString(x[4], y, str(e["mem"]))
        c.drawString(x[5], y, str(e["disk"]))
        c.drawString(x[6], y, str(e["net"]))
        y -= 12

    # -------- PAGE LAST: AGGREGATED AVERAGES --------
    c.showPage()
    y = height - 40

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "AVERAGE USAGE SUMMARY (Per Application)")
    y -= 30

    headers = [
        "Application",
        "Avg CPU%",
        "Avg Memory(MB)",
        "Avg Disk(MB/s)",
        "Avg Network(Mbps)"
    ]
    x = [40, 300, 380, 470, 560]

    c.setFont("Helvetica-Bold", 9)
    for i, h in enumerate(headers):
        c.drawString(x[i], y, h)

    y -= 10
    c.line(40, y, width - 40, y)
    y -= 16
    c.setFont("Helvetica", 9)

    for a in averages:
        if y < 40:
            c.showPage()
            y = height - 40
            c.setFont("Helvetica", 9)

        c.drawString(x[0], y, a["name"])
        c.drawString(x[1], y, str(a["cpu"]))
        c.drawString(x[2], y, str(a["mem"]))
        c.drawString(x[3], y, str(a["disk"]))
        c.drawString(x[4], y, str(a["net"]))
        y -= 14

    c.save()
    print(f"\nPDF generated successfully: {OUTPUT_PDF}")

# ---------------- EXIT HANDLER ----------------
def handle_exit(sig, frame):
    print("\nStopping monitoring...")
    generate_pdf()
    sys.exit(0)

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

# ---------------- MAIN LOOP ----------------
print("Monitoring (CPU | Memory | Disk | Network) for:")
for a in APPLICATION_NAMES:
    print(f" - {a}")
print("\nPress Ctrl+C to stop and generate PDF\n")

while True:
    collect_metrics()
    time.sleep(SAMPLING_INTERVAL)
