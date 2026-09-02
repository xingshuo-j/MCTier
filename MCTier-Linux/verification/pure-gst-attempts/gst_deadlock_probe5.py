#!/usr/bin/env python3
"""复现尝试 v5: 反复 link/unlink + 持续推事件 制造 sticky 重推窗口
GStreamer 在"新 pad 接入/重 link"时会向上游请求 sticky 事件重推,
此时若另一线程同时在推事件 → 持锁交叉窗口
"""
import gi, threading, time
gi.require_version('Gst', '1.0')
from gi.repository import Gst

Gst.init(None)

src = Gst.ElementFactory.make('audiotestsrc', 'src')
src.set_property('num-buffers', -1)
tee = Gst.ElementFactory.make('tee', 'tee')
mainq = Gst.ElementFactory.make('queue', 'mainq')
sink = Gst.ElementFactory.make('fakesink', 'sink')
sink.set_property('sync', False)

pipeline = Gst.Pipeline.new('t5')
for e in (src, tee, mainq, sink):
    pipeline.add(e)
src.link(tee)
tee.link(mainq); mainq.link(sink)

stop = threading.Event()

def relinker():
    """反复在 tee 上加/删分支: 每次新分支请求 sticky 重推"""
    i = 0
    while not stop.is_set():
        q = Gst.ElementFactory.make('queue', f'q{i%7}')
        fs = Gst.ElementFactory.make('fakesink', f'fs{i%7}')
        fs.set_property('sync', False)
        pipeline.add(q); pipeline.add(fs)
        q.link(fs)
        # 请求 tee 的一个 sink pad 并 link
        pad = tee.request_pad_simple('src_%u')
        # 把 q 的 sink pad link 到 tee 的这个 src pad
        qpad = q.get_static_pad('sink')
        if pad and qpad:
            ret = pad.link(qpad)
            if ret != Gst.PadLinkReturn.OK:
                pad.unlink(qpad)
        i += 1
        if i % 100 == 0:
            # 清理旧分支: unlink + remove
            pass
    print(f'[relinker] 完成 {i} 次')

def cappusher():
    """另一个线程持续推 CAPS (触发 sticky 检查)"""
    caps = Gst.Caps.from_string('audio/x-raw,format=(string)S16LE,rate=(int)48000,channels=(int)2')
    spad = src.get_static_pad('src')
    i = 0
    while not stop.is_set():
        spad.push_event(Gst.Event.new_caps(caps))
        i += 1
    print(f'[pusher] 推 {i} 次')

print('启动...')
pipeline.set_state(Gst.State.PLAYING)
time.sleep(1)
t1 = threading.Thread(target=relinker, daemon=True)
t2 = threading.Thread(target=cappusher, daemon=True)
t1.start(); t2.start()
for i in range(15):
    time.sleep(1)
    if i % 5 == 4:
        print(f'  {i+1}s (relink={t1.is_alive()}, push={t2.is_alive()})')
print('停止...')
stop.set(); time.sleep(2)
a,b = t1.is_alive(), t2.is_alive()
print(f'relink={a}, push={b}')
print('⚠️ 疑似死锁' if (a or b) else '✅ 无死锁')
pipeline.set_state(Gst.State.NULL)
