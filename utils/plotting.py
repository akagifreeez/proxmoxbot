import asyncio
import io
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from datetime import datetime

# Configure backend
matplotlib.use('Agg')

def create_graph_blocking(data, title, timeframe):
    """
    Synchronous function to generate the plot using Object-Oriented Matplotlib API.
    """
    times = []
    cpus = []
    mems = []
    netins = []
    netouts = []

    for point in data:
        t = point.get('time')
        c = point.get('cpu')
        m = point.get('mem')
        ni = point.get('netin')
        no = point.get('netout')

        if t is None: continue

        times.append(datetime.fromtimestamp(t))
        cpus.append((c * 100) if c is not None else 0)
        mems.append((m / 1024 / 1024) if m is not None else 0)
        netins.append((ni / 1024 / 1024) if ni is not None else 0)
        netouts.append((no / 1024 / 1024) if no is not None else 0)

    fig = Figure(figsize=(10, 12))
    ax1, ax2, ax3 = fig.subplots(3, 1, sharex=True)

    # CPU Plot
    ax1.plot(times, cpus, label='CPU Usage', color='blue')
    ax1.set_title(f'{title} - CPU Usage (%)')
    ax1.set_ylabel('Usage (%)')
    ax1.grid(True)

    # Memory Plot
    ax2.plot(times, mems, label='Memory Usage', color='orange')
    ax2.set_title(f'{title} - Memory Usage (MB)')
    ax2.set_ylabel('Memory (MB)')
    ax2.grid(True)

    # Network Plot
    ax3.plot(times, netins, label='Net In', color='green')
    ax3.plot(times, netouts, label='Net Out', color='red')
    ax3.set_title(f'{title} - Network Traffic (MB/s)')
    ax3.set_ylabel('Traffic (MB/s)')
    ax3.legend()
    ax3.grid(True)

    fig.autofmt_xdate()

    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    return buf

async def generate_graph(data, title, timeframe):
    """
    Asynchronous wrapper to run plotting in a thread.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, create_graph_blocking, data, title, timeframe)
