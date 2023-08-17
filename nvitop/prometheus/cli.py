import threading
from flask import Response, Flask
import prometheus_client
from prometheus_client import Gauge, CollectorRegistry
import asyncio
import schedule
import time
import socket
from nvitop.api import libnvml
from nvitop.gui import Device, colored
import sys
import logging
import os
logging.getLogger("werkzeug").setLevel(os.getenv('LOGLEVEL', default='WARNING').upper())

ip_addr = socket.gethostbyname(socket.gethostname())
registry = CollectorRegistry(auto_describe=False)
device_count = 0


def doUpdateMetrics():
    global registry
    newRegistry = CollectorRegistry(auto_describe=False)
    gpu_pid_sm_util = Gauge("gpu_pid_sm_util", "gpu_pid_sm_util", ["time_span", "ip_addr", "gpu_index", "pid"], registry=newRegistry)
    gpu_pid_mem_used = Gauge("gpu_pid_mem_used", "gpu_pid_mem_used", ["time_span", "ip_addr", "gpu_index", "pid"],
                             registry=newRegistry)
    gpu_pid_mem_total = Gauge("gpu_pid_mem_total", "gpu_pid_mem_total", ["time_span", "ip_addr", "gpu_index", "pid"],
                              registry=newRegistry)

    mem_total = {}
    sm_util = {}
    mem_used = {}
    indices = set(range(device_count))
    devices = Device.from_indices(sorted(indices))

    for device in devices:
        mem_total[str(device.index)] = int(device.memory_total() / 1024 / 1024)
        processes = device.processes().values()
        for process in processes:
            sm_util[(str(device.index), str(process.pid))] = process.gpu_sm_utilization()
            mem_used[(str(device.index), str(process.pid))] = int(process._gpu_memory / 1024 / 1024)
    for key in sm_util:
        pid = key[1]
        gpu_index = key[0]
        util = sm_util[key]
        gpu_pid_sm_util.labels("250ms", ip_addr, gpu_index, pid).set(util)

    for key in mem_used:
        pid = key[1]
        gpu_index = key[0]
        if gpu_index not in mem_total:
            continue
        total = mem_total[gpu_index]
        used = mem_used[key]
        gpu_pid_mem_total.labels("250ms", ip_addr, gpu_index, pid).set(total)
        gpu_pid_mem_used.labels("250ms", ip_addr, gpu_index, pid).set(used)
    registry = newRegistry


def updateMetrics():
    global device_count
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        device_count = Device.count()
    except libnvml.NVMLError_LibraryNotFound:
        print("libnvml.NVMLError_LibraryNotFound")
        return
    except libnvml.NVMLError as ex:
        print(
            '{} {}'.format(colored('NVML ERROR:', color='red', attrs=('bold',)), ex),
            file=sys.stderr,
        )
        return
    schedule.every(1).seconds.do(doUpdateMetrics)
    while True:
        schedule.run_pending()
        time.sleep(1)


app = Flask(__name__)


@app.route("/metrics")
def metrics():
    return Response(prometheus_client.generate_latest(registry), mimetype="text/plain")


def main() -> int:
    thread = threading.Thread(target=updateMetrics)
    thread.start()
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    sys.exit(main())
