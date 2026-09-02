#!/usr/bin/env python3
"""复现尝试 v4: audiotestsrc 真实协商路径 + 双源共享 tee
audiotestsrc 任务线程在 PLAYING 中反复改 caps → 每次触发
gst_base_src_negotiate → set_caps → gst_pad_push_event(CAPS)
(与死锁 Thread A 的 gst_base_src_set_caps 路径一致)
两源共享 tee 下游 → 两任务线程的 sticky 重推在 tee 附近交叉
"""
import gi, threading, time
gi.require_version('Gst', '1.0')
from gi.repository import Gst

Gst.init(None)

def make_src(name, fmt, rate):
    s = Gst.ElementFactory.make('audiotestsrc', name)
    s.set_property('num-buffers', -1)  # 无限
    s.set_property('wave', 0)
    # 固定初始 caps
    fc = Gst.ElementFactory.make('capsfilter', name+'-cap')
    c = Gst.Caps.from_string(f'audio/x-raw,format=(string){fmt},rate=(int){rate},channels=(int)2')
    fc.set_property('caps', c)
    return s, fc

s1, f1 = make_src('s1', 'S16LE', 48000)
s2, f2 = make_src('s2', 'F32LE', 48000)
tee = Gst.ElementFactory.make('tee', 'tee')
qs = Gst.ElementFactory.make('queue', 'qs')
sink = Gst.ElementFactory.make('fakesink', 'sink')
sink.set_property('sync', False)

pipeline = Gst.Pipeline.new('t4')
for e in (s1, f1, s2, f2, tee, qs, sink):
    pipeline.add(e)
s1.link(f1); f1.link(tee)
s2.link(f2); f2.link(tee)
tee.link(qs); qs.link(sink)

stop = threading.Event()

def flip(name, capfilter, fmts, base_rate):
    """循环切换 capsfilter 的 caps → 触发源任务线程重新协商并重推 CAPS"""
    i = 0
    while not stop.is_set():
        f = fmts[i % len(fmts)]
        c = Gst.Caps.from_string(f'audio/x-raw,format=(string){f},rate=(int){base_rate + (i%5)*1000},channels=(int)2')
        capfilter.set_property('caps', c)
        i += 1
        if i % 2000 == 0:
            pass
    print(f'[{name}] 切换 {i} 次')

print('启动管道...')
pipeline.set_state(Gst.State.PLAYING)
time.sleep(1.5)

t1 = threading.Thread(target=flip, args=('A', f1, ['S16LE','S24LE','S32LE'], 48000), daemon=True)
t2 = threading.Thread(target=flip, args=('B', f2, ['F32LE','F64LE','U8'], 44100), daemon=True)
t1.start(); t2.start()

print('压力测试 25 秒...')
for i in range(25):
    time.sleep(1)
    if i % 5 == 4:
        print(f'  {i+1}s  (A={t1.is_alive()}, B={t2.is_alive()})')

print('停止...')
stop.set(); time.sleep(2)
a, b = t1.is_alive(), t2.is_alive()
# 若卡死, 线程无法 join — 先检查 alive 再 NULL
print(f'A alive={a}, B alive={b}')
if not (a or b):
    pipeline.set_state(Gst.State.NULL)
    print('✅ 无死锁')
else:
    print('⚠️ 疑似死锁 (线程无法退出)')
