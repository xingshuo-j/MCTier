#!/usr/bin/env python3
"""复现尝试 v3: 用真实 gst_base_src 任务线程的协商路径
两个 fakesrc(设为 live) 任务线程在 PLAYING 中反复改 caps → 触发真正的
gst_base_src_negotiate → set_caps → push_event(CAPS) 路径(与死锁 Thread A 一致)
共享下游 tee 制造交叉
"""
import gi, threading, time
gi.require_version('Gst', '1.0')
from gi.repository import Gst

Gst.init(None)

def make_src(name, fmt):
    s = Gst.ElementFactory.make('fakesrc', name)
    s.set_property('is-live', True)   # 任务线程持续运行
    s.set_property('num-buffers', -1) # 无限
    caps = Gst.Caps.from_string(f'audio/x-raw,format=(string){fmt},rate=(int)48000,channels=(int)2')
    s.set_property('caps', caps)
    return s

src1 = make_src('src1', 'S16LE')
src2 = make_src('src2', 'F32LE')
q1 = Gst.ElementFactory.make('queue', 'q1')
q2 = Gst.ElementFactory.make('queue', 'q2')
tee = Gst.ElementFactory.make('tee', 'tee')
qs = Gst.ElementFactory.make('queue', 'qs')
sink = Gst.ElementFactory.make('fakesink', 'sink')
sink.set_property('sync', False)

pipeline = Gst.Pipeline.new('t3')
for e in (src1, src2, q1, q2, tee, qs, sink):
    pipeline.add(e)
src1.link(q1); src2.link(q2)
q1.link(tee); q2.link(tee)
tee.link(qs); qs.link(sink)

stop = threading.Event()

def flipsrc(s, name, fmts):
    """循环改 src 的 caps, 强制任务线程反复协商/重推 CAPS"""
    i = 0
    while not stop.is_set():
        f = fmts[i % len(fmts)]
        c = Gst.Caps.from_string(f'audio/x-raw,format=(string){f},rate=(int)(48000+i%3*1000),channels=(int)2')
        s.set_property('caps', c)   # 改 caps → 任务线程重新协商 → set_caps → push CAPS
        i += 1
    print(f'[{name}] 切换 {i} 次格式')

print('启动管道 (两源为 live, 任务线程持续协商)...')
pipeline.set_state(Gst.State.PLAYING)
time.sleep(1.0)

t1 = threading.Thread(target=flipsrc, args=(src1, 'flip1', ['S16LE','F32LE','S24LE']), daemon=True)
t2 = threading.Thread(target=flipsrc, args=(src2, 'flip2', ['U8','S32LE','F64LE']), daemon=True)
t1.start(); t2.start()

print('压力测试 25 秒...')
for i in range(25):
    time.sleep(1)
    if i % 5 == 4:
        print(f'  {i+1}s')

print('停止...')
stop.set(); time.sleep(1.5)
a, b = t1.is_alive(), t2.is_alive()
pipeline.set_state(Gst.State.NULL)
print(f'flip1 alive={a}, flip2 alive={b}')
print('⚠️ 疑似死锁!' if (a or b) else '✅ 无死锁')
